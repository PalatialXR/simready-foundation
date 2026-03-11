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
"""Feature adapter to convert PhysX robotic assets to Isaac Sim format.

This adapter uses the AssetStructureManager to apply the robot schema
transformation rules to convert assets to the Isaac Sim structure.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

# ============================================================================
# Module aliasing: Register local modules under 'isaacsim.asset.transformer'
# This allows copied code using 'from isaacsim.asset.transformer import ...'
# to resolve to our local .asset.transformer package without modification.
# ============================================================================
from .asset import transformer as _local_transformer

# Create stub parent modules if they don't exist
if "isaacsim" not in sys.modules:
    sys.modules["isaacsim"] = ModuleType("isaacsim")
if "isaacsim.asset" not in sys.modules:
    _isaacsim_asset = ModuleType("isaacsim.asset")
    sys.modules["isaacsim.asset"] = _isaacsim_asset
    sys.modules["isaacsim"].asset = _isaacsim_asset

# Register the local transformer module under the expected path
sys.modules["isaacsim.asset.transformer"] = _local_transformer
sys.modules["isaacsim.asset"].transformer = _local_transformer
# ============================================================================

from omni.cip.configurable.feature_adapter import feature_adapter
from pxr import Kind, Sdf, Usd

# Import from local asset transformer package
from .asset.transformer import AssetStructureManager, RuleProfile

# Rule registration
from .asset.transformer.manager import RuleRegistry
from .asset.transformer.organizer.rules.flatten import FlattenRule
from .asset.transformer.organizer.rules.geometries import GeometriesRoutingRule
from .asset.transformer.organizer.rules.interface import InterfaceConnectionRule
from .asset.transformer.organizer.rules.materials import MaterialsRoutingRule
from .asset.transformer.organizer.rules.prims import PrimRoutingRule
from .asset.transformer.organizer.rules.properties import PropertyRoutingRule
from .asset.transformer.organizer.rules.robot_schema import RobotSchemaRule
from .asset.transformer.organizer.rules.schemas import SchemaRoutingRule
from .asset.transformer.organizer.rules.variants import VariantRoutingRule

logger = logging.getLogger(__name__)

# Path to the profile JSON relative to this module
_PROFILE_JSON_PATH = Path(__file__).parent / "asset" / "transformer" / "data" / "organize_routing.json"


@feature_adapter(
    name="neutral_composition_to_isaacsim",
    input_feature_id="FET001_BASE_NEUTRAL",
    input_feature_version="0.1.0",
    output_feature_id="FET100_BASE_ISAACSIM",
    output_feature_version="0.1.0",
    priority=1000,  # low priority, so it runs last
)
def modify_stage(input_stage: Usd.Stage, output_stage: Usd.Stage):
    """Convert a PhysX robotic asset to Isaac Sim format.

    Uses the AssetStructureManager to apply robot schema transformation rules.
    The input stage is saved to a temporary file, processed by the manager,
    and the results are copied back to the output stage.

    Args:
        input_stage: The source USD stage containing the PhysX asset.
        output_stage: The destination USD stage for the Isaac Sim asset.

    Raises:
        ValueError: If the input stage has no default prim.
        RuntimeError: If the asset transformation fails.
        FileNotFoundError: If the profile JSON file is not found.
    """

    # Register rules under the isaacsim.* paths expected by the JSON profile
    # (The actual module paths differ, but the JSON uses isaacsim.* paths)
    registry = RuleRegistry()
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.flatten.FlattenRule"] = FlattenRule
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.geometries.GeometriesRoutingRule"] = (
        GeometriesRoutingRule
    )
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.interface.InterfaceConnectionRule"] = (
        InterfaceConnectionRule
    )
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.materials.MaterialsRoutingRule"] = (
        MaterialsRoutingRule
    )
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.prims.PrimRoutingRule"] = PrimRoutingRule
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.properties.PropertyRoutingRule"] = (
        PropertyRoutingRule
    )
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.robot_schema.RobotSchemaRule"] = RobotSchemaRule
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.schemas.SchemaRoutingRule"] = SchemaRoutingRule
    registry._type_to_cls["isaacsim.asset.transformer.organizer.rules.variants.VariantRoutingRule"] = VariantRoutingRule

    # Validate input stage has a default prim
    input_default_prim = input_stage.GetDefaultPrim()
    if not input_default_prim:
        raise ValueError("Input stage must have a default prim")

    default_prim_name = input_default_prim.GetName()

    # Determine output paths
    output_layer = output_stage.GetRootLayer()
    output_path = Path(output_layer.identifier)
    package_root = str(output_path.parent)
    asset_name = output_path.stem

    # Validate profile JSON exists
    if not _PROFILE_JSON_PATH.exists():
        raise FileNotFoundError(f"Profile JSON not found: {_PROFILE_JSON_PATH}")

    # Save input stage to a temporary file for the manager
    with tempfile.TemporaryDirectory() as temp_dir:

        temp_input_path = os.path.join(temp_dir, "input_stage.usda")
        input_stage.GetRootLayer().Export(temp_input_path)

        # Load the profile from JSON
        with open(_PROFILE_JSON_PATH, "r", encoding="utf-8") as f:
            profile = RuleProfile.from_json(f.read())

        # Configure the profile with asset-specific settings
        profile.interface_asset_name = asset_name

        # Create manager (rules already registered in the singleton registry above)
        manager = AssetStructureManager()

        # Run the transformation
        logger.info(f"Running AssetStructureManager for asset: {asset_name}")
        report = manager.run(
            input_stage_path=temp_input_path.replace("\\", "/"), profile=profile, package_root=package_root
        )

        # Check for errors in rule execution
        for result in report.results:
            if not result.success:
                error_msg = f"Rule '{result.rule.name}' failed: {result.error}"
                logger.error(error_msg)
                # raise RuntimeError(f"Asset transformation failed: {result.error}")
            else:
                # Log successful rule operations
                for log_entry in result.log:
                    logger.debug(f"[{result.rule.name}] {log_entry.get('message', '')}")

            # delete the default prim
            # Sdf.RemovePrim(output_stage.GetRootLayer(), "/defaultPrim")

            ## Copy the transformed results back to the output stage
            # _compose_output_stage(
            #    output_stage=output_stage,
            #    package_root=package_root,
            #    default_prim_name=default_prim_name,
            #    asset_name=asset_name,
            # )

    logger.info(f"Successfully converted asset to Isaac Sim format: {asset_name}")


def _compose_output_stage(
    output_stage: Usd.Stage,
    package_root: str,
    default_prim_name: str,
    asset_name: str,
) -> None:
    """Compose the transformed results into the output stage.

    The AssetStructureManager creates:
    - {package_root}/payloads/base.usd - copy of input with robot schema sublayer
    - {package_root}/payloads/robot.usda - robot schema opinions

    This function copies the content from base.usd to the output stage and
    sets up the proper layer composition.

    Args:
        output_stage: The destination USD stage.
        package_root: Root directory where payloads were created.
        default_prim_name: Name of the default prim in the input stage.
        asset_name: Name to use for the output asset.
    """
    payloads_dir = os.path.join(package_root, "payloads")
    base_path = os.path.join(payloads_dir, "base.usd")
    robot_path = os.path.join(payloads_dir, "robot.usda")

    output_layer = output_stage.GetRootLayer()

    # Open the base layer created by the manager
    if not os.path.exists(base_path):
        raise RuntimeError(f"Base payload not found: {base_path}")

    base_layer = Sdf.Layer.FindOrOpen(base_path)
    if not base_layer:
        raise RuntimeError(f"Failed to open base layer: {base_path}")

    # Copy the default prim content from base to output
    source_prim_path = f"/{default_prim_name}"
    target_prim_path = f"/{asset_name}"

    # Ensure we have content to copy
    if not base_layer.GetPrimAtPath(source_prim_path):
        raise RuntimeError(f"Default prim not found in base layer: {source_prim_path}")

    # Copy the prim hierarchy using Sdf.CopySpec
    if source_prim_path == target_prim_path:
        # Same path - direct copy
        Sdf.CopySpec(base_layer, source_prim_path, output_layer, target_prim_path)
    else:
        # Different paths - copy and potentially remap
        Sdf.CopySpec(base_layer, source_prim_path, output_layer, target_prim_path)

    # Set the default prim on output stage
    output_prim = output_stage.GetPrimAtPath(target_prim_path)
    if output_prim:
        output_stage.SetDefaultPrim(output_prim)

        # Set the kind to component for proper USD composition
        model_api = Usd.ModelAPI(output_prim)
        model_api.SetKind(Kind.Tokens.component)
    else:
        logger.warning(f"Could not find output prim at: {target_prim_path}")

    # Copy stage metadata from base layer
    _copy_stage_metadata(base_layer, output_layer)

    # If robot schema layer exists, add it as a sublayer to output
    if os.path.exists(robot_path):
        robot_rel_path = os.path.relpath(robot_path, os.path.dirname(output_layer.identifier))
        if robot_rel_path not in output_layer.subLayerPaths:
            output_layer.subLayerPaths.append(robot_rel_path)
            logger.debug(f"Added robot schema sublayer: {robot_rel_path}")

    # Save the output stage
    output_stage.Save()


def _copy_stage_metadata(source_layer: Sdf.Layer, target_layer: Sdf.Layer) -> None:
    """Copy stage-level metadata from source layer to target layer.

    Copies metersPerUnit, upAxis, timeCodesPerSecond, and other layer metadata.

    Args:
        source_layer: The source layer to copy metadata from.
        target_layer: The target layer to copy metadata to.
    """
    # Keys to skip (handled separately or should not be copied)
    skip_keys = frozenset(("defaultPrim", "subLayers", "primChildren"))

    source_pseudo_root = source_layer.pseudoRoot
    target_pseudo_root = target_layer.pseudoRoot

    for key in source_pseudo_root.ListInfoKeys():
        if key in skip_keys:
            continue
        try:
            value = source_pseudo_root.GetInfo(key)
            if value is not None:
                target_pseudo_root.SetInfo(key, value)
        except Exception as e:
            logger.debug(f"Could not copy metadata key '{key}': {e}")
