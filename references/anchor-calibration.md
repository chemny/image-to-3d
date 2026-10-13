# Reference grid and geometry-bound anchor evidence

This is an evidence tool, not an automatic shape reconstruction or visual approval.
Use after the reference set is approved and before fitting. Preserve clean source images;
the tool writes a separate 10-by-10 grid overlay and report into a new directory.

## Annotation contract, version 1

All paths in annotations resolve relative to that annotation file. Freeze the reference
Spec separately from the mutable candidate. Hashes use SHA-256 of file bytes; camera
hash uses `anchor_evidence.digest(scene_build.resolve(camera, parameters))` (sorted,
compact JSON). Record the same frozen annotations for every comparison.

```json
{
  "schema_version": 1,
  "reference_id": "original",
  "image": {"path": "reference.png", "sha256": "FILE_HASH", "size": [100, 100]},
  "reference_spec": {"path": "frozen-spec.json", "sha256": "FILE_HASH"},
  "camera_id": "front",
  "camera_sha256": "RESOLVED_CAMERA_HASH",
  "transform": {"kind": "identity"},
  "features": [{
    "id": "wing-root",
    "kind": "landmark",
    "target_px": [50, 50],
    "uncertainty_px": 1,
    "tolerance_px": 3,
    "protected": true,
    "regression_allowance_px": 0.5,
    "binding": {"component_id": "wing", "binding": {"vertex_index": 0}}
  }]
}
```

Numbers above illustrate schema, NOT universal tolerances. Author coordinates by
reading the reference; never populate targets from model projections. Declare
uncertainty, task-specific acceptance tolerance, and protected-feature regression
allowance before fitting. Uncertainty is reported, not added to tolerance.
A hash locks the comparison but cannot prove honest authorship or declaration time;
retain the baseline preparation record and independent review.

The top-level `reference_id` must identify exactly one reference entry in both the
frozen and candidate Spec. Its referenced image file and recorded SHA-256 must match
the annotation source. An unrelated same-size image is rejected. Spec reference paths
resolve relative to each Spec, while the annotation image path resolves relative to
the annotations.

A feature can use `observation_id` instead of `binding`; the Spec observation must
exist uniquely, use this reference ID and camera and retain the same binding in the candidate. Both
paths resolve real mesh `vertex_index` or Bezier `patch_id` plus `uv` using
`scene_build.landmark`, followed by `reconstruction.project`. Arbitrary `local_point`
labels are rejected in this evidence tool. Mesh vertex count and triangle indices
must remain unchanged; re-topology needs explicit reannotation. Preserve vertex
semantics even when index counts match. Occlusion and semantic correspondence need
review: a point can numerically project correctly while not being the visible feature.

For a view-dependent contour point use `kind: "silhouette"`, coordinates and
uncertainty/tolerance, with no binding/protection. It is displayed but always marked
`manual-review-required`. A head's leftmost image edge is generally not the same
3D point across cameras. Use separate fixed-camera masks/contours for those checks,
not pseudo-landmark triangulation.

## Run and interpret

```sh
python3 scripts/anchor_evidence.py --annotations annotations.json --spec candidate.json --out evidence/anchors-v1
python3 scripts/anchor_evidence.py --annotations annotations.json --spec candidate-v2.json --baseline-report evidence/anchors-v1/report.json --out evidence/anchors-v2
```

The immutable baseline model file must remain available with its original hash.
Outputs: `anchor-overlay.png` (blue reference target, red model point and displacement
arrow) and `report.json`. Each feature reports pixel/normalized coordinates, world
point, signed displacement, error, declared tolerance and protected regression result.
No global mean can hide a failed local feature. `numeric_checks_passed` applies only
to measured landmarks; `manual_review_pending` flags contour review; `visual_pass`
is always false because projection evidence alone cannot certify shape.

Source image bytes, annotation bytes, candidate Spec bytes and resolved camera identity
are recorded. Changed source/reference Spec, changed camera, changed annotation
criteria across a regression comparison, invalid binding and dimension mismatch fail.
Crop/resize transforms are deliberately unsupported and rejected, never silently
aligned or warped. If a crop is necessary, prepare an explicitly documented new
reference and compatible camera/annotation baseline; do not compare it as the old run.

This does not prove thickness, topology closure, attachment, material fidelity, all-view
accuracy or physical truth. Keep gray multi-view checks, structural tests and manual
semantic review as separate acceptance evidence. A contour-only file has zero numeric
checks and never passes numerically. Tool execution success is not gate approval.

## Tests

`python3 -m unittest discover -s tests -p test_anchor_evidence.py -v`

Covers real geometry displacement and coordinate direction, vertex movement, invalid
bindings, fake local points, changed camera/dimensions, stale image/Spec, unsupported
transforms, silhouette non-certification, protected regression and changed tolerances.
