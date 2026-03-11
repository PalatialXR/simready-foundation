# root-joint-pinned

| Code     | RC.009 |
|----------|--------|
| Validator| CheckStage |
| Compatibility | {compatibility}`Isaac Sim` |
| Tags     | {tag}`essential` |

## Summary

The root joint (the first target of `isaac:physics:robotJoints`) must be pinned for robot types that require a fixed base (e.g. Manipulator, End Effector) and must not be pinned for other robot types.

## Description

The root joint is the first joint in the `isaac:physics:robotJoints` relationship. A joint is considered pinned when one of its two bodies is not a rigid body (e.g. body is the world or a non-physics prim). For types such as **Manipulator** and **End Effector**, the root joint must be pinned (fixed base). For all other valid robot types, the root joint must not be pinned.

## Why is it required?

* To match simulation expectations for fixed-base vs mobile robots
* To prevent incorrect physics behavior (e.g. floating manipulators or incorrectly fixed mobile bases)
* To keep asset configuration consistent with the declared robot type

## Examples

```usd
# Valid: Manipulator with pinned root (body0 or body1 is non-rigid / world)
over "Robot" (
    prepend apiSchemas = ["IsaacRobotAPI"]
)
{
    token isaac:robotType = "Manipulator"
    rel isaac:physics:robotJoints = [ </joints/root>, </joints/joint_1> ]
    rel isaac:physics:robotLinks = [ </links/base>, </links/link_1> ]
}
# Root joint: body0 = world (or non-rigid), body1 = base link -> pinned

# Invalid: Manipulator with root joint not pinned (both bodies are rigid)
# Root joint must have one body that is world or non-rigid for Manipulator/End Effector

# Invalid: Non-manipulator type with root joint pinned
# For robot types other than Manipulator and End Effector, root must not be pinned
```

## How to comply

* Ensure the default prim has `isaac:robotType` and `isaac:physics:robotJoints` (see [robot-type](robot-type.md) and [robot-schema](robot-schema.md)).
* For **Manipulator** and **End Effector**: make the root joint pinned by having one of its `physics:body0` or `physics:body1` targets be the world or a prim without `RigidBodyAPI`.
* For all other robot types: ensure both bodies of the root joint are rigid bodies (root joint not pinned).

## Related requirements

- [robot-type](robot-type.md)
- [robot-schema](robot-schema.md)

## For More Information

* [Isaac Sim Robot API](https://docs.omniverse.nvidia.com/isaacsim/latest/)
* [USD Physics Joints](https://openusd.org/dev/api/usd_physics_page_front.html)
