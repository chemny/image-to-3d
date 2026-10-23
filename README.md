# Image to 3D

English | [中文](./README.zh.md)

## Overview

Image to 3D is an Agent Skill for building editable Three.js models from object reference images. It helps designers and developers turn visual observations into a model specification, construct geometry, compare renders with references, and package the resulting assets.

It works with vehicles, toys and other objects. The Agent interprets images and authors the shape; the tools build and check that specification. Hidden surfaces remain design inferences. High-fidelity reconstruction and one-pass completion are not guaranteed.

## Preview

![AI-retouched exhibition showcase: full-size SUV, electric SUV, sports car, cloth doll, teapot and toy chick](./assets/preview-six-models-polished.png)

AI-retouched exhibition illustration of six models, also used on the personal website; it is not an unedited runtime screenshot. An [earlier unretouched render](assets/preview.png) is also available.

## Features

| Capability | What it helps you do |
|---|---|
| Reference-based modeling | Build a Three.js scene from a traceable component, material and camera specification. |
| Reference preparation | Plan additional views and detail images, distinguish observations from inferred designs, and record approvals. |
| Controlled shapes and continuous surfaces | Build section lofts, rolled edges and transition patches; check actual mesh seams, profile turns and curvature direction changes. |
| Visual comparison | Compare fixed-camera renders, silhouettes and geometry-bound landmarks without silently warping references. |
| Editable parts | Select, recolor, replace, separate and restore components when the asset contract supports those operations. |
| Defect diagnosis and mounting checks | Separate geometry, normals and appearance issues; sample actual mounting roots against the intended host surface. |
| Version continuity | Distinguish the model currently displayed from accepted samples, track inherited work, and verify integration evidence. |
| Lightweight delivery | Load full geometry once, deduplicate resources and losslessly compress display data; report asset budgets without automatic decimation. |
| Asset delivery | Export GLB and preserve sources and review evidence; optionally check actual Blender imports. |

Version 0.13.2 includes the vehicle module described below and retains [version lifecycle management](references/version-lifecycle.md): dependency-aware cleanup previews, recoverable quarantine, explicit entry retirement and separately approved permanent deletion. [Runtime guards](references/runtime-guards.md) check recorded temporal stability, normalization and world anchors, declared release dependencies, and conflict-safe scoped rollback previews. These tools do not automatically capture a browser, discover every dependency, modify a registry or publish.

The local macOS regression suite passed 782 tests, including the vehicle-module migration checks and 36 runtime-guard tests; this is software validation, not a visual reconstruction benchmark or fresh Windows/Claude Code certification.

## Installation

Start with **install.command (macOS)** or **install.cmd (Windows)**. They diagnose first, ask before installing missing required dependencies, then run the existing first-use check. Add `--check-only` for read-only diagnosis. No optional tools are installed. Windows launcher/installation still lacks real-machine validation; see the [setup guide](references/installation.md).

| Capability | Requirements |
|---|---|
| Core modeling, checks and GLB export | Python 3.10+, Pillow >=9, NumPy >=1.24 |
| Manual model viewing | A compatible browser and local HTTP server |
| Optional automatic screenshots/browser tests | Node.js >=18, Playwright and a compatible browser |
| Optional Blender import verification | Blender |

Vehicle tools/templates are bundled; no separate vehicle-configurator Skill is required.

Ask your Agent to install the complete Skill, verify it can load SKILL.md, then run read-only diagnosis. Prepare only missing core dependencies with your authorization; configure automation or Blender when requested.

```sh
# macOS, from the installed Skill directory
python3 -X utf8 scripts/environment.py doctor
python3 -X utf8 scripts/environment.py first-use --out /path/to/first-use-new
```

```powershell
# Windows PowerShell, with an available Python launcher
py -3 -X utf8 scripts/environment.py doctor
py -3 -X utf8 scripts/environment.py first-use --out C:\path\to\first-use-new
```

First-use creates a synthetic preview and GLB in a new directory; it does not modify user models or install dependencies. Playwright/Blender are not required for this core check. [Full installation guide](references/installation.md) includes isolated environments, manual preview, optional configuration and failure handling.

macOS has execution evidence. Windows detection and argument handling have simulated tests, but no real Windows run is claimed. Claude Code has not been freshly runtime-tested. Skill discovery and visual quality require separate confirmation.

## Quick Start

Attach a clear object image and ask:

> Use Image to 3D to build an editable model of this object. First identify the main shapes and missing views, then create a first model and show me where it still differs from the reference.

You receive a local model preview and its specification and review files. Inspect the original camera angle and at least one depth-revealing angle before accepting the result.

## Usage Examples

### Build a toy from a reference

> Turn this toy image into a model. Keep its recognizable silhouette and separate the parts I may want to recolor. Ask me before choosing a new hidden-side design.

### Repair a local shape

> The wing is too flat. Keep the camera, materials and other parts unchanged, rebuild its thickness and root, and compare the original and side views.

### Continue an existing model

> First verify which version this case actually loads. Preserve the shape changes I already accepted and the current materials and controls. Improve the body transition, show the before-and-after comparison, and keep the baseline wherever the result regresses.

### Prepare reusable assets

> Prepare this reviewed model for Three.js and GLB. Check part selection, color changes and disassembly. If Blender is available, verify the import too.

## How It Works

1. Analyze the original and prepare a reference set, including explicit uncertainty and generated-design approval.
2. Author the Spec: components, geometry, materials, cameras, relationships and real observation bindings.
3. Build local forms with `form_construction.py`; `construction_plan.py` connects recipes to actual meshes and protected parts.
4. Use `project.py` to build, capture, compare and review. `reference_set.py` checks reference records; `anchor_evidence.py` projects real geometry; `workflow.py` enforces evidence identity and stage requirements.
5. Use `surface_attachment.py` for declared mounting-root samples and aperture rays, and `surface_quality.py` for actual mesh continuity checks. Defect triage remains evidence-driven Agent judgment, not automatic image diagnosis.
6. Reuse `adoption_check.py` to assess recorded local adoption decisions; `version_handoff.py` validates version, inheritance and browser evidence records. It does not launch browsers or automatically hook into build/export.
7. Use the asset checks, `lightweight_delivery.py` and exchange tools to verify supported interactions, lossless transport and export. A diagnostic model is not an accepted delivery. Final case integration uses the project’s existing interface.

The bundled tools validate declared data and geometry. They do not automatically judge whether every picture or shape is correct. Scope, source evidence and human visual review remain necessary. Parallel Agents can split work under the collaboration contract when the host supports them.

## Repository Structure

```text
SKILL.md       Agent entry point
requirements.txt Core Python dependencies
agents/        Client display metadata
scripts/       Construction, project, review and exchange tools
references/    Modeling, reference and delivery standards
assets/        Three.js runtime, license and preview
examples/      Synthetic editable-asset examples
tests/         Software and optional runtime regression checks
```

Start with [the execution guide](references/unified-execution.md), [reference preparation](references/reference-set-standard.md), [local construction](references/form-construction.md), and [asset exchange](references/asset-exchange.md). The examples test functionality; they are not photo-reconstruction benchmarks.


For existing-model work, see [defect triage](references/defect-triage.md), [repair and root attachment contracts](references/repair-contract.md), [continuous surfaces](references/continuous-surfaces.md), [version continuity and case integration](references/presentation-delivery.md), and [lightweight delivery](references/lightweight-delivery.md).

Additional contracts: [legacy interface notes](references/implementation-contract.md) and [Spec and evidence](references/spec-and-evidence.md).

## License

Bundled Three.js retains its [own MIT notice](assets/vendor/LICENSE). Reference images and user-supplied assets require appropriate rights and are not relicensed by this repository. Rule provenance is recorded in [the source mapping](references/production-rule-sources.md).

## About Me

Maintained by [chemny](https://github.com/chemny). Report reproducible issues through [GitHub Issues](https://github.com/chemny/image-to-3d/issues).
