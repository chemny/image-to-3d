# GLB 与 Blender 交换

输入为 `scene_build.build(spec)` 的 JSON payload，坐标保持 +Y up / +Z forward。导出仅使用 Python 标准库，不安装依赖。

```sh
python3 scripts/asset_exchange.py payload.json --out model.glb --resource-root TASK
/Applications/Blender.app/Contents/MacOS/Blender --background --python scripts/blender_asset_check.py -- --glb model.glb --out blender-check.json
```

默认生成新文件 `model.glb` 和 `model.glb.manifest.json`；拒绝覆盖。API 为 `export_glb(payload, out=None, resource_root='.', include_all_variants=False)`。给出 out 时写文件并返回报告；不提供 out 时返回 `(bytes, report)`。CLI 可用 `--manifest FILE` 改报告路径，Blender 校验对应指定 `--manifest FILE`。

默认 GLB 只包含默认可见选项及其子树，报告列出被省略的组件 ID，GLB extras 保留变体定义。`--all-variants` 导出所有选项，用于结构检查；glTF 没有这里所需的标准节点可见性切换，通用导入器可能把选项全部重叠显示。`extras.default_visible` 只是元数据，不宣称 Blender 自动切换变体。需要每个选项单独可见的交付时，逐个修改 payload 的 variant default 并分别导出。

保留组件和装配层级、component_id、父子关系、position/XYZ rotation、selection/explode/material_slots 元数据。动作沿用运行时的父坐标 pivot 语义：插入 pivot 节点，组件位置减去 pivot，输出一秒钟独立旋转动画。大于 180 度的动作拆分关键帧，避免四元数取短路径。动画不包含运行时交互 UI 或 easing。相机接受统一的 width、height、position、target、up、fov_y_deg 或 ortho_height，及 near/far。

材质导出线性化的 sRGB 颜色和 PBR roughness/metalness/opacity，clearcoat、transmission、emissiveIntensity 使用对应 glTF 扩展。贴图仅接受 PNG/JPEG，资源必须位于 resource-root 内且 SHA-256 与 descriptor 完全相符；纹理直接嵌入 GLB，报告记录来源和哈希。color/emissive 纹理要求 srgb，其余要求 linear，使用 TEXCOORD_0，统一采用 glTF 顶部为 V=0 的 UV 约定，Three 运行时 texture.flipY=false，导出不额外翻转 UV。没有 UV 的纹理网格拒绝导出，不猜测或生成 UV。roughnessMap/metalnessMap 必须指向同一打包图：G 通道粗糙度，B 通道金属度；不自动进行通道打包。法线贴图使用 glTF 的 OpenGL/+Y 法线约定。

组件 material_slots 表示授权替换材质，默认导出主 material；备选映射保留为元数据，不能解释成同时分配给多组面的材质。需要多材质表面时按子件拆分。自定义 shader、未知材质参数/网格属性、payload scale/matrix 等未支持特性拒绝导出，不能静默遗失。asset_contract.version=1 要求材料来源 source。导出保留输入的几何与法线，不证明图像还原度。

Blender checker 实际调用 glTF importer，然后核对文件哈希、组件 ID、实际 mesh/material/camera/animation、静止姿态世界顶点包围盒。Blender 的 Z-up 坐标换回 glTF 坐标后比较（误差阈值 1e-4）。报告记录软件版本、对象父子关系、材质图片节点、动画名称与帧范围。报告需存在匹配 manifest 才通过；这不是仅解析 JSON 的假导入。结构检查不等于视觉审美、全部材质效果、开合碰撞、运行时脚本或图片高还原度验收。

测试：`python3 -m unittest discover -s tests -p test_asset_exchange.py -v`。通过PATH找到Blender或设置BLENDER_EXECUTABLE时会真实执行 Blender roundtrip，否则该项显示 skip，不能报告已通过实际 Blender 验收。
