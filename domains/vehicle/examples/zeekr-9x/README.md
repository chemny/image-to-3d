# ZEEKR 9X image-to-3D case / 极氪 9X 图片建模案例

This optional case archive contains the five user-supplied reference images, two user-approved generated reference boards, and the accepted final Three.js configurator with its GLB. The public Skill repository carries this guide and provenance only; the vehicle/image archive is packaged separately because public redistribution rights have not been established. Intermediate model iterations and review drafts are omitted.

## 内容 / Contents

- `original/user-supplied/`: five original vehicle images, kept byte-for-byte.
- `original/approved-reference/`: approved exterior and detail boards. They are generated design references; inferred views are not engineering evidence.
- `final/`: the accepted runnable H5 page, final GLB, Three.js source and local vendor dependencies. `model.js` and `build_glb.py` preserve the final geometry construction path; `model.glb` alone does not reproduce runtime door, hatch, light and wheel interactions.
- `provenance.json`: file identities, origins, acceptance scope and exclusions.
- `verify.py`: checks the archived file hashes and required runtime files.

## 运行 / Run

After merging the optional archive into the Skill directory, ask your Agent: “打开极氪 9X 案例最终配置页，运行并检查旋转、换色、三款轮毂、开门、前后备箱、车灯、参考图与保存导出。”

From this directory:

```sh
python3 verify.py
python3 -m http.server 8902 --bind 127.0.0.1
```

Open `http://127.0.0.1:8902/final/`. A local HTTP server is required for module and GLB loading. No Blender, external service, credentials or model download is required to run the completed example.

## 验收边界 / Acceptance scope

The user chose this P1/P2 version as the **case final** after reviewing the remaining gains from further local refinements. Functional, framing and offline checks passed in the source task. This does **not** certify whole-car visual fidelity: the silhouette, front fascia and body curvature still visibly differ from the original photos. Only the side-view local upper-contour gate was numerically calibrated; other views need qualitative review. Interior and hinge structures are inferred. See `final/FINAL_ACCEPTANCE.json` for the recorded decision and limits.

Use this case to study the source → approved boards → Three.js model → interaction → separate functional/visual acceptance workflow. Do not reuse its vehicle-specific coordinates, geometry or numerical thresholds as general Skill rules.

## 素材权利 / Asset rights

The root Skill MIT license applies to original Skill code and documentation. Vehicle imagery, approved boards, model geometry and their depictions retain their respective rights and are not covered by that grant. The local archive is for this case's handoff; public redistribution authorization has not been established. Bundled Three.js keeps its own `final/vendor/LICENSE` notice.

## 默认功能基准

用户已指定本案例最终配置页为后续车型的功能与布局基准，默认功能清单见 [默认交付规范](../../references/default-delivery.md)。此指定不改变上述造型验收结论，也不授权复制车型专用参数或公开素材。
