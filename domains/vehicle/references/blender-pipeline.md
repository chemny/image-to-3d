# CLI + Python 分阶段建模与验收

本工具执行任务脚本、保留版本、生成检查图及记录评审。它不是单图自动恢复精确车辆几何的模型。几何脚本仍由代理根据当前参考编写，并在实际图像反馈后修正。

本文件仅用于已按 [加工路线](tool-routing.md) 选择 Blender 的任务。已有 GLB 的展示调整和可保护的局部属性加工优先在 Three.js／原生 GLB 层完成；版本与验收可以独立记录，不要求经过本执行器。

阶段划分来自 [集中优化任务卡](model-optimization.md)，不是要求重跑所有历史步骤。已通过且输入/参考身份仍有效的结果可复用；基础轮廓失败时先修主要结构，不先推进细节/材质。

## 任务结构及参数
任务目录保存 parameters-v1.json、各部件 Python 脚本、原始参考及版本目录。参数采用 JSON：

```json
{
  "schema_version": 1,
  "units": "m",
  "axes": {"forward": "+X", "up": "+Z"},
  "source": "记录真实尺寸来源或估算依据",
  "vehicle": {"length": 5.0, "width": 2.0, "height": 1.8, "wheelbase": 3.0},
  "wheel": {"paired_spokes": 10, "blade_half_width": 0.015},
  "required_nodes": [],
  "allowed_change_prefixes": [],
  "preview_hide_prefixes": [],
  "max_repair_rounds": 3,
  "resolution": [800, 600],
  "samples": 8,
  "views": [
    {"name": "side", "position": [0, 12, 1], "target": [0, 0, 1], "scale": 6.5, "clay": true},
    {"name": "reference", "position": [8, 10, 4], "target": [0, 0, 1], "type": "PERSP", "lens": 50}
  ]
}
```
示例尺寸、轮次和相机均不代表任何车型或默认任务；执行前根据目标差距和成本明确设置正整数 `max_repair_rounds`，记录理由。各阶段脚本必须真正读取相关 vehicle / wheel 参数，写了参数文件不代表几何已参数化。轴向需与导入资产核对；GLB 和 Blender 的轴向转换在网页中另行确认。根据车辆尺寸选择相机，参考透视图需要独立拟合相机并记录，不把标准正交图冒充像素匹配。

allowed_change_prefixes 为空数组表示不允许修改已有网格；省略表示允许任意网格修改；局部修复须显式设置部件前缀。检查覆盖网格顶点、面、世界变换、材质名称/面槽绑定和 UV。可用 allowed_material_names / allowed_image_names 限制材质和贴图变更：空数组禁止，省略保持旧流程允许修改的兼容行为。结果记录 changed_materials / changed_images，检查材质基色、节点输入/连线、图片绑定、贴图颜色空间/字节/像素；仍不覆盖所有自定义节点属性、修改器或动画语义，后者需专门检查。局部纯几何修复通常设置两项为空数组，不能只凭网格数宣称材质已保护。preview_hide_prefixes 隐藏未选中的轮毂变体，仅影响预览，不从 GLB 删除可选配置。

## 执行与恢复

```sh
python3 scripts/blender_pipeline.py run --stage proportions --params parameters-v1.json --script stages/proportions.py --out runs/01-proportions
python3 scripts/blender_pipeline.py review --job runs/01-proportions --verdict passed --scope proportions --reason "写明实际看图结论" --evidence runs/01-proportions/side.png
python3 scripts/blender_pipeline.py run --stage body --params parameters-v2.json --script stages/body.py --input runs/01-proportions/model.blend --depends runs/01-proportions --out runs/02-body
```
阶段脚本得到 PARAMS（参数字典）、JOB_DIR（本轮输出目录）、bpy；只负责本阶段几何，保存和导出由执行器处理。脚本是受信任的本地代码，不是沙箱：必须审查写入路径，禁止修改原始资产或 unrelated 文件。

每轮保存参数和脚本快照、来源哈希、blender.log、model.blend、model.glb、result.json 及相机预览图。目录不可覆盖。进程失败/超时标记 failed；代码执行成功仅标记 awaiting_review。失败后使用新目录重跑，不能只更改状态当作恢复。

## 评审与局部修复
按比例、车身、细节、内饰、材质顺序推进，阶段名可自定。每阶段至少查看侧面、正面和参考角；重点部件增加近景。记录具体偏差和修复范围。首次导入已有资产可先做 baseline，不要求重建整车。

```sh
python3 scripts/blender_pipeline.py review --job runs/02-body --verdict needs_revision --scope body --reason "门板与侧面曲面不连续" --evidence runs/02-body/side.png --issue "只修门板边缘"
python3 scripts/blender_pipeline.py run --stage body --params parameters-v3.json --script stages/fix-door.py --input runs/02-body/model.blend --repair-of runs/02-body --out runs/03-body-repair
```
--depends 要求上阶段评审 passed；--repair-of 要求 needs_revision，并限制连续修复轮次。不要通过去掉依赖或重置修复链绕过质量门。评审必须说明 scope，轮毂局部通过不等于车身或整车通过。需要原车高保真而比例未通过时，网页可作为清楚标记的诊断预览，不作正式资产验收。

max_repair_rounds 限制同一 --repair-of 链的反馈修正，不限制集中计划中有依赖的不同通过阶段数量。上限在任务卡确定，失败后不静默加大；同一目标两次无实质改善时应诊断方法，不通过另起阶段规避。工具不会自动判断基础比例或修复方法正确性，仍须实际看图评审。

```sh
python3 scripts/blender_pipeline.py compare --reference source.png --render runs/03-body-repair/reference.png --out comparison.html --note "相机尚未拟合，仅作形态对照"
```
比较页提供并排和透明度、缩放、位移叠图。修改前后使用相同相机、灯光、材质；原图与模型的比较必须说明相机是否对齐。工具不自动分割轮廓、不自动评分、不自动作 passed 判断。需代理查看证据并调用 review。

## 网页实测
用 model.glb 和已有配置器副本绑定，验证实际节点、换色、轮毂组、门动画、全景进出及窄屏。记录未实现项与未达到目标的几何差异。保留原版入口，只有新资产通过相关验收才替换正式模型。

参考相机已有人工锚点时读 [camera-alignment.md](camera-alignment.md)。fit_camera.py 的 pipeline-view.json 可合入参数；views 另支持 rotation_euler（Blender XYZ 弧度）、sensor_fit 和 sensor_width，以完整复现镜头。相机 aligned 只说明所给点的投影，不替代当前阶段几何 passed。
