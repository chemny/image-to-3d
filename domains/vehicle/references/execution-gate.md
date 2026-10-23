# 首版执行门禁

本规范要求代理按检查结果继续执行；不能把一次修改完成、截图生成或功能通过当作首版完成。脚本只校验声明、证据身份和决策，不自动判断画面真伪、不自动修网格，也无法从系统层禁止代理结束聊天。打包或宣称验收通过前必须重新运行门禁；尚未接入所有外部打包工具，不能声称不可绕过。

## 固定计划

先固定批准参考、相机校准方法、关键特征、保护项、独立校验样本、阈值依据及连续预算。任务目录保存车型坐标、具体阈值、图片和历史；不得把这些参数写成通用默认值。未校准阈值必须标记 calibrated=false，不能为通过而放宽。校准草案和正式计划分版本保留，不回填虚构历史，不借更换方法重置预算。

计划沿用 fidelity_loop.py 的格式，增加 required_views 和 required_features。每个视角必须有 <view>.silhouette、<view>.landmark、<view>.visual；每个关键特征有 feature.<name>；另有 protection 和 functional。覆盖范围应符合已确认任务，不得删掉失败视角。

```sh
python3 scripts/first_version_gate.py seal --plan TASK/plan.json --lock TASK/plan.lock.json
```

## 每轮证据

捕获时锁定模型、运行时代码、配置、模板身份和相机设置；保存输入快照及其哈希，并记录 live_inputs 对应实际交付路径。捕获前后核对来源没有变化。capture.json 包含 model、plan_sha256、inputs、live_inputs、outputs。每项文件引用为 path 和 sha256；路径相对于计划目录，或使用绝对路径。

outputs 必须包括每个视角的 <view>.render、.gray、.difference、.alignment，以及 feature.<name>。差异图采用清晰的红色溢出/另一色缺失标记，保留原图、模型图、图例和测量记录。先相机对齐，再比较几何；禁止靠非刚性拉伸、每轮重裁参考掩膜来改善分数。alignment JSON 记录 status=validated、相机参数，以及 independent_validation 文件引用；独立校验需包含未用于拟合的标志点和残差。脚本验证文件身份，代理仍须核验内容是否足以支撑结论。

轮次记录沿用 fidelity_loop 格式，增加 capture 文件引用。所有 checks 的证据都必须列在 capture.outputs 中；保护、交互、视觉审查也须保存相应证据。模型或运行时代码变更后，旧证据不得用于新版本验收。视觉二值通过必须基于真实审查，不得由功能测试或轮廓单一指标代填。

## 决策与继续执行

```sh
python3 scripts/first_version_gate.py check --lock TASK/plan.lock.json --record TASK/round-001.json --out TASK/decision-001.json
python3 scripts/first_version_gate.py authorize-delivery --lock TASK/plan.lock.json --record TASK/round-001.json --out TASK/authorization-001.json
```

输出不可覆盖。退出码 0 表示通过（seal 的 0 仅表示计划已封存）；退出码 2 禁止交付。只有 may_deliver=true 才允许声称首版完成。授权记录是本地核验凭证，不是密码学可信签名。

| action | 必须执行的下一步 |
|---|---|
| calibrate | 补相机配准、阈值依据或缺失证据，再检查 |
| repair_evidence | 恢复正确文件或重新捕获，不能据此宣称无法优化 |
| repair | 修复失败特征，再捕获全套必要证据 |
| rollback | 恢复最佳有效检查点，再验证 |
| change_method | 更换建模方法，保留同一目标与连续预算 |
| blocked | 如实说明具体阻塞或预算耗尽，保留最佳版本；不能说完成 |
| passed | 对当前交付资产重验后交付 |

缺证据、普通失败和停滞均不能作为“这一轮完成，等用户提醒再改”的理由。预算耗尽必须报告残差、尝试与后续所需条件；不能伪造通过或无限循环。用户明确暂停时遵从。既有案例接入时保留原记录，标明证据链从哪一轮开始，不把旧轮次包装成已通过新门禁。

## 验证边界

test_first_version_gate.py 验证覆盖、资产身份和拒绝行为；test_fidelity_loop.py 验证返工、退步回滚、停滞换方法与预算。合成测试通过不证明某个车型形似通过。真实车型必须保留自己的对照图、标注、测量与审查结论。
