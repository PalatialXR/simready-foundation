# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import copy
import enum
import importlib
import json
import logging
import sys
import tempfile
import tomllib as toml
import traceback
from pathlib import Path
from typing import Optional, Union

import omni.capabilities
from omni.asset_validator import (
    Capability,
    CapabilityRegistry,
    Issue,
    IssueSeverity,
    Profile,
    ProfileRegistry,
    RequirementsRegistry,
    ValidationEngine,
)
from omni.usd_profiles.codegen._py_generate import PythonGenerator

__all__ = [
    "load_validation_implementation",
]

logger = logging.getLogger("Validation Sample")


def load_validation_implementation(
    rules_and_requirements_paths: list[Path],
    features_paths: list[Path],
    profiles_paths: list[Path],
) -> None:
    """Load the validation implementation from the given filesystem paths."""

    def _find_tomls_and_jsons(path: Path) -> list[Path]:
        if path.is_dir():
            return list(path.glob("*.json")) + list(path.glob("*.toml"))
        else:
            return [path]

    # Unregister any existing validation rules/features/profiles, to ensure that we're using only what we load ourselves
    _unregister_all_existing_implementations()
    # Ensure all requirements specified in json files are defined in omni.capabilities before loading any rules
    _generate_missing_requirements(rules_and_requirements_paths)
    # Then load rules & reqs from a local python module, as they might depend on omni.capabilities requirements
    for rules_and_requirements_path in rules_and_requirements_paths:
        _load_python_module(rules_and_requirements_path)
    # Load the features next, as they depend on the requirements
    for feature_path in features_paths:
        if feature_path.is_dir():
            for feature_file in _find_tomls_and_jsons(feature_path):
                _load_and_register_feature(feature_file)
    # Load the profiles last, as they depend on the features
    for profile_path in profiles_paths:
        _load_and_register_profile(profile_path)


def _unregister_all_existing_implementations() -> None:
    """Unregister any validation requirements, rules, features, and profiles that are already registered"""
    logger.info("Clearing requirements registry")
    RequirementsRegistry().clear()
    RequirementsRegistry()._req_to_rule.clear()
    RequirementsRegistry()._rule_to_req.clear()
    logger.info("Clearing features registry")
    keys_to_delete = list(CapabilityRegistry().keys())
    for key in keys_to_delete:
        del CapabilityRegistry()[key]
    logger.info("Clearing profiles registry")
    keys_to_delete = list(ProfileRegistry().keys())
    for key in keys_to_delete:
        del ProfileRegistry()[key]


def _generate_missing_requirements(rules_and_requirements_paths: list[Path]) -> None:
    """Generate missing requirements from json/toml files using PythonGenerator and inject into omni.capabilities."""
    try:
        logger.info(f"Generating requirements from {len(rules_and_requirements_paths)} path(s)")

        for req_path in rules_and_requirements_paths:
            logger.info(f"Processing requirements from: {req_path}")

            with tempfile.TemporaryDirectory() as tmpdirname:
                try:
                    generator = PythonGenerator(
                        capabilities_root=req_path,
                        destination_dir=tmpdirname,
                        namespace="omni.generated_capabilities",
                    )
                    generator.generate()
                    logger.info(f"Successfully generated code from {req_path}")
                except Exception as gen_error:
                    logger.error(f"Error running PythonGenerator on {req_path}: {repr(gen_error)}")
                    traceback.print_exc()
                    continue

                sys.path.insert(0, tmpdirname)
                try:
                    sys.modules.pop("omni.generated_capabilities", None)

                    generated_capabilities = importlib.import_module("omni.generated_capabilities")
                    for attr_name in dir(generated_capabilities):
                        attr = getattr(generated_capabilities, attr_name)
                        if isinstance(attr, type) and issubclass(attr, enum.Enum):
                            setattr(omni.capabilities, attr_name, attr)
                            logger.info(f"Injected {attr_name} into omni.capabilities")
                except Exception as import_error:
                    logger.error(f"Error importing generated module from {req_path}: {repr(import_error)}")
                    traceback.print_exc()
                finally:
                    sys.path.remove(tmpdirname)

        logger.info("Requirements generation and injection complete")
    except Exception as e:
        logger.error(f"Error generating missing requirements: {repr(e)}")
        traceback.print_exc()
        raise e


def _load_python_module(module_path: Path) -> None:
    """Load a python module from the specified path."""
    module_search_path = str(module_path.parent)
    module_name = module_path.stem
    try:
        if module_search_path not in sys.path:
            sys.path.append(module_search_path)
        logger.info(f"Loading module: '{module_name}' from {module_search_path}")
        importlib.import_module(module_name)
        logger.info(f"  '{module_name}' module loaded successfully.")
    except Exception as e:
        logger.error(f"Error loading module '{module_name}' from {module_search_path}. {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise e


def _load_and_register_feature(feature_path: Path) -> None:
    """Load a feature description from the given toml/json file, and register it in the validation library."""
    feature_data = _load_json_or_toml_file(feature_path)
    feature_id = feature_data.get("id")
    requirements = set()

    # Check that each requirement is registered
    missing_requirements = []
    for code in feature_data.get("requirements", []):
        if requirement := RequirementsRegistry().find_requirement(code):
            requirements.add(requirement)
        else:
            missing_requirements.append(code)
    if missing_requirements:
        logger.error(
            f"Skipping feature '{feature_id}' because it contains unregistered requirements: {missing_requirements}"
        )
        return

    # Ensure the file contains a valid feature definition
    if feature_id is None or len(requirements) == 0:
        logger.info(
            f"Skipping file in features path '{feature_path}' because it does not contain a valid feature definition."
        )
        return

    # Build and register the feature
    attributes = {
        "id": feature_id,
        "version": feature_data.get("version", ""),
        "path": feature_data.get("path", ""),
        "requirements": list(requirements),
    }
    logger.info(f"Registering feature '{attributes['id']}' version '{attributes['version']}' from {feature_path}")
    feature_class = type(feature_path.stem, (Capability,), attributes)
    CapabilityRegistry().add(feature_class())

    # find the other feature data that is not in the attributes
    custom_data = feature_data.copy()
    custom_data.pop("id")
    custom_data.pop("version")
    custom_data.pop("path")
    custom_data.pop("requirements")
    attributes["custom_data"] = custom_data

    # add the custom data to the feature class
    feature_class.custom_data = custom_data


def _load_and_register_profile(profile_path: Path) -> None:
    """Load the profile descriptions from the given toml/json file, and register them in the validation library."""
    for profile_name, profile_data in _load_json_or_toml_file(profile_path).items():
        if isinstance(profile_data, dict):
            # profile_data should contain version keys with dict values containing feature lists
            for version, version_data in profile_data.items():
                if isinstance(version_data, dict):
                    features = set()
                    # Check that each feature is registered
                    missing_features = []
                    for feature_dict in version_data.get("features", []):
                        if isinstance(feature_dict, dict):
                            feature_id = list(feature_dict.keys())[0]
                            feature_version = feature_dict[feature_id].get("version", None)
                            if feature_version is not None and (
                                feature := CapabilityRegistry().find(feature_id, feature_version)
                            ):
                                features.add(feature)
                            else:
                                missing_features.append(feature_dict)
                        else:
                            missing_features.append(feature_dict)
                    if missing_features:
                        logger.error(
                            f"Skipping profile '{profile_name}' version '{version}' because it contains unregistered features: {missing_features}"
                        )
                        continue
                    if not features:
                        logger.error(
                            f"Skipping profile '{profile_name}' version '{version}' because it has no valid features."
                        )
                        continue

                    # Build and register the profile
                    attributes = {
                        "id": profile_name,
                        "version": version,
                        "path": profile_path,
                        "capabilities": list(features),
                    }
                    logger.info(f"Registering profile '{profile_name}' version '{version}' from {profile_path}")
                    profile_class = type(profile_name, (Profile,), attributes)
                    ProfileRegistry().add_profile(profile_class())


def _load_json_or_toml_file(file_path: Path) -> dict:
    try:
        with open(file_path, "rb") as f:
            if file_path.suffix.lower() == ".json":
                return json.load(f)
            elif file_path.suffix.lower() == ".toml":
                return toml.load(f)
            else:
                logger.error(f"Unsupported file type: {file_path}")
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {repr(e)}")
    return {}
