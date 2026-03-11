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
__all__ = ["BackwardCompatibilityChecker"]

from omni.asset_validator.core import BaseRuleChecker, Suggestion, registerRule
from pxr import Usd

from .. import get_physx_asset_validator_interface
from .utils import check_timeline_playing, get_stage_id


@registerRule("Omni:Physx")
class BackwardCompatibilityChecker(BaseRuleChecker):
    __doc__ = """
    Check all physics backward compatibility rules for the given stage.
    """

    def CheckStage(self, stage: Usd.Stage):
        if check_timeline_playing(self, stage):
            return

        validator = get_physx_asset_validator_interface()
        if validator.backward_compatibility_check(get_stage_id(stage)):
            log = validator.get_backward_compatibility_log()

            self._AddFailedCheck(
                message=f"{log}",
                at=stage.GetPrimAtPath("/"),
                suggestion=Suggestion(
                    message="Do backward compatibility fixes",
                    callable=self.run_fix,
                    at=[stage.GetRootLayer()],
                ),
            )

    def run_fix(self, stage: Usd.Stage, _: Usd.Prim):
        validator = get_physx_asset_validator_interface()
        validator.run_backward_compatibility_check(get_stage_id(stage))
