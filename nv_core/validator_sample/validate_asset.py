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
import argparse
import copy
import enum
import importlib
import json
import logging
import tomllib as toml
import traceback
from pathlib import Path
from typing import Optional, Union

import omni.capabilities
from loading.validation_loader import load_validation_implementation
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
from pxr import Usd

logger = logging.getLogger("Validation Sample")


def validate_asset_with_profile(
    input: Union[Usd.Stage, str], profile_id: str, profile_version: Optional[str] = None
) -> list[Issue]:
    """Validate the asset with the given profile"""
    stage = input if isinstance(input, Usd.Stage) else Usd.Stage.Open(input)

    profile = ProfileRegistry().find_profile(profile_id, profile_version)
    if not profile:
        return [
            Issue(
                f"Profile '{profile_id}' with version '{profile_version}' not found among registered profiles.",
                severity=IssueSeverity.ERROR,
                at=stage,
            )
        ]

    # Enable the validation rules for the profile
    engine = ValidationEngine(init_rules=False, variants=False)
    for capability in sorted(profile.capabilities, key=lambda c: c.id):
        logger.info(f"Validation feature: {capability.id} ({capability.version})")

        # copy the capability with all dependent requirements
        capability_copy, _ = _copy_capability_with_dependencies(capability, log=True)

        sorted_requirements = sorted(capability_copy.requirements, key=lambda r: r.code)
        for requirement in sorted_requirements:
            if rule := RequirementsRegistry().get_validator(requirement):
                logger.info(f"  Requirement: {requirement.code}: Rule: {rule}")
            else:
                logger.error(f"  Requirement: {requirement.code}: Rule not found")
        engine.enable_capability(capability_copy)

    # Validate!
    results = engine.validate(stage)
    logger.info("Asset validation complete.")

    failure_issues = []
    for issue in results.issues().filter_by(lambda i: i.severity in (IssueSeverity.ERROR, IssueSeverity.FAILURE)):
        failure_issues.append(issue)
    return failure_issues


def build_features_validation_summary(
    validation_results: list[Issue], profile_id: str, profile_version: str, include_failed_requirements: bool = True
) -> dict[str, dict]:
    """Build the features summary dictionary from the validation results"""
    # Collect failed requirements
    issues_missing_requirement = set()
    failed_requirements = set()
    for issue in validation_results:
        if issue.requirement is None:
            if issue.rule is not None:
                logger.warning(f"Rule {issue.rule} did not specify a requirement for an issue.")
                issues_missing_requirement.add(issue.rule)
        else:
            failed_requirements.add(issue.requirement.code)

    try:
        profile = ProfileRegistry().find_profile(profile_id, profile_version)
        if profile is None:
            logger.warning(f"Profile {profile_id} not found.")
            return {}
        # Get a copy of features with all dependent requirements to avoid mutating original data
        features = []
        for capability in profile.capabilities:
            feature_copy, dependencies = _copy_capability_with_dependencies(capability)
            features.append(feature_copy)
            # Also add dependencies that are not already in features
            for dep in dependencies:
                if all(not (dep.id == f.id and dep.version == f.version) for f in features):
                    features.append(dep)

        for feature in features:
            for requirement in feature.requirements:
                # try to match requirementless issues with the requirements associated with its rule
                if RequirementsRegistry().get_validator(requirement) in issues_missing_requirement:
                    failed_requirements.add(requirement.code)
        # Build features summary
        features_summary = {}
        for feature in features:
            feature_id = feature.id
            feature_requirements = feature.requirements
            failed_feature_requirements = [req.code for req in feature_requirements if req.code in failed_requirements]
            features_summary[feature_id] = {
                "version": feature.version,
                "dependencies": str(feature.custom_data.get("dependencies", [])),
                "passed": not failed_feature_requirements,
            }
            if failed_feature_requirements:
                logger.info(f"Failed requirements {failed_feature_requirements} preclude feature {feature_id}.")
            if failed_feature_requirements and include_failed_requirements:
                features_summary[feature_id]["failing requirements"] = str(failed_feature_requirements)
        return features_summary
    except AttributeError as e:
        logger.warning(f"Unable to get features from the config: {e}")
        return {}


def _copy_capability_with_dependencies(capability: Capability, log: bool = False) -> tuple[Capability, set[Capability]]:
    """Copy a capability and collect all its dependent requirements recursively.

    This function creates a deep copy of the capability and recursively adds
    requirements from all feature dependencies without mutating the original data.

    Args:
        capability: The capability to copy

    Returns:
        A copy of the capability with all dependent requirements included
    """
    # copy the capability
    capability_copy = copy.copy(capability)
    feature_depency_set = set()
    # add the requirements of the feature dependencies
    if capability_copy.custom_data:
        # get the dependencies from the custom data, make sure its a copy
        feature_dependencies = list(capability_copy.custom_data.get("dependencies", []))
        processed_dependencies = set()  # Track processed dependencies to avoid infinite loops

        while feature_dependencies:
            current_dependency = feature_dependencies.pop(0)

            # Handle dependency format: {"FET_001": {"version": "0.1.0"}} (version is optional)
            try:
                dependency_id = list(current_dependency.keys())[0]
                dependency_version = list(current_dependency.values())[0].get("version", "")
            except Exception as e:
                logger.error(f"Error extracting dependency_id and version from dependency {current_dependency}: {e}")
                continue

            dependency_key = f"{dependency_id}_{dependency_version}"
            if dependency_key in processed_dependencies:
                continue

            processed_dependencies.add(dependency_key)

            feature_dependency = CapabilityRegistry().find(dependency_id, dependency_version)

            if feature_dependency:
                if log:
                    logger.info(f"  Feature dependency: {feature_dependency.id} ({feature_dependency.version})")
                feature_depency_set.add(feature_dependency)
                capability_copy.requirements.extend(feature_dependency.requirements)

                # add any new dependencies to the queue, already processed dependencies are skipped
                if feature_dependency.custom_data:
                    dependencies = feature_dependency.custom_data.get("dependencies", [])
                    for dependency in dependencies:
                        feature_dependencies.append(dependency)

            elif log:
                logger.error(f"  Feature dependency not found: {dependency_id}_{dependency_version}")
    # dedupe the requirements before returning
    capability_copy.requirements = list(set(capability_copy.requirements))

    return capability_copy, feature_depency_set


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate an asset against the sample profile.")
    parser.add_argument("asset_path", help="Path to the USD asset to validate.")
    args = parser.parse_args()
    asset_path = Path(args.asset_path)
    if not asset_path.is_file():
        parser.error(f"File does not exist: '{asset_path}'")
    if not asset_path.suffix.lower().startswith(".usd"):
        parser.error(f"File must be a USD file: '{asset_path}'")

    load_validation_implementation(
        rules_and_requirements_paths=[Path(__file__).parent / "sample_requirements"],
        features_paths=[Path(__file__).parent / "sample_features"],
        profiles_paths=[Path(__file__).parent / "sample_profiles" / "profiles.toml"],
    )
    for k, v in RequirementsRegistry().items():
        logger.info(f"Requirement: {k}: {v}")

    issues = validate_asset_with_profile(str(asset_path), "Sample-Profile", "1.0.0")
    summary = build_features_validation_summary(issues, "Sample-Profile", "1.0.0", include_failed_requirements=True)
    logger.info("Validation summary:")
    for feature, data in summary.items():
        logger.info(f"Feature: {feature}")
        logger.info(f"  Version: {data['version']}")
        logger.info(f"  Dependencies: {data['dependencies']}")
        logger.info(f"  Passed: {data['passed']}")
        if failed_reqs := data.get("failing requirements"):
            logger.info(f"  Failing requirements: {failed_reqs}")
