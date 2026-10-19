# 通用形体修复与迭代

工作组织采用 [系统制作流程](systematic-production.md)：结构与表面分支共用参考、版本和展示；已有基线的替换执行 [采用质量阀](adoption-review.md)，退步或不确定的候选不替换已接受版本。本文正式认证/技术检查与迭代预览分别使用，不把预览进度等同认证通过。

新开始的修复先执行 [新建/修改共用参考准入 v2](common-reference-admission.md)。旧的“只补必要约束”指复用足够证据，不能跳过区域覆盖、机位校准或实际特征验收。

用于已有模型的局部或整体造型修正，包括首次建模后的继续迭代。车辆、软体玩具、日用品使用相同核心。具体造型、参数和领域尺寸留在任务中；不写入永久规则。材质、灯光及动作声明默认受保护；本版修复会话不承担材质反演或任意动画重设。

## 1 诊断、冻结、接入

先按 [缺陷分诊](defect-triage.md) 对照参考图区分 camera / proportion / representation / topology / connection / normal / material-lighting 原因；重叠面或深度冲突不能误判成掉漆。新增加的图先登记来源和用途，按区域说明优先级；多视图矛盾先定位相机或设计冲突。现有清晰参考够用时复用，不为了走流程重复生成。

精修前核对整体尺度、主体比例、稳定附件尺寸及主结构位置。相机与几何分别校准，能由比例表达的问题不整体拉伸所有组件。单图不足以确定的深度保留为推断。

按 [修复契约](repair-contract.md) 明确目标、可改件、刚性/完全保护件、参数范围、参考、视角、依赖和容差。关键组件逐个绑定自身视觉检查，不能只绑定相邻件。先补当前任务必要约束，不强制旧资产迁移全部新版格式。新建修复目录，保留可重建原Spec与资源。

```sh
python3 scripts/project.py repair-start --project TASK --contract CONTRACT.json --out NEW_SESSION
python3 scripts/project.py next --project TASK
```

repair_session 是主 project/state 的附属证据，不另建一套阶段批准状态。已接入后，删除会话、移除策略或缺少元数据均不能绕过检查。已有独立创建会话可 `repair-attach --session SESSION/session.json`，只允许未接入的项目。改变目标、相机或容差须明确新建会话/任务并保留旧证据，不能原地改合同降标。

## 2 少量可控参数与真实几何

先解决影响识别的主体和最难局部，再增加细节。使用原生Spec参数时：

```sh
python3 scripts/project.py repair-parameters --project TASK --values VALUES.json --out TASK/candidate.json
```

此命令只生成新候选，不自动采用。参数值必须实际驱动几何，保留原边界和语义；采用前重新构建并检查变化。外部作者脚本的控制参数应集中保存，重新编译为显式mesh，再登记源码摘要；不能只改Spec中的孤立数字声称模型已改变。现有参数化模块优先复用；复杂自由曲面选择适合的表达，不强塞进基本体。

刚性件只做允许的整体变换，全部对应顶点、拓扑、UV和渲染法线一致。主体局部变形时，边界与关联附件使用同一来源。依赖不完整默认完整复查；声明完整依赖只减少可确定无关的检查，关键目标检查仍保留。

## 3 开口、厚度与贴合

按结构选择实心、开放片、凹槽或贯通开口。影响识别/深度的黑色槽口必须有对应几何，不以黑片代替。声明宿主面、附着部件、安装间隙、回边与需要的封闭范围。开放衣片不强制全封闭。

`surface_attachment.evaluate` 提供 surface_gap：使用真实构建、父级变换和三角形，采样最近面距离及法线侧向；opening_clearance：从实际绑定点沿声明方向检查宿主阻挡。安装根部与局部宿主的选择、字段及边界见 [表面贴合约束](repair-contract.md#表面贴合约束)。容差必须在合同初始化前制定。

`cut_projected_opening` 可从无贴图的显式三角网格按轴投影减去凸多边形，保留深度范围外网格。输出positions/triangles；需重建法线，另外构造槽底、回边和厚度。不支持任意非凸布尔、UV自动插值或CAD曲面。纹理网格应使用能保持属性的适合构建器。

形体变形、平滑、坐标映射之后，重新计算或校验开孔、边框、密封边和附件的共同边界；不能把变形前的贴合当成最终贴合。相邻面优先共享边界函数和切线约束，避免各自拟合产生缝隙。修正一处后检查正面、背面及掠射角，区分法线反向、宿主残面和真实缺口。

薄板、玻璃框、壳体接缝等关键接口，另登记对应边界点对和允许间隙，用 distance 约束检查；不要只采组件中部。容差按对象尺度和连接方式制定。若采用设计上的上抬边或安装间隙，明确由哪个回边、内衬或紧固结构连接，并检查最终装配中的实际表面。

这些是声明样本/射线检查，不是全表面碰撞或语义识别。关键局部始终看原角度、揭示深度角度和连接上下文。

## 4 固定机位捕获

```sh
python3 scripts/project.py capture --project TASK --bundle BUNDLE --out NEW_CAPTURE --views reference side --modes beauty gray mask --poses closed --playwright-module EXISTING_PLAYWRIGHT/index.mjs --browser EXISTING_CHROME
python3 scripts/repair_capture.py create --spec TASK/spec.json --bundle BUNDLE --capture-report NEW_CAPTURE/capture-report.json --out NEW_CAPTURE/repair-capture.json
```

views/modes/poses可选；省略保持原全量捕获。局部轮次只捕获所需视角，最终覆盖合同全部视角。内部中性诊断/蒙版不增加产品页中间态入口。旧新对照必须同相机/画幅/姿态/展示条件；不配准图只能作视觉参考，不能输出还原分数。

凭据绑定实际构建、相机、资源和图像摘要，复用错图/旧图失败。局部裁图保留原机位和坐标关系，不能剪掉问题后判定通过。当前通用capture使用独立校对场景，产品页另做功能和展示核对。

## 5 检查、采用与安全回退

```sh
python3 scripts/project.py repair-audit --project TASK --out NEW_AUDIT.json
python3 scripts/project.py repair-review --project TASK --review REVIEW.json
python3 scripts/project.py repair-restore --project TASK --out NEW_REBUILD_PROJECT
```

audit只判断声明的几何/保护/影响关系。review需真实逐项视觉和功能审查，格式见repair-contract.md，引用当前捕获凭据。数字通过不自动形成视觉通过。外观未达到预先目标，保持fail继续修复或报告具体阻塞，不缩小scope出关。

生产build检查修复数值约束；主流程body及后续批准、export检查完整修复审查。代码/几何/参考或凭据变化后旧证据失效。普通技术返工自行处理；会影响用户确认设计的冲突交给用户决定。

restore新建基线重建项目，恢复冻结Spec及声明资源，清空批准，不覆盖当前源码/展示页。v1项目级恢复不支持带嵌套reference_plan/construction_plan的自动重定位；这类任务使用原有export保留的rebuild副本。底层model_repair.restore只输出Spec原字节与原资源基目录，不能当完整项目恢复。

## 6 效果验证

软件：正例、负例、父级运动、法线/拓扑、失效证据、误绑目标和策略删除。跨对象例子验证同一API，而非换名字的车模板。实际浏览器确认真实capture、选配、动作和恢复。

开发回归：固定参考及机位，记录具体改善、退步、失败轮次和耗时。已调过的车型/布偶/玩具均为开发样本。独立新对象软件测试只证明工具行为；未见图片的重建质量和速度需要单独对照实验。没有同等任务/质量/环境的旧新运行，不宣称提速百分比。

## 导出证据

附带修复策略的任务导出时，必须通过当前修复审查，并保存 repair-evidence/inventory.json、冻结输入、审查原件、捕获回执及图像。原件内部路径不重写；索引记录原路径与归档路径。这是历史证据归档，不向迁移后的重建项目自动授予通过状态。
