---
name: image-to-3d
description: 当用户需要从物体参考图分析结构、建立模型Spec、构建和校准可交互Three.js模型；提供多视角参考、曲面建模、装配与渲染对照的完整执行流程。车辆通过专用领域规则接入已确认配置器。
metadata:
  version: "0.6.0"
---
# Image to 3D

以任意物体图片为输入，代理完成观察、拆解和几何推断，工具将 Spec 落为可运行模型并提供可重复校准和审查。车辆是重点领域，不限制通用对象；单图遮挡区域是推断，不能承诺一次恢复精确真值。

## 开始与恢复

使用 [统一执行入口](references/unified-execution.md)。新任务 `python3 scripts/project.py init --image INPUT --domain generic --object-class generic --targets threejs glb --out TASK`；已有任务先 `project.py next --project TASK`。车辆用 domain vehicle。统一 state.json 决定阶段；历史项目证据只有资源和范围一致时才能复用，不从聊天推测已通过。

顺序：输入分析 → 参考确认 → 施工Spec → 主体 → 装配 → 材质/展示 → 对照审查 → 交付。每阶段提交真实证据；用户接受一个基线不等于质量通过。普通技术失败自行定位修复，设计冲突或需用户决定的范围才询问。原始图片用于本任务的授权不等于所有新生成隐藏面已经确认。

## 通用制作标准

新项目执行 [制作标准 v1](references/production-standard.md)：按原图分层观察，关键形体与关系绑定实际几何；Spec 审查前完成 production_contract，灰模使用当前捕获报告作多方向局部复查。production-check 校验声明与采样几何，不能替代视觉判断；采用拟合修复需通过 repair-check。旧项目不自动获得新版认证。规则来源与实现边界见 [来源映射](references/production-rule-sources.md)。

## 图片、Spec与建模

按 [施工操作](references/construction-playbook.md) 拆解主要体量、连续面、部件关系和识别细节，用网格辅助防漏。先执行 [建模参考集标准](references/reference-set-standard.md)：单图默认规划补充视角与关键结构特写，充分的已有参考可凭覆盖记录复用；参考准备不得跳过。登记原图/生成图、ROI、可见性、推断与置信度；生成造型先确认再取独立高清图。使用宿主图像工具，不依赖特定外部付费服务。

[统一数据契约](references/integration-contract-v2.md) 将观察绑定真实模型组件、顶点/曲面点、参数与相机。analysis负责语义清单，spec负责几何/观测唯一真值。几何按形状选择Bezier共边网络、旋转体、显式网格或适当基本体；未知类型拒绝，不静默退成方块。涉及分叉、收窄、厚片与凹槽时，先按 [局部形体施工](references/local-form-construction.md) 定义体积、截面和连接关系，在首个灰模中逐区验收，不能用缝线或平滑大体替代结构。

关键局部位置正确但形状不符时，执行 [形体构造与局部样件](references/form-construction.md)：先确定轮廓、截面、根部和构造参数，用可重建recipe生成实际网格，再检查局部与装配。构造计划接入验证，不能只写说明而不影响几何。

运行 `project.py validate` 后建模。早期预览明确用 `build --diagnostic`，禁止当交付；生产build要求Spec阶段已审查。相邻面共享边界与一致切向/法线，开合件使用实际分界及枢轴。Python与Three使用同一参数和变换来源，不独立维护一套评分点。

参考标定读 [锚点校准](references/anchor-calibration.md)，按固定机位检查实际模型投影、局部轮廓、厚度与连接；网格不是三维测量。新增规则测试见 [参考链路验证](references/reference-validation-plan.md)。

## 专业资产生产

新项目按 [资产生产规范](references/asset-production.md) 使用 asset_contract v1：明确 part/assembly、稳定组件ID、材质槽、独立变体子树、动作枢轴及来源。按对象选择 car / bicycle / motorcycle / toy / generic；不把汽车结构强加给其他物体。先统一比例/相机和主曲面，再拆实际部件、装配和材质；参考不能支持的隐藏结构标明推断。

构建后运行 asset-check 检查选取、独立换色、替换、拆解与动作恢复；按 [交换规范](references/asset-exchange.md) 导出 GLB，需要 Blender 目标时实际导入验证。最终按 [资产验收](references/asset-acceptance.md) 分开记录视觉、结构、功能、交换和性能；任一必需层未通过不能用总分抵消。网页临时编辑须回写 Spec 并重建才能交付。

## 修正与验证

通过 `build → capture → analyze/compare → fit或修改Spec → adopt/rebase → rebuild → recapture` 形成闭环，命令见统一入口。投影支持透视和正交，拟合基于模型真实绑定，校准与留出分离；不能通过改验证目标、移动参考或放宽阈值宣称改善。

红色显示模型超出参考、蓝色显示缺少部分。机位、尺寸与源身份先校验，轮廓之外还审查局部特征、曲面高光、装配和内衬。连续无改善时检查语义、可观测性和曲面表达，不盲目细分或重复调相同参数。

`scene_build` 的拓扑契约与 `mesh_checks` 的采样连接检查拦截可计算问题；实际开闭、多角度捕获仍要看，不能把接点通过当全面无碰撞。阶段审查使用 `review-template` 后填写实际结果，`mark`验证身份；代码、参数或参考更新后旧证据失效。

## 领域、协作和交付

- 车辆：读 [车辆领域](references/vehicle-domain.md)，保留已确认页面框架，模型经纯Three适配器接入；通用校对页不能替换产品配置器。
- 多Agent：按 [协作契约](references/collaboration.md) 冻结共享Spec/边界、精确分配写入文件并用check-all核对实际变化；宿主没有并行接口时顺序执行。
- 交付：审查通过后 `project.py export` 输出同版本模型/页面/资源与证据；拒绝陈旧或诊断包。外部发布另需用户指令。
- 能力/测试：见 [实现范围](references/capabilities.md) 和 [分层测试](references/validation-plan.md)。软件可运行不等于已证明任何图片高还原或效率优势。

## 环境

Python 3.10+；图片工具用 Pillow。Three.js及其许可随skill带入。真实捕获支持已安装Playwright和浏览器（传路径），也可用宿主浏览器工具记录同等证据；不自动安装依赖。车辆锁定页面由同级 vehicle-configurator 提供，可用 --vehicle-skill 指定位置。已有GLB/Blender资产修复继续使用该领域skill；不要求为新流程推倒有效资产。
