# 稳定执行与验收门槛

“一次集中优化”是一次诊断、一份冻结目标的计划、必要的顺序检查点和明确退出条件。稳定性首先来自输入可解释、方法适用、成果保护和独立验收；不等于任何图片都能恢复隐藏结构。这里规定正式验收条件，诊断与候选构建不因证据不足而停止一切工作。

## 范围先确定

| 目标 | 可接受的结论 | 缺失条件时的路径 |
|---|---|---|
| 无参考模型的资产修复 | 当前区域的表面、结构、UV/材料或功能质量 | 做资产质量优化；形似不作通过结论 |
| 指定视角/区域贴近参考 | 指定参考及可观察区域的形似 | 缺少对应机位/结构点时先做视觉诊断或校准相机，不能报像素通过 |
| 完整外观形似 | 前、侧、后、斜视及主体轮廓、屋顶、窗线、轮系、灯具和特征位置全部验收 | 参考不完整时交付明确区域的候选，保留完整范围未通过，不包装成整车完成 |

“贴近参考”不自动等于“贴近实车”：生成参考、未知来源拼图、非同款配置与推断部位必须单列。

## 六个检查点

| 检查点 | 通过依据 | 未通过怎么处理 |
|---|---|---|
| G0 输入与可达目标 | 车型/配置、尺度/轴向、可用参考和工具已确定；有证据的范围清楚 | 冲突参考分组/排除；隐藏区域标推断。无底模只先生成或构建主体候选 |
| G1 基线与验收计划 | 原输入→所选基线→优化结果分别留证；关键特征、机位、保护、阈值与独立样本优化前固定 | 新基线无同视角比较时不将换底模收益算为修形收益；无法量化时采用明确视觉标准 |
| G2 主体造型 | 所声明视角的车体外轮廓、屋顶/窗线、轴位、轮径及悬长同时合理；独立特征无关键失败 | 相机/参考先复诊，再修控制曲线、分区变形或更换基础候选。暂停依赖它的细节施工 |
| G3 分区与特征 | 共用边界、邻接过渡和特征位置通过；不是仅对象仍存在 | 有框无正确窗线、把手保住却放错位置都未通过。修对应载体/关系，不全车光顺 |
| G4 保护与运行 | UV/拓扑、材料/图片、允许域、法线/退化面及当前启用功能按任务检查 | 有保护或邻区回归先回退；正 Jacobian 不证明无自交，零退化面不证明形似 |
| G5 独立验收与交付 | 每个关键目标有当前证据；独立样本满足冻结标准；相关视角复核；质量结论分开 | 平均误差下降不能掩盖关键特征失败。继续执行 fidelity-loop.md 返工；预算耗尽或明确阻塞时输出最佳诊断候选与剩余差距，不把网页通过当造型通过 |

没有问题且证据身份仍有效的层级跳过。一个集中计划可含多个顺序通过阶段；不因检查点数量增加而重新探索已验证方法。

## 标注、阈值与独立性

- 优化前分开 calibration 与 validation，记录特征组、视角、原图点位和标注不确定性。整车验收须覆盖多个结构组，不能所有点都落在轮胎上。
- 阈值根据参考分辨率、尺度、标注误差与本轮范围解释；不设跨车型通用8像素或固定毫米目标。阈值比证据不确定性更严时应补证，不能报虚假精度。
- validation 参与反馈调参后变为 calibration，保留失败记录；新选独立样本前不能再用它证明泛化。多视角也一样：用于调整的图不能单独证明跨视角稳定。
- 修改前/后用固定相机、灯光和材料。相机重拟合须另存并说明可比性；不能靠移动相机隐藏车体差异。近似正交对照只作近似诊断，未经确认不报严格像素验收。
- 所选基线已有多视图误差时，不能把它当真值做大面积拟合；方法输入要能说明支持域与可信来源。

## 有限试修与停止

先在最影响当前目标的代表区域验证所选方法，再按同一因果扩大到同类区域。保护邻域并检查另一视角，不只看局部残差或反光。

任务指定本轮最小可辨改善、允许回归和同一修复链预算。改善小于证据噪声时不声称进步；关键目标或保护项退步即撤回。通过冻结目标后停止，不继续追求无依据的精度。同一目标默认最多2次反馈；无实质改善时按 [方法复诊](shape-optimization-methods.md) 改变原因假设/方法/证据，保留最佳版本。新的方法需明确新条件与理由，不静默重置原目标预算。

## 可执行记录检查

对涉及形似验收的集中优化，用 `scripts/optimization_review.py` 冻结和核对结构化计划；普通材料修复可使用 asset_quality 范围。它检查哈希、声明的证据和验收逻辑，计算点误差；不自动识别照片、判断造型或执行曲面优化。

```sh
python3 scripts/optimization_review.py seal --plan TASK/optimization-plan.json --out TASK/optimization-plan.lock.json
python3 scripts/optimization_review.py check --lock TASK/optimization-plan.lock.json --record TASK/optimization-review.json --out TASK/optimization-gate.json
```

lock 和 plan 放同一任务目录，引用文件相对此目录。先冻结再加工，输出不覆盖；改范围或标准要另存修订及原因，保留原计划的失败结论。退出码0表示 sealed/consistent，2表示 needs_revision，1表示契约或文件身份错误。consistent 只表示记录一致，正式视觉结论由实际看图评审决定。

计划 schema_version=1，字段：

| 字段 | 内容 |
|---|---|
| claim / coverage / scope | claim=asset_quality或reference_fidelity；coverage=asset_quality、selected_regions或whole_exterior；scope写具体可验证目标 |
| baseline_model / original_model / references | 任务文件路径；original_model可省略（纯图片任务）；references为路径数组 |
| baseline_comparison_evidence | 换模型基线时必填，文件路径数组；分别说明基线选择与加工收益 |
| views | 以视角ID为key，每项alignment=validated/approximate/unregistered；validated需alignment_evidence路径（由真实相机/视觉复核记录支持） |
| critical_features | 特征组ID→必须评审的视角ID数组；whole_exterior含body_outline、roofline、windowline、wheels、lamps、feature_placement及front/side/rear/quarter视角 |
| independent_features / required_checks | 必须有独立点通过的特征组数组；保护/资产检查ID数组，按实际加工选择 |
| calibration_points / validation_points | 每点id、feature、view、reference=[x,y]；validation另有threshold_px、uncertainty_px、threshold_reason，可选max_regression_px |

评审记录字段：plan_sha256（lock提供）、output_model={path,sha256}、checks={检查ID:{verdict,evidence}}、visual_reviews=[{view,features,verdict,evidence}]、observations=[{id,before:[x,y],after:[x,y]}]、used_for_adjustment=[参与反馈调参的validation ID]。每项 evidence 为 [{path,sha256}]，不是报告分数。检查与视觉状态使用passed或needs_revision。

不依赖新增 project.json 字段；任务卡仍负责方法、动作和授权，结构化记录补充验收。哈希能发现换文件，不能证明人工声明真实；检查器不将已有文件或高通过数量当作真实车辆准确性的证据。

## 跨案例验证与成熟度

流程验证、工具边界测试、真实形似验证分别记录。合成记录能证明错误声明会被拒绝，不能证明新车型能修准。

要提升方法成熟度，使用与提炼案例不同的输入做独立执行：有参考的干净模型、融合/UV接缝模型、无历史底模的图片、参考矛盾或不全的图片，以及纯材质任务。每例从原输入开始，保留首次计划、试修次数、关键误差、回归、可复用成果及未通过项；不向评审提供预期答案。既有模型选择与实际加工效果分别比较。

在这些输入上验证前，只能声明流程和检查机制已增强。历史车型上的成功方法可继续复用，但不能自动升级为“任意新输入稳定一次高保真”。真实车型、参考及大体积测试资产留在任务，不塞进 Skill 或 memory；工具的小型合成契约夹具可随测试脚本保存。

## 与批准参考闭环的关系

指定参考的最终形似任务按 [连续返工](fidelity-loop.md) 执行。用于调参的批准参考可证明 target_conformance，不冒充独立泛化验收；上述独立样本要求仍约束独立性声明。连续两轮无改善触发方法改变而非普通交付，总预算不重置。
