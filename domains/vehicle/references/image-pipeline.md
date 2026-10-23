# 图片路线执行契约

开始新模型构建前，先按 [造型总览确认关卡](reference-approval.md) 展示一张多视角图并取得对应版本的用户确认；reference-pack 的 accepted 记录不能代替用户造型批准。

工具做可追溯的局部计算；代理负责看图、解释来源、选择点位和建模。没有一键恢复任意车辆的模型，也不能把完整候选等同高保真成品。

资产获取和后续加工按 [tool-routing.md](tool-routing.md) 选择工具；已有 GLB 不要求转入 Blender。本文件的 loft_sections.py / surface_patch.py 是 Blender 辅助实现，使用它们时才需要相应环境；它们尚未移植为 Three.js 建模工具。参考包、section_curves.py 和 silhouette_review.py 可在其声明的 Python 依赖下独立使用。

先按 [统一集中优化](model-optimization.md) 查找可复用同车候选与已通过记录；本文件只补充图片参考和辅助工具，不要求每次重新造全车。底模的主要比例/轮廓未通过时先解决它们，局部补片不作为整车修形的替代。

## 逐视角参考包

`python3 scripts/reference_pack.py --spec <任务JSON> --out <新目录>`。当前支持 PNG/JPEG 原件，无新增库要求。

schema_version=1；sources 为 `{id,path,sha256,origin}`，path 相对 spec，origin 为 real/generated/inferred/user_supplied。views 为 `{id,source_id,roi,projection,consistency,evidence,configuration_group,configuration}`：

- roi 是原图整数 `[x,y,width,height]`，可省略表示整张；越界、陈旧哈希、重复 ID 拒绝。
- projection 是 perspective/approx_orthographic/unknown，不能因板上标签是“正视”就认定标定成立。
- consistency 是 accepted/excluded/needs_review；accepted 仅表示人工允许用于本任务，不认证来源或造型。
- 接受视角需要 configuration_group。configuration 记录 `{feature:{value,evidence}}`；同组已接受视角的同一特征矛盾时停止构建，排除的参考保留在包中。

生成 reference-pack.json、原图字节副本、输入 spec 快照与逐视角 SVG 画廊。只调整显示 ROI，不改原图像素。特征观察及 ROI 由代理填写，不自动识别配置或姿态。拼图中后视图被标为推断时，记录该说明；标签不能证明真正的照片来源。

## 有限建模与补片

无可信底模的盒状候选先按 [图片结构修正](image-structure.md) 修正可见体积和共用边界；该文档说明 section_curves.py 和 silhouette_review.py 的适用条件及严格范围，不将普通照片自动视为已对齐掩码。

`loft_sections.py` 可作为 blender_pipeline.py 阶段脚本运行，PARAMS.loft：schema_version=1、name、evidence、可选 material（已有材料名）、sections（至少两组 `{station,profile:[[y,z],...]}`）、可选 caps/smooth。世界 +X 是该计划的截面轴，+Z 上。截面 station 递增、轮廓点数与绕向一致；任务负责共同拓扑和无自交形状。工具按明确点线性连面、封端并重算法线，不插值猜测隐藏结构。已有同名对象拒绝替换。真实车辆的尺寸、截面和材质均在任务中。

`surface_patch.py` 的 `conform_patch(target,boundary_origins,direction,offset,rings)` 读取评估后的实际 Blender 网格，支持变换和修改器。边界射线位于任务明确的投射平面，形成无自交、可由中心辐射的区域；不适合任意凹形、遮挡、多层表面或错误投射方向。返回世界坐标顶点和面，不改目标；射线未命中时失败。调用方明确创建/替换哪个补片，并沿用材料和保护门。

该补片工具保证采样点投射到网格，不保证面内部、曲面法线或边界全无穿插。使用小偏移和足够采样后仍须看灰模与材质；不能以顶点命中代替视觉通过。纹理 UV、接缝、玻璃厚度和内侧结构须另行提供，工具不自动生成。

## 复核与交付

1. 先按 reference-pack 固定可用视角及原图来源，记录估算尺度与不可见区域。
2. 用真实几何对应点拟合每个视角的相机，优先预留独立复核点；按 camera-alignment.md 的 ROI 原图坐标契约执行。
3. 构建全车基础轮廓：轴距、车高、前后悬、窗线、前后轮廓；局部车头不能充当完整输入样例。
4. 定向修复应有集中任务卡、当前评审、允许变化列表和源哈希。同一连续修复链在任务卡中设置 `max_repair_rounds` 和依据；整个优化计划可包含多个已评审的顺序阶段，不以改名/换目录绕过同一未通过目标的预算。
5. 灰模、材质、完整性、几何、网页功能和性能分别结论。网页换色/下载成功不提升几何 verdict；可以交付明确标识的诊断网页。

辅助来源包与人工点可随任务交付，车型截面/镜像/尺寸不能写入通用 Skill。完整候选的背面、底盘、远侧、内饰仍须按证据区分观测、生成和推断。
