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
__all__ = ["APIConflictChecker"]

import omni.physx.bindings._physx as pxb
from omni.asset_validator.core import BaseRuleChecker, registerRule
from pxr import Usd, UsdPhysics


@registerRule("Omni:Physx")
class APIConflictChecker(BaseRuleChecker):
    __doc__ = """
    Check if applied RigidBodyAPI, CollisionAPI, and ArticulationRootAPI have conflicting APIs in the hierarchy.
    """

    RB_API_CONFLICT_CODE = "APIConflictChecker:APIConflict"
    COLLISION_API_CONFLICT_CODE = "APIConflictChecker:CollisionAPIConflict"
    ARTICULATION_ROOT_API_CONFLICT_CODE = "APIConflictChecker:ArticulationRootAPIConflict"

    def _check_api_conflict_on_prim(self, prim: Usd.Prim) -> None:
        """Validate mass configuration for individual prims"""

        if UsdPhysics.RigidBodyAPI(prim):
            fail, where = pxb.hasconflictingapis_RigidBodyAPI_WRet(prim, True, False)
            print(prim, fail, where)
            if fail:
                self._AddFailedCheck(
                    message=f"RigidBodyAPI has conflicting API(s) at {where.GetPath()}",
                    at=prim,
                    code=self.RB_API_CONFLICT_CODE,
                )

        if UsdPhysics.CollisionAPI(prim):
            fail, where = pxb.hasconflictingapis_CollisionAPI_WRet(prim, False, False)
            if fail:
                self._AddFailedCheck(
                    message=f"CollisionAPI has conflicting API(s) at {where.GetPath()}",
                    at=prim,
                    code=self.COLLISION_API_CONFLICT_CODE,
                )

        if UsdPhysics.ArticulationRootAPI(prim):
            fail, where = pxb.hasconflictingapis_ArticulationRoot_WRet(prim, True, False)
            if fail:
                self._AddFailedCheck(
                    message=f"ArticulationRootAPI has conflicting API(s) at {where.GetPath()}",
                    at=prim,
                    code=self.ARTICULATION_ROOT_API_CONFLICT_CODE,
                )

    def CheckPrim(self, prim: Usd.Prim):
        self._check_api_conflict_on_prim(prim)
