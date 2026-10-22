---
name: image-to-3d
description: 当用户需要根据参考图建模或修复已有模型时使用；从物体参考图分析结构、建立模型Spec、构建和校准可交互Three.js模型；提供多视角参考、曲面建模、装配与渲染对照的完整执行流程。车辆通过专用领域规则接入已确认配置器。
metadata:
  version: "0.12.5"
---
# Image to 3D

以任意物体图片为输入，代理完成观察、拆解和几何推断，工具将 Spec 落为可运行模型并提供可重复校准和审查。车辆是重点领域，不限制通用对象；单图遮挡区域是推断，不能承诺一次恢复精确真值。

## 开始与恢复

使用 [统一执行入口](references/unified-execution.md)。新任务 `python3 scripts/project.py init --image INPUT --domain generic --object-class generic --targets threejs glb --out TASK`；已有任务先 `project.py next --project TASK`。恢复已有展示案例时，按 [版本核实与成果继承](references/presentation-delivery.md#版本核实与成果继承) 区分当前生产版、已接受样件和施工基线，并核对实际加载身份。车辆用 domain vehicle。统一 state.json 决定阶段；历史项目证据只有资源和范围一致时才能复用，不从聊天推测已通过。

顺序：输入分析 → 参考确认 → 施工Spec → 主体 → 装配 → 材质/展示 → 对照审查 → 交付。每阶段提交真实证据；用户接受一个基线不等于质量通过。普通技术失败自行定位修复，设计冲突或需用户决定的范围才询问。原始图片用于本任务的授权不等于所有新生成隐藏面已经确认。

## 新建与修改共用制作流程

按 [系统制作流程](references/systematic-production.md) 组织参考、拆解、重点样件、结构与表面施工、对照检查及展示交付；复用现有 project/state 和工具，不增加一套审批状态。结构与纹理/颜色/材质分别诊断、联合展示。有已接受基线的修改，替换默认展示前执行 [采用质量阀](references/adoption-review.md)：受影响区域退步或判断不确定时保留原版，候选可继续隔离试验。无需所有区域改善，不以总分抵消局部退步。基本可运行性、用户指定不可改内容及结果真实性仍须遵守；正式认证与迭代预览分别标识。

## 整体形体先行

新建默认foundation_standard:1。按 [整体形体控制与验收](references/shape-foundation.md) 声明修改层级、主体关系、真实曲线/截面与固定尺度；主曲面从Spec统一生成。主体轮廓、内部特征、体积与曲面全部通过后才进入精修。旧模型新一轮形体修改先foundation-prepare，不自动认证旧结果；整体偏离应重构对应主体，不能以局部加宽或平滑替代。纯技术修复可沿用原设计，但必须由既有工具证明形状未改变，不追认旧模型还原达标。

参考准备时保存像素网格与标注；每个形体候选捕获受影响机位并做当前红蓝绿对照（红超出、蓝缺少、绿重合）。机位近似的叠图只能诊断。正式整体审查要求所有声明验收机位；控制、机位或参考变化使相关批准失效。诊断失败回到参考/机位/表达，不自动采用，也不无期限重复局部试修。

## 已有模型修复与迭代

新建及修改共用 [参考准入 v2](references/common-reference-admission.md)：先声明目标、关键部位、当前设计依据、ROI及覆盖缺口，再校准机位、绑定实际特征与冻结施工范围。新建默认v2；历史项目开始新修复也不能跳过，不因已有图片数量多而默认准备完成。原图不足以确定的新设计先取得确认；已有充分参考直接复用。匹配参考任务不得以局部改善替代还原验收。

已有模型改造先读 [通用修复流程](references/repair-workflow.md) 与 [修复契约](references/repair-contract.md)：先按 [缺陷分诊](references/defect-triage.md) 定位相机、比例、拓扑、曲面、贴合、法线或材质/照明原因，冻结目标、保护件、固定机位与容差，再做局部施工和逐项审查。`project.py repair-start` 接入唯一主流程；`repair-audit` 检查实际世界几何、刚性法线与依赖，`repair-review` 核验真实捕获和判断。依赖不完整完整复查；旧资产只补本轮必要约束。主流程body和交付拒绝缺少修复审查的候选，数值通过不代替视觉。

## 通用制作标准

新项目执行 [制作标准 v1](references/production-standard.md)：按原图分层观察，关键形体与关系绑定实际几何；Spec 审查前完成 production_contract，灰模使用当前捕获报告作多方向局部复查。production-check 校验声明与采样几何，不能替代视觉判断；采用拟合修复需通过 repair-check。旧项目不自动获得新版认证。规则来源与实现边界见 [来源映射](references/production-rule-sources.md)。

## 图片、Spec与建模

按 [施工操作](references/construction-playbook.md) 拆解主要体量、连续面、部件关系和识别细节，用网格辅助防漏。先执行 [建模参考集标准](references/reference-set-standard.md)：单图默认规划补充视角与关键结构特写，充分的已有参考可凭覆盖记录复用；参考准备不得跳过。登记原图/生成图、ROI、可见性、推断与置信度；生成造型先确认再取独立高清图。使用宿主图像工具，不依赖特定外部付费服务。

[统一数据契约](references/integration-contract-v2.md) 将观察绑定真实模型组件、顶点/曲面点、参数与相机。analysis负责语义清单，spec负责几何/观测唯一真值。几何按形状选择Bezier共边网络、旋转体、显式网格或适当基本体；未知类型拒绝，不静默退成方块。涉及分叉、收窄、厚片与凹槽时，先按 [局部形体施工](references/local-form-construction.md) 定义体积、截面和连接关系，在首个灰模中逐区验收，不能用缝线或平滑大体替代结构。

已有可信外部生成脚本按 [外部几何验收适配](references/external-geometry.md) 核对源码/输入、双重重建、参数作用与实际网格；普通门禁不隐式执行脚本，再生通过不替代参考和视觉验收。

关键局部位置正确但形状不符时，执行 [形体构造与局部样件](references/form-construction.md)：先确定轮廓、截面、根部和构造参数，用可重建recipe生成实际网格，再检查局部与装配。构造计划接入验证，不能只写说明而不影响几何。

边缘、厚片收口及多面转角执行 [连续曲面施工](references/continuous-surfaces.md)：先区分硬边与平滑连接，用连续截面、切向匹配卷边及受边界约束的补面替代直壁和无约束网格平均。最难局部先做样件；surface_contract接入实际构建检查，掠射光/条纹和参考轮廓分别复核。保留设计硬边，有限采样不宣称全局G2。

运行 `project.py validate` 后建模。早期预览明确用 `build --diagnostic`，禁止当交付；生产build要求Spec阶段已审查。相邻面共享边界与一致切向/法线，开合件使用实际分界及枢轴。Python与Three使用同一参数和变换来源，不独立维护一套评分点。

参考标定读 [锚点校准](references/anchor-calibration.md)，按固定机位检查实际模型投影、局部轮廓、厚度与连接；网格不是三维测量。新增规则测试见 [参考链路验证](references/reference-validation-plan.md)。

只调机位仍不达标时，先执行 [粗比例与机位联合初始化](references/coarse-initialization.md)：核对源图语义，冻结校准/留出与尺度基准，仅调整有参考依据的实际粗比例及机位。完整原生几何、资源、可观测性与留出均通过后另存新基线，再进入正常局部修复；不得把诊断拟合当成还原验收或覆盖产品模型。

## 专业资产生产

新项目按 [资产生产规范](references/asset-production.md) 使用 asset_contract v1：明确 part/assembly、稳定组件ID、材质槽、独立变体子树、动作枢轴及来源。按对象选择 car / bicycle / motorcycle / toy / generic；不把汽车结构强加给其他物体。先统一比例/相机和主曲面，再拆实际部件、装配和材质；参考不能支持的隐藏结构标明推断。

构建后运行 asset-check 检查选取、独立换色、替换、拆解与动作恢复；按 [交换规范](references/asset-exchange.md) 导出 GLB，需要 Blender 目标时实际导入验证。最终按 [资产验收](references/asset-acceptance.md) 分开记录视觉、结构、功能、交换和性能；任一必需层未通过不能用总分抵消。网页临时编辑须回写 Spec 并重建才能交付。

## 轻量交付与加载

按 [轻量展示交付](references/lightweight-delivery.md) 在现有 build/asset-check/exchange/export 中执行：完整几何只加载一次，界面复用轻量元数据，默认无损压缩，贴图按内容去重。展示资产默认目标50,000,000字节，可由 delivery_profile.budget_bytes 覆盖；超预算报告原因，不自动减面或改变材质。制作源与展示数据分开保留，大小不代替渲染性能或视觉判断。旧包仅在明确迁移时输出新版本，原版保留；未知适配器不猜测转换。采用前核对解压/资源哈希、实际几何材质、浏览器请求及原有交互，再执行已有采用质量阀。

运行时出现阴影跳变、局部修复触发整车缩放，或需要冻结预览/检查发布依赖/局部回退时，按 [运行时校验](references/runtime-guards.md) 补充已有修复与交付检查；不自动改模型或写注册。

## 版本登记与空间清理

迭代恢复、采用/接入及收尾按 [版本生命周期](references/version-lifecycle.md) 从已有状态刷新版本登记，生成只读清理预览；保护正式版、已认可未接入成果、候选、回退和原图/源码/有效证据依赖。用途未知不自动清理。取得具体范围授权后才隔离载荷并事务性退役显式旧入口；restore 在永久删除开始前恢复模型与入口。真实检查后由 purge-plan / purge 按独立已确认清单永久删除；删除开始后不能完整恢复。隔离不释放空间，不自动到期清理。工具不修改几何或自动注册，build/export 尚未自动挂接，定时调度另需授权。

## 修正与验证

通过 `build → capture → analyze/compare → fit或修改Spec → adopt/rebase → rebuild → recapture` 形成闭环，命令见统一入口。投影支持透视和正交，拟合基于模型真实绑定，校准与留出分离；不能通过改验证目标、移动参考或放宽阈值宣称改善。

红色显示模型超出参考、蓝色显示缺少部分、绿色显示重合。机位、尺寸与源身份先校验，轮廓之外还审查局部特征、曲面高光、装配和内衬。连续无改善时检查语义、可观测性和曲面表达，不盲目细分或重复调相同参数。

`scene_build` 的拓扑契约与 `mesh_checks` 的采样连接检查拦截可计算问题；实际开闭、多角度捕获仍要看，不能把接点通过当全面无碰撞。阶段审查使用 `review-template` 后填写实际结果，`mark`验证身份；代码、参数或参考更新后旧证据失效。

## 领域、协作和交付

- 车辆：读 [车辆领域](references/vehicle-domain.md)，保留已确认页面框架，模型经纯Three适配器接入；通用校对页不能替换产品配置器。
- 多Agent：按 [协作契约](references/collaboration.md) 冻结共享Spec/边界、精确分配写入文件并用check-all核对实际变化；宿主没有并行接口时顺序执行。
- 交付：审查通过后 `project.py export` 输出同版本模型/页面/资源与证据；拒绝陈旧或诊断包。指定统一案例页的项目按 [展示交付与案例接入](references/presentation-delivery.md) 登记已验收版本，检查统一布局、操作和选配；导出不等于完成案例接入。外部发布另需用户指令。
- 展示请求：打开页面前按上述交付文档判定用户要看模型、统一案例还是审查证据；前文已确认目标不能被环境当前URL替代。检查页面用途和实际模型加载，HTTP成功不等于打开了正确模型页。
- 能力/测试：见 [实现范围](references/capabilities.md) 和 [分层测试](references/validation-plan.md)。软件可运行不等于已证明任何图片高还原或效率优势。

## 环境

Python 3.10+；图片工具用 Pillow。Three.js及其许可随skill带入。真实捕获支持已安装Playwright和浏览器（传路径），也可用宿主浏览器工具记录同等证据；不自动安装依赖。车辆锁定页面由同级 vehicle-configurator 提供，可用 --vehicle-skill 指定位置。已有GLB/Blender资产修复继续使用该领域skill；不要求为新流程推倒有效资产。
