# Automotive Studio reference case / 成熟车辆配置器案例

This public Skill contains only the case guide, provenance and rebuild script. Models and images are not distributed with this release. Running this specific reference example requires a separately authorized asset archive from its owner; otherwise use scripts/project.py with your own model. The contents below describe that optional archive. Intermediate iterations are intentionally omitted.

## 内容 / Contents

- `original/model.glb`: 最早下载的腾讯图生三维原始模型；哈希与历史导入记录一致，未改字节。
- `original/source-image.png`: 历史项目保留的源参考图片；不宣称已验证它与下载模型的生成请求一一对应。
- `original/reference-images/`: 用户后续提供的统一造型生成参考原件，八个视图及一张推测底视图；不是实测工程图。
- `final/`: 已验收完整配置页、最终 GLB、内嵌贴图、语义遮罩、案例材质适配模块、三张页面参考图及 Three.js 依赖。
- `provenance.json`: 原始与最终资产身份及用途说明。
- `rebuild.py`: 使用当前 Skill 模板和最终资产在新目录重建配置页。

## 运行 / Run

Ask your Agent: “打开本 Skill 的 Automotive Studio 参考案例，用本地 HTTP 服务运行 final/index.html，并检查换色、视角、灯光、参考图库、JSON 和 PNG 保存。”

Agent command, from this directory:

```sh
python3 -m http.server 8901 --bind 127.0.0.1
```

Open `http://127.0.0.1:8901/final/`. Use HTTP; double-clicking index.html cannot reliably load module/GLB resources. No Blender, remote API, model download or credentials are needed to run the finished example.

To rebuild with the installed Skill template:

```sh
python3 rebuild.py --out NEW_DIRECTORY
```

`rebuild.py` uses the final model and case adapter. It rebuilds the page, not the historical model reconstruction. The raw model and final model differ: the final geometry includes earlier Blender repairs; the latest layout/material/light alignment used Three.js. This example is not evidence that arbitrary raw images/models can reach this result in one automatic pass.

## 使用边界 / Scope

Copy the workflow, layout hierarchy, resource integrity and verification rules. Do not copy this vehicle's UV masks, hard-coded feature coordinates or paint segmentation onto another vehicle. Fixed wheels remain fixed; there are no usable door-opening parts or replaceable wheel variants. Physical mobile performance is not certified.

## 素材权利 / Asset rights

Original Skill code/documentation are covered by the root MIT license. Model files, input/reference images and their depictions retain their respective rights and are excluded from that MIT grant. Their public redistribution authorization has not been established by this local packaging step. Three.js retains its bundled notice. The public core release does not distribute the underlying model/image archive. The README screenshot was selected for this release; it does not grant redistribution rights to the original assets.

## 视角动画 / View animation

The current final page uses an approximately 800ms eased orbit for view presets, follows the shortest azimuth arc, replaces pending destinations on a new click, and allows pointer/wheel takeover. Reduced-motion preferences use immediate placement.

The current view labels are 正侧45°、车头侧面、后侧45°、车尾、车顶. The roof preset looks down from above; all five retain the smooth orbit transition.
