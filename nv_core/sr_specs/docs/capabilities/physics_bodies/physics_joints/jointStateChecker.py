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

__all__ = ["JointStateChecker"]

import asyncio

import carb
import omni.physx.bindings._physx as physx_bindings
from omni.asset_validator.core import BaseRuleChecker, Suggestion, registerRule
from omni.asset_validator.core.complianceChecker import is_omni_path
from omni.physx import get_physx_interface, get_physx_simulation_interface
from pxr import PhysicsSchemaTools, Usd, UsdPhysics, UsdUtils

from .. import get_physx_asset_validator_interface

MAX_NUMBER_OF_FIX_ITERATIONS = 5  # How many times should the fix be applied until validation passes
MARSHAL_TO_MAIN_THREAD = True  # Must run on main thread because it uses omni.physx runtime that is not thread safe


@registerRule("Omni:Physx")
class JointStateChecker(BaseRuleChecker):

    def fix_articulation_joint_state(self, stage: Usd.Stage, location: Usd.Prim) -> None:
        # As we can't know what the user could have been doing between the analysis and pressing
        # the fix button, to play safe we must reset simulation and re-force load physics.
        # This is going to be slow if there are many prims in the same stage, but there is no
        # way of enforcing that for example, between "Analyze" and "Fix selected" the user has
        # not been going in simulation mode and stopped (that will release all needed physx objects)
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        if stage_id == -1:
            stage_id = UsdUtils.StageCache.Get().Insert(stage).ToLongInt()

        get_physx_simulation_interface().attach_stage(stage_id)
        get_physx_interface().reset_simulation()
        get_physx_interface().force_load_physics_from_usd()
        # We don't want to reset on stop in order to persist the changes
        settings = carb.settings.acquire_settings_interface()
        saved_reset_on_stop = settings.get_as_bool(physx_bindings.SETTING_RESET_ON_STOP)
        settings.set(physx_bindings.SETTING_RESET_ON_STOP, False)

        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        prim_id = PhysicsSchemaTools.sdfPathToInt(location.GetPath())
        iterations = 0
        validator = get_physx_asset_validator_interface()
        while True:
            validator.joint_state_apply_fix(stage_id, prim_id)
            iterations += 1
            if validator.joint_state_is_valid(stage_id, prim_id):
                break
            if iterations >= MAX_NUMBER_OF_FIX_ITERATIONS:
                carb.log_error("Joint State cannot be fixed. Simulated articulation is not stable.")
                settings.set(physx_bindings.SETTING_RESET_ON_STOP, True)
                break

        get_physx_interface().reset_simulation()
        get_physx_simulation_interface().detach_stage()
        settings.set(physx_bindings.SETTING_RESET_ON_STOP, saved_reset_on_stop)

    def CheckStage(self, stage: Usd.Stage):
        try:
            asyncio.get_event_loop()
            is_on_main_thread = True
        except Exception as e:
            is_on_main_thread = False
        if not is_on_main_thread and MARSHAL_TO_MAIN_THREAD:
            from omni.kit.async_engine import run_coroutine

            result = run_coroutine(self._async_check_stage(stage))
            import time

            try:
                while not result.done():
                    time.sleep(0.5)
            except Exception as e:
                print(e)
        else:
            self._internal_check_stage(stage)

    async def _async_check_stage(self, stage: Usd.Stage):
        self._internal_check_stage(stage)

    def _internal_check_stage(self, stage: Usd.Stage):
        if MARSHAL_TO_MAIN_THREAD:
            try:
                import asyncio

                asyncio.get_event_loop()
            except Exception:
                carb.log_error("CheckStage can only be run on main asyncio thread")
                return
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        if stage_id == -1:
            stage_id = UsdUtils.StageCache.Get().Insert(stage).ToLongInt()

        settings = carb.settings.acquire_settings_interface()
        # NOTE: CheckStage is invoked on an asyncio thread, so it's important avoiding writing to USD
        saved_update_to_usd = settings.get(physx_bindings.SETTING_UPDATE_TO_USD)
        settings.set(physx_bindings.SETTING_UPDATE_TO_USD, False)

        get_physx_simulation_interface().attach_stage(stage_id)
        get_physx_interface().reset_simulation()
        get_physx_interface().force_load_physics_from_usd()

        if stage.GetDefaultPrim():
            # Traverse the prims under the default prim
            traversal = iter(
                Usd.PrimRange(
                    stage.GetDefaultPrim(),
                    Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate),
                )
            )
        else:
            # No default prim, so traverse all prims
            traversal = iter(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))

        # TODO: Maybe on a large stage it could be useful trying usdrt
        for prim in traversal:
            if is_omni_path(prim.GetPath()):
                traversal.PruneChildren()
                continue
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                prim_path = str(prim.GetPath())
                prim_id = PhysicsSchemaTools.sdfPathToInt(prim.GetPath())
                if not get_physx_asset_validator_interface().joint_state_is_valid(stage_id, prim_id):
                    self._AddFailedCheck(
                        message=f'Joint State for "{prim_path}" is not coherent with transforms of rigid bodies belonging to the articulation',
                        at=prim,
                        suggestion=Suggestion(
                            message="Change XForms to match Joint State",
                            callable=self.fix_articulation_joint_state,
                            at=[stage.GetRootLayer()],
                        ),
                    )
                traversal.PruneChildren()  # Do not traverse childrens of articulation root
                continue

        get_physx_interface().reset_simulation()
        get_physx_simulation_interface().detach_stage()
        settings.set(physx_bindings.SETTING_UPDATE_TO_USD, saved_update_to_usd)
