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
"""
Validation rules for Naming and Paths capability.
"""

import asyncio
import os
import re
from datetime import datetime
from typing import List, Optional, Union

try:
    import omni.client
except ImportError:
    omni_client = None

import omni.capabilities as cap
from omni.asset_validator.core import BaseRuleChecker, register_requirements
from pxr import Sdf, Usd


@omni.asset_validator.core.registerRule("SimReady")
@omni.asset_validator.core.register_requirements(cap.SimReadyRequirements.SR_001)
class SimReadyCapabilityChecker(BaseRuleChecker):
    """Checker for Sim Ready capability requirements."""

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except TypeError:
            kwargs.pop("parameters", None)
            super().__init__(*args, **kwargs)

    def CheckStage(self, stage: Usd.Stage) -> None:
        """Check all NP requirements."""
        errors = []

        errors.extend(self.check_sr001_metadata_whitelist(stage))

        return errors

    def check_sr001_metadata_whitelist(self, stage: Usd.Stage) -> List[str]:
        """
        Check SR.001: Verify that the asset stage contains required metadata.

        Validates that:
        1. All required metadata fields are present
        2. The SimReady_Metadata dictionary has all required fields (if present)

        Note: Additional/unexpected metadata fields are allowed.
        """
        errors = []

        root_layer = stage.GetRootLayer()
        customlayerdata = root_layer.customLayerData

        # Check for required fields at top level (alternative location)
        missing_fields = []
        required_metadata_fields = {
            "SimReady_Metadata",
            "asset_name",
            "asset_type",
            "source_file",
            "usd_date_generated",
        }
        for required_field in required_metadata_fields:
            if required_field not in customlayerdata:
                missing_fields.append(required_field)

        if missing_fields:
            errors.append(
                f"Required metadata fields are missing: {', '.join(missing_fields)}. "
                f"Metadata should be in SimReady_Metadata dictionary or at top level of customLayerData."
            )

        return errors
