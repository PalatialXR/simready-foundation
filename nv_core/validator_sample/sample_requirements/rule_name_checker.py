import omni.capabilities as cap
from omni.asset_validator import (
    BaseRuleChecker,
    register_requirements,
    register_rule,
)
from pxr import Usd

@register_rule("Sample")
@register_requirements(cap.SampleRequirements.SAMP_001)
class SampleNameChecker(BaseRuleChecker):
    """
    The default prim must be named "World".
    """
    def CheckStage(self, stage: Usd.Stage):
        default_prim = stage.GetDefaultPrim()
        if not default_prim:
            self._AddFailedCheck("Stage has no default prim.", at=stage, requirement=cap.SampleRequirements.SAMP_001)
            return
        if default_prim.GetName() != "World":
            self._AddFailedCheck("Root prim must be named 'World'.", at=default_prim, requirement=cap.SampleRequirements.SAMP_001)
            return
