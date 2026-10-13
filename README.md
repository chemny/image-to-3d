# Image to 3D

English | [中文](./README.zh.md)

## Overview

Image to 3D is an Agent Skill for building editable Three.js models from object reference images. It helps designers and developers turn visual observations into a model specification, construct geometry, compare renders with references, and package the resulting assets.

It works with vehicles, toys and other objects. The Agent interprets images and authors the shape; the tools build and check that specification. Hidden surfaces remain design inferences. High-fidelity reconstruction and one-pass completion are not guaranteed.

## Preview

![Model rendered with Image to 3D](./assets/preview.png)

Example model rendered in Three.js.

## Features

| Capability | What it helps you do |
|---|---|
| Reference-based modeling | Build a Three.js scene from a traceable component, material and camera specification. |
| Reference preparation | Plan additional views and detail images, distinguish observations from inferred designs, and record approvals. |
| Controlled local shapes | Generate explicit meshes from section lofts or outlined thick forms, with reproducible parameters. |
| Visual comparison | Compare fixed-camera renders, silhouettes and geometry-bound landmarks without silently warping references. |
| Editable parts | Select, recolor, replace, separate and restore components when the asset contract supports those operations. |
| Asset delivery | Export GLB and preserve sources and review evidence; optionally check actual Blender imports. |

## Installation

### Requirements

The core runs locally. Additional image generation and browser or Blender checks require tools available to your Agent.

| Item | Requirement |
|---|---|
| Agent client | Codex on macOS. |
| Core runtime | Python 3.10 or later with image-processing support. |
| Preview and capture | A modern browser; automated capture also needs Node.js and Playwright. |
| Optional features | Host image generation for supplemental views; Blender for import verification. |

The existing vehicle-page adapter additionally requires the separate vehicle-configurator skill; generic models do not.

### Quick Installation

Ask your Agent:

> Install this Skill: https://github.com/chemny/image-to-3d. Check the basic environment, prepare missing core requirements, then install and verify that the Skill can be loaded. Set up optional features when I need them.

The Agent should report what was verified and any remaining setup, rather than treating a file copy as successful operation.

## Quick Start

Attach a clear object image and ask:

> Use Image to 3D to build an editable model of this object. First identify the main shapes and missing views, then create a first model and show me where it still differs from the reference.

You receive a local model preview and its specification and review files. Inspect the original camera angle and at least one depth-revealing angle before accepting the result.

## Usage Examples

### Build a toy from a reference

> Turn this toy image into a model. Keep its recognizable silhouette and separate the parts I may want to recolor. Ask me before choosing a new hidden-side design.

### Repair a local shape

> The wing is too flat. Keep the camera, materials and other parts unchanged, rebuild its thickness and root, and compare the original and side views.

### Prepare reusable assets

> Prepare this reviewed model for Three.js and GLB. Check part selection, color changes and disassembly. If Blender is available, verify the import too.

## How It Works

1. Analyze the original and prepare a reference set, including explicit uncertainty and generated-design approval.
2. Author the Spec: components, geometry, materials, cameras, relationships and real observation bindings.
3. Build local forms with `form_construction.py`; `construction_plan.py` connects recipes to actual meshes and protected parts.
4. Use `project.py` to build, capture, compare and review. `reference_set.py` checks reference records; `anchor_evidence.py` projects real geometry; `workflow.py` enforces evidence identity and stage requirements.
5. Use the asset checks and exchange tools to verify supported interactions and export. A diagnostic model is not an accepted delivery.

The bundled tools validate declared data and geometry. They do not automatically judge whether every picture or shape is correct. Scope, source evidence and human visual review remain necessary. Parallel Agents can split work under the collaboration contract when the host supports them.

## Repository Structure

```text
SKILL.md       Agent entry point
agents/        Client display metadata
scripts/       Construction, project, review and exchange tools
references/    Modeling, reference and delivery standards
assets/        Three.js runtime, license and preview
examples/      Synthetic editable-asset examples
tests/         Software and optional runtime regression checks
```

Start with [the execution guide](references/unified-execution.md), [reference preparation](references/reference-set-standard.md), [local construction](references/form-construction.md), and [asset exchange](references/asset-exchange.md). The examples test functionality; they are not photo-reconstruction benchmarks.


Additional contracts: [legacy interface notes](references/implementation-contract.md) and [Spec and evidence](references/spec-and-evidence.md).

## License

Project code is distributed under the [MIT License](LICENSE). Bundled Three.js retains its [own MIT notice](assets/vendor/LICENSE). Reference images and user-supplied assets require appropriate rights and are not relicensed by the code license. Rule provenance is recorded in [the source mapping](references/production-rule-sources.md).

## About Me

Maintained by [chemny](https://github.com/chemny). Report reproducible issues through [GitHub Issues](https://github.com/chemny/image-to-3d/issues).
