# 建模参考集标准

新项目及新修复使用 [共用参考准入 v2](common-reference-admission.md) 的任务/区域/机位/特征扩展；本文v1来源与生成设计确认规则继续适用。

本规范适用于通用对象。目标是给轮廓、体积和连接提供依据，不以凑够固定图数代替覆盖检查。参考准备是必经阶段；单图任务默认规划补充视角与关键局部。已有充分参考可复用，但须逐项记录覆盖和理由，不因“简单”自动跳过。

## 制作顺序

1. 原图拆解：主体、独立部件、识别特征；列可见/遮挡/隐藏和信息缺口。
2. 建立 reference-plan.json：需要哪些视角、哪些局部以及用途；图像ID与关键部件覆盖关系明确。未确认状态保留pending。
3. 用宿主生图工具先出总览核对同一造型；原图可见造型优先。新增隐藏面由用户确认后，才出独立高清视角和必要特写。用户已明确批准的同版设计不重复询问。
4. 核对独立图与总览和原图一致；不得把小总览插值放大称为高清。记录真实图像尺寸、来源、批准证据及哈希。
5. 参考集检查通过后进入标定与Spec；开发诊断允许隔离预览，但不追认审批。

## 视角选择

默认规划正面、背面、左右侧、俯视和补充斜视。对称、不可见或与用途无关的视角可以有依据地合并/不要求，必须记理由；内部、底部与开闭状态按交付目标补充。车辆继续读vehicle-domain，不强加汽车图数给玩偶或自行车。

每图说明朝向、投影估计和可用特征。生成“正视图”不代表严格正交；先估计相机再用投影对照。图像不提供物理尺寸时使用相对比例并声明，不能虚构毫米精度。

## 结构特写

按关键结构分组，每组覆盖outline / volume / connection：外轮廓与凹口；厚度与截面变化；根部与相邻件。一个角度不足时增加另一个。保留周边上下文和部件定位。原图裁切只放大已有信息，不增加背面或真实分辨率；生成细节属于设计补全，不是观测真值。

## 人工视觉验收

- 关键轮廓未裁切，重要边缘在实际标注尺寸下可辨，未被高光/阴影大面积遮挡。
- 部件数量、主要比例、连接、分瓣与不同视角一致。冲突先处理参考，不让模型迎合矛盾图。
- 每张图有部件/特征用途；每个关键部件都有轮廓、体积、连接依据或明确未解决项。
- 原图、派生裁切、生成补全明确区分；隐藏面被批准只代表设计授权。
- 保留干净图，网格/锚点为独立分析层。不得重生成原图来降低当前模型误差。

reference-check只能验证记录、身份和覆盖声明，不会自动看懂图片。视觉一致性必须引用实际查看的图片/证据并给出判断；模板填pass不等于事实。

## 标定和版本

按anchor-calibration.md建立稳定结构点、视角相关轮廓、ROI与模型绑定。相机估计可用简单代理形体，但精建前冻结验证机位。必要纠正相机需重新记录版本并使旧比较失效。参考/计划修改必须refresh-inputs；阶段批准不能沿用旧哈希。

## 实际检查入口与数据

0.8起新项目init自动生成v2 reference-plan.json，并设置reference_standard=2固定到project/state；旧v1记录仍可读取，历史项目不追认新版认证，新修复先迁移共用准入。

```
python3 scripts/project.py reference-check --project TASK --stage references
python3 scripts/project.py reference-check --project TASK --stage spec
```

计划是Spec的source_files哈希资源，spec.reference_plan指向该文件。结构：
- version:1、status:pending/ready、strategy:generate/reuse；reuse必须填写reuse_reason，generate必须含实际生成补充参考。
- required_views:[{id,reference_ids}]：所需视角的覆盖。
- critical_components:[{id,coverage:{outline,volume,connection},component_ids,observation_ids,uncertainties}]：coverage值为参考ID数组；Spec阶段绑定真实组件和属于它们的观察。
- sources:[{reference_id,source_identity,parent_reference_ids,view:{orientation,projection},purpose}]：生成/派生parent_reference_ids必须与Spec.source_reference_ids相同。
- 生成源增加approval:{actor:user,decision:approved,reference_sha256,evidence:{path,sha256}}。确认记录必须反映真实用户授权，不能伪造。派生图若沿用同版设计确认，应在记录中说明来源及一致性复查。
- consistency_review:{verdict:pass,method:visual,reviewer,rationale,reference_hashes:{参考ID:哈希},artifacts:[{path,sha256}]}；unresolved_conflicts必须为空才能通过。

批准和审查artifacts都须为Spec相对路径，加入source_files并哈希。待完成计划允许intake，但references及后续阶段不能通过。机器结果certified:false表示仅校验身份和覆盖声明，不自动认证图像真实性或视觉质量。

### 非固定点的形体约束

Spec阶段每组必须有真实observation_ids或明确的manual_constraints，不能为了覆盖率把轮廓伪造为固定3D点。manual_constraints每项包含kind(silhouette/section/connection-review)、component_id、reference_ids、uncertainty、rationale、artifact:{path,sha256}。组件须真实存在且属于该组，参考须在覆盖范围，artifact须source_files登记。两类约束均为空则拒绝。manual_review_required明确表示尚需形体视觉审查；登记人工约束不代表几何通过。
