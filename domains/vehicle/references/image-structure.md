# 图片粗坯的结构修正与轮廓验收

用于无可信底模、已建立图片相机但斜视仍显盒状的候选。先复核标注和可见体积，不扩大粗估截面去堆细节。以下工具只解决明确控制截面和同机位轮廓检查，不能自动恢复任意车型。

## 修正结构

分开检查下车身、机盖/尾厢、乘员舱等可见分区；单张侧面最高点直接外挤成等宽实体通常会把车顶、玻璃和肩部合成盒子。用正面/后面的有效观察约束相应宽度及收缩，侧面约束屋顶、腰线、轴位及悬长；无证据的深度单列推断。各视图的车身、轮胎和后视镜宽度要分别标注，不能用一个模糊包围框代替。

标注同时区分近侧、远侧和顶面。略俯视的侧图中，远侧边缘也可能构成最高外轮廓；把所有像素都反投影到同一个近侧平面，会系统性抬高机盖或肩部。先声明深度假设并检查另一已有视角，不以每个点都投影匹配一个视图来证明真实截面。

检查可见形状的斜率变化处，增加有依据的控制截面；在没有特征折线的方向做平滑采样。不能把截面插值当作自动校准形状，也不要横跨机盖边、窗框或真实折线做全车光顺。

`section_curves.py` 在明确且拓扑一致的 +X 控制截面之间做有界单调三次插值，保留每个原控制截面、局部坐标范围和镜像关系。`max-step` 使用当前 authored 单位，由任务按尺度和曲率指定。新采样意味着新顶点拓扑，仅适合新建曲面；不能直接覆盖需要保留原 UV/顶点身份的资产。

```sh
python3 scripts/section_curves.py --input TASK/control-sections.json --max-step TASK_STEP --out TASK/sampled-sections.json
```

输入沿用 loft_sections.py 的明确 sections 契约；输出仍可作为 make_loft 的计划。工具检查有限值、station 顺序、轮廓点数/绕向及采样预算；不保证面内部无自交、真实曲率或车辆尺寸。

轮拱属于主体结构。用可见轮心、轮径和拱口轮廓建立真实开口及间隙，不把轮胎贴在一整块未开孔的车身上。布尔操作可用于明确的开口，但必须检查实际结果的非流形边、退化、近邻轮廓和锐边法线。轮胎与轮拱不能共用同一半径就宣称匹配。

玻璃与窗框优先共用控制边界或面分区材质；单独浮贴多边形容易出现穿插、错误厚度和缝线。轮廓阶段可先以同曲面的分面材质表达玻璃，玻璃厚度/内侧结构另外验收。把手和缝线沿实际载体安装，不能用一个常数侧宽去浮贴所有点。主体未通过时暂停轮辐、灯具和装饰细节。

## 可执行轮廓检查

对已标定相机、有明确前景掩码的任务，可以用 `silhouette_review.py` 冻结各视角的投影轮廓标准，再检查实际候选。

```sh
python3 scripts/silhouette_review.py freeze --spec TASK/silhouette-plan.json --out TASK/silhouette-plan.lock.json
python3 scripts/silhouette_review.py check --lock TASK/silhouette-plan.lock.json --candidate-dir TASK/renders --model TASK/model.glb --render-record TASK/renders/render-record.json --out TASK/silhouette-review.json
```

依赖已有 Pillow/numpy。freeze/check 输出使用新文件；返回0=冻结/通过，2=needs_revision，1=证据/契约错误。mask_mode=alpha 需要真实透明通道（阈值128），binary 需要明确 L 模式的0/255掩码。普通不透明照片、全前景/全背景参考或尺寸不一致会拒绝，不自动抠图、缩放或配准。即使 PNG 是 RGBA，旧合成器也可能把背景写成不透明；诊断渲染应检查通道内容，并保存关闭诊断后期处理的证据，原参考图原件保留。

spec schema_version=1，claim 固定 projected_outline，scope、baseline_model 必填。views 为下列记录数组：

| 字段 | 内容 |
|---|---|
| id / role / origin | 唯一视角；role=calibration或validation；origin=real/generated/inferred/user_supplied |
| reference / baseline / candidate_filename | 前两项相对 spec 的图像路径；最后一项为候选渲染目录中的单个文件名 |
| mask_mode / alignment_evidence | alpha或binary；已对齐相机及裁切的证据文件，不由工具自动判断真实性 |
| minimum_iou / maximum_boundary_p95_px | 每个视角的交并比下限和双向边界距离95分位上限，由本任务冻结 |
| uncertainty_px / threshold_reason | 标注不确定性不高于边界阈值；明确为什么该目标适用于本任务，不能复制通用像素数 |

render-record.json：model_sha256 绑定实际模型；views={id:{sha256,alignment_sha256}} 绑定每张候选掩码与相机证据。推荐实际解码最终 GLB 后渲染，以检查导出后几何；自填哈希本身不能证明图片来自该模型。

输出逐视角 before/after 的前景 IoU 和双向轮廓距离；轮廓包含掩码中的内部孔边界（例如格栅、轮毂孔），不是凸包或自动填孔的外包络。若 G2 只评主体外轮廓，需要在冻结前提供定义明确的分区/外轮廓掩码，将细部开口另外验收；不能在失败后临时填孔或松阈值来升格同一验收。报告要区分整体包络误差、分区边界误差和细部孔洞，不能让一个混合平均值代替诊断。

工具不会做自动相机重拟合，任何视角不达标均保持失败。`--used-for-adjustment VIEW_ID` 明确污染已参与调参的 validation 视角，工具不允许它继续独立通过。旧视角进入反馈后保留失败记录，重新冻结未使用视角或独立特征；新目录不是独立证据。

**轮廓通过仅证明已声明投影掩码的边界。** 窗线、灯组、轮拱内边界、曲面鼓包、材质和隐藏结构仍需按各自范围核对；IoU 不是“车型相似度百分比”。生成示例上的通过不能升级为实车照片或整车高保真。将结果作为 optimization_review 的 required_checks 一项，继续执行相关特征与视觉验收。
