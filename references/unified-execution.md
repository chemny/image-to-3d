# 统一入口：从图片到可交付模型

工作组织采用 [系统制作流程](systematic-production.md)：结构与表面分支共用参考、版本和展示；已有基线的替换执行 [采用质量阀](adoption-review.md)，退步或不确定的候选不替换已接受版本。本文正式认证/技术检查与迭代预览分别使用，不把预览进度等同认证通过。

新建默认reference_standard:2、foundation_standard:1；整体形体流程见 [整体形体控制](shape-foundation.md)。整体未通过不得进入正式精修；已有模型新修复先使用reference-prepare，再reference-check，按 [共用准入](common-reference-admission.md) 执行。next.reference_admission明确报告参考是否准备好；workflow的blocked:false不代表参考已通过。

执行代理负责看图、记录语义、选择几何与填控制网；确定性工具负责投影、构建、修正、捕获和证据校验。不要把这些角色混成“图片自己转出了控制点”。下列命令均从 skill 根目录运行，路径使用任务的实际绝对路径。

## 开始与参考

`python3 scripts/project.py init --image INPUT.png --domain generic --object-class generic --targets threejs glb --out TASK`

车辆使用 domain vehicle。初始化保留原图、哈希、尺寸，建立 spec.json、analysis.json、project.json 和唯一的 state.json；不预填猜测模型。每次恢复运行 `project.py next --project TASK`，不要只依赖聊天记忆。已有案例另按 [版本核实与成果继承](presentation-delivery.md#版本核实与成果继承) 执行 resume 记录检查；next 不自动查询统一案例或合并已接受样件。已有新core任务直接恢复；旧车辆项目保留原状态，迁移时单独登记输入与真实证据，不自动套用旧通过记录。

按 construction-playbook.md 看图并填写 analysis.feature_inventory：reference_id、feature、component_id、required、visibility。Spec 中观察项绑定 component_id 与 local_point / vertex_index / patch_id+uv 三种之一，并填 reference_id、camera_id、target、roi、parameter_ids、sigma_px 和 calibration/validation。隐藏项填 rationale/confidence，不假装观测。全部几何、相机、材质与动作放 Spec；analysis 不得持有不同版本的 observations。

参考准备必经，先按 [参考集标准](reference-set-standard.md) 登记视角与关键部件覆盖；单图任务默认补充参考。使用宿主图像生成工具：总览先确认造型，再出必要独立高清角度/局部；生成图附来源reference IDs、provenance、实际尺寸和批准状态。使用既有清晰原图优先。不能把原图请求当作已批准所有生成隐藏面，也已有充分参考可复用，但必须说明覆盖依据，不能仅以物体简单为理由跳过。

修改输入/analysis后运行 `project.py refresh-inputs --project TASK` 显式登记新身份；参考变更会撤回旧批准。这个命令不批准任何阶段。

## Spec、建模与校准

字段见 integration-contract-v2.md；实际约束由 reference_analysis.py、scene_build.py 和 reconstruction.py 校验。所有内置构建器用 +Y 向上、+Z 向前；不同坐标先转换。参数可写入几何/父变换/相机标量，语法 {"param":"name"}。选择Be​zier控制网、截面/旋转体、显式网格或合适基本体；未知形状不降级方块。

对需要可控局部构造的组件，先按 [构造计划](form-construction.md) 执行construction_plan apply生成新Spec。明确失效的旧拓扑观测，局部检查保持pending，完成实际灰模审查后再提交阶段证据。

`python3 scripts/project.py validate --project TASK`

缺字段就从图像分析和 Spec 补足，不生成伪数据让检查器通过。多视角优先拟合稳定材料特征，先分析相机/尺度可辨识性：

`python3 scripts/reconstruction.py analyze TASK/spec.json --parameters P1 P2 --out NEW_DIAG.json`

早期试验可 `project.py build --project TASK --out NEW_PREVIEW --diagnostic`。它仍验证输入和几何，明确隔离未通过作品，不能 export。正常 build 要先通过 Spec 阶段。每个阶段运行 `review-template --project TASK --out NEW_REVIEW.json`，实际审查后填 reviewer、rationale、artifacts 哈希及各check结果，再 `mark --project TASK --evidence NEW_REVIEW.json`。模板默认pending，不能直接盖通过章。

## 可重复优化闭环

1. `project.py build --project TASK --out BEFORE [--diagnostic]`：同一Spec输出场景、完整Three工厂、本地运行依赖、精确相机和来源清单。
2. `project.py capture --project TASK --bundle BEFORE --out CAPTURES --playwright-module EXISTING_PLAYWRIGHT/index.mjs [--browser EXECUTABLE]`：真实WebGL捕获每个机位的材质/灰模/轮廓及关闭/半开/展开。只用已存在运行依赖，不自动安装。无CLI浏览器时可用宿主浏览器读取同一modelReview接口并保存同等证据；不能跳过捕获直接声称验证。
3. 比例/位置残差用 reconstruction analyze。红蓝图用 `project.py compare --project TASK --capture-dir CAPTURES --view VIEW --reference-mask MASK.png --alignment ALIGNMENT.json --out DIFF`。先制作独立参考二值蒙版并验证机位；alignment的camera/model与蒙版哈希需匹配。不会自动缩放、透视扭曲参考以迎合候选。
4. `project.py fit --project TASK --parameters P1 P2 --iterations 80 --out FIT.json [--diagnostic]`：从模型真实几何绑定计算投影，拟合只看calibration，记录所有候选和保护区域退步。控制网坐标可用参数引用参与拟合。只能改善所声明误差，不能保证全局最优。
5. 审查候选、语义和保护视角后 `project.py adopt --project TASK --report FIT.json`：核对输入版本、归档旧Spec、采用新参数、使后续旧验收失效。人工控制网/拓扑修复直接改Spec/模型来源后也要重验；不把临时浏览器修改当持久修复。
6. 重建到新目录，重新capture与compare，检查与原图是否相符。若无显著改善，按construction-playbook区分语义、机位、表达能力、拓扑/法线、材质原因，换对应方法；普通返工自行处理。

数字改善不自动mark通过。连续回归/预算用尽保留最佳候选与问题说明，不更改原图或放宽门槛伪通过。对开发集进行过方法选择后，不再称它为独立盲测。

## 装配、显示与交付

scene_build会根据逐件topology_contract检查开闭；内置硬边生成器使用显式诊断拓扑副本，渲染网格保留硬法线；用户mesh不默默焊接。装配连接点、归属与姿态的结构约束用 mesh_checks.py，视觉捕获补检查全表面穿插、空洞、门槛/内衬等；它不是连续碰撞引擎。

普通物件默认通用校对/展示页；车辆按 vehicle-domain.md 连接已确认配置器，不改其HTML/CSS。最终项目所有阶段审查通过后：

`project.py export --project TASK --bundle CURRENT_BUNDLE --out DELIVERY`

它拒绝诊断包、陈旧Spec、资源变更和未通过交付门槛。打包可重跑资源/证据，不等于部署或GitHub发布。公开skill不包含用户案例模型或私有参考。

项目指定统一案例展示页时，继续执行 [展示交付与案例接入](presentation-delivery.md)：将已验收交付版本登记到项目案例目录，完成统一界面的加载、操作及切换回归后才报告接入完成。当前export不自动注册案例；不得将模型包导出成功当作案例页已更新。


## 资产合同、真实操作和跨工具交换（v0.3）

新建项目添加 `--object-class generic|car|bicycle|motorcycle|toy`（取其中一个），`--use display|configurator|disassembly|animation`，`--targets threejs glb blender`（实际需要的目标）。`init` 只建立空合同；必须从分析填写 required_components / required_operations，不能把空项目当已建模。旧项目不带 asset_contract 时保留原行为，不能因此称为完整专业资产。

按 asset-production.md 编写契约。显式网格支持 uvs（每顶点2值）、normals（每顶点3值）；torus/tube生成UV。贴图在项目内部，声明 path/sha256/color_space。UV统一采用glTF方向，Three加载 flipY=false；颜色/emissive用srgb，normal/roughness/metalness/ao用linear。不具备UV的几何不能贴图。更换材质/换部件使用授权slot/variant边界；不随意删除父节点。

```sh
python3 scripts/project.py asset-check --project TASK --bundle QA_BUNDLE --out NEW_AUDIT --playwright-module EXISTING_PLAYWRIGHT/index.mjs --browser EXISTING_CHROME
python3 scripts/project.py exchange --project TASK --bundle QA_BUNDLE --out NEW_EXCHANGE --blender EXISTING_BLENDER
python3 scripts/project.py export --project TASK --bundle QA_BUNDLE --out DELIVERY --asset-report NEW_AUDIT/asset-report.json --exchange-dir NEW_EXCHANGE
```

asset-check使用通用校对页，锁定车辆配置器仍另外执行原有版式/功能检查。若最终bundle为锁定车辆页面，先使用同Spec通用包完成技术审查，再用独立锁定界面证据；当前自动export的asset-report要求完全相同bundle身份，不能拿通用包报告冒充锁定包已通过，需以通用资产包交付核心模型，车辆页面另包交付。

exchange输出 model.glb、清单、交换报告，以及实际执行时的blender-report。允许在诊断阶段检查可交换性；诊断包仍不能正式交付。默认GLB只含当前默认变体，完整备选件留在Spec/Three工厂；需要所有备件用独立asset_exchange.py --all-variants检查包，它会同时显示全部，不是默认展示模型。GLB保存几何、材质、层级、相机、旋转动作；选择/换色/拆解交互脚本留在Three代码。导出不等同于有CAD精度、完整DCC编辑历史或照片级质量。

最终export对asset_contract项目额外要求实际操作报告和目标交换报告，核对Spec与bundle身份、资源哈希并归档；Blender目标没有真实导入就拒绝。临时网页调色、替换和拆解是检查状态，不改变Spec，也不悄悄导出成新设计。


## 制作标准 v1 扩展

参见 [通用制作标准](production-standard.md)：新增生产契约、真实表面绑定、采样距离/镜像检查、捕获绑定的局部多视角记录以及显式修复审查。新项目在 Spec 阶段强制完整契约；旧项目保持兼容但不追认。规则完整性与视觉还原质量分别验收，未见对象效果需另做独立测试。

## 已有模型修复入口（0.7）

造型修复使用 [通用修复流程](repair-workflow.md)；repair-start/repair-audit/repair-review/repair-parameters/repair-restore 共享原 project/state 阶段，不创建第二套批准状态。未接入修复的历史任务保持兼容；接入后不能删除策略逃过检查。

## 校准前置：粗比例与机位

只调相机失败时先核对语义与可观测性；参考支持的实际粗比例可以执行[联合初始化](coarse-initialization.md)。`coarse_initialization.py`生成新候选与报告；`coarse_baseline.py --spec CANDIDATE --contract JOINT --fit-report FIT --resource-root RESOURCES --out NEW_BASELINE`重新校验后冻结。新基线之后再执行reference-prepare/repair-start，初始化报告不能替代body或交付审查。


## 轻量展示交付

接入 [轻量展示交付 v1](lightweight-delivery.md)：新建构建默认采用独立或锁定模板兼容的无损压缩数据，界面不重复加载完整几何。分别记录展示资产预算、解压规模及设备性能；现有功能、视觉、交换验证和采用质量阀保持有效，打包通过不代替这些结论。
