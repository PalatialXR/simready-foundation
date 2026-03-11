# Feature: `Isaac Sim Composition`

## Description

The Isaac Sim Composition feature organizes files and prims in a specific way meant for performance in Isaac Sim.

## Specification

This feature is based on the [Isaac Sim Asset specification](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/robot_setup/asset_structure.html).

## Isaac Sim Format

### Version 0.1.0
<details>
<summary><strong>Details</strong></summary>

| **Property**            | **Value**         |
|-------------------------|-------------------|
|Internal ID              | `FET100_BASE_ISAACSIM`|

#### Used in Profiles

This version is used in the following profiles:

- **[Prop-Robotics-Isaac](../profiles/prop-robotics-isaac.md)** (v1.0.0)
- **[Robot-Body-Isaac](../profiles/robot-body-isaac.md)** (v1.0.0)

#### Requirements 
* Capability: [Isaac_Sim](../capabilities/isaac_sim/isaac_sim.md)
    * Requirements
        * [IsaacSim-Composition](../capabilities/isaac_sim/composition/requirements/composition.md)
            * ISA.001 | version 0.1.0
            * [Rule | Implementation](../capabilities/isaac_sim/composition/validation.py)

#### Pipelines Supported for this Feature
Source file type:
* .usd
  * Via CIP.
  * Convert from [FET001_BASE](./FET_001-minimal.md)

#### Test Process
* None