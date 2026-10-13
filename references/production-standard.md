# 通用制作标准 v1

用于从图片重建对象的分析、施工与验收；不是图片自动识别器，也不是一次成型保证。规则借鉴 img2threejs 的分层观察、拓扑选型、关键特征与自纠正体系，按本项目数据契约独立实现；来源见 production-rule-sources.md。

## 启用与兼容

新 `project.py init` 在 quality_contract 和项目/状态中声明 production_standard:1。intake/references 可在尚未写完施工契约时进行，到 spec 审查必须提供完整 production_contract。删除或降级已声明政策会被拦截。旧项目继续按旧流程读取，报告 legacy、不宣称符合新标准。旧项目迁移需备份、增加契约/检查项，并重新取得实现阶段证据；不自动追认。

diagnostic 只用于开发预览，不获得生产验收。已经声明的无效契约即使在 diagnostic 下也必须先修正。正式生产沿用统一状态文件，不能另建一套聊天进度。

## 制作步骤

1. 观察整体比例和主形体，再观察局部结构和表面细节；明确可见信息与推断。以原图及批准的补充参考为依据。
2. 为影响识别、结构和交付的特征登记 ROI、几何类型与实际绑定。先记录体积/厚度/截面变化，再增加材质纹理。简单物件不用虚构复杂结构。
3. 用部件关系描述接触、间隙、搭接、包裹、融合和铰接。观察不清的关系不能填成已知精确尺寸。
4. 决定建模方法并给出原因。凹陷需真实下凹曲面/体积，分叉需真实分支；贴片、画线不是大尺度结构。规则检查声明是否自相矛盾，不自动证明实现。
5. 首个灰模检查整体轮廓及关键内部形体；重要体积至少两个不同观察方向。单图背面只能评估合理性。
6. 结构通过后进入材质与光照，再运行实际装配、开合/动作、选择、换色、拆解和复位。每个阶段使用当前源身份的证据。

## production_contract 数据

外层 Spec schema_version 仍为 1；production_contract.version 为 1。字段：

- profiles：soft / hard / assembly / moving，可组合。assembly 要求关系；moving 要求铰接关系与实际动作。soft/hard 是施工规则选择，不是自动物理分类。
- features：非空，每项 id、reference_id、roi=[x0,y0,x1,y1]（0..1 非零矩形）、provenance=observed/inferred、importance=critical/important/supporting、form_type、component_ids、method={type,rationale}、check_ids。
- form_type：volume / concavity / branch / thickness / layer / curve / surface_detail。
- 绑定：geometry_bindings=[{component_id,vertex_index}]，或 observation_ids 引用已有 observations 的真实 vertex_index / patch_id+uv；不得用自由 local_point 标签代替实际表面。每个组件必须覆盖，显式网格顶点须被实际三角形引用。
- relations：列表；每项 id、type=contact/gap/overlap/wrap/fusion/hinge、component_ids（至少2个）、check_ids、rationale。
- geometry_checks：可选的已支持几何检查，格式如下。

关键/重要特征必须关联必需的 body/review 视觉 check。所有契约还必须声明 body 阶段必需视觉项 production-feature-coverage，由审查者核对原图有没有被遗漏的关键特征。填满列表不等于覆盖完整。

不要复制示例名当对象语义；用本对象的部件/特征名称。引用无效、绑定不存在、组件仅是 assembly、ROI无效或不支持的版本均报错。当前规则仅明确拦截 critical concavity 的 flat_patch/painted_line 和 critical branch 的 painted_line；换个方法名字不会让不正确几何变正确，实际结果仍须审查。

## 分类施工规则

| 类型 | 首版必须表达 | 复查重点 |
|---|---|---|
| soft | 鼓起、收窄、分叉、包裹、受压连接 | 侧面厚度、鞍面、收口、切向过渡；不可用多个小球堆叠代替连续体 |
| hard | 主曲率、边缘、开口、凹槽及壁厚 | 截面、背面、法线、高光；开放曲面与封闭壳体选择真实拓扑契约 |
| assembly | 实际组件及接触/间隙关系 | 世界坐标中的绑定、相邻件保护、选择/替换/拆解复位 |
| moving | 上述装配及实际轴/枢轴 | 关闭、中间、打开状态；静态接点通过不能证明全程无碰撞 |

对称件是关于声明平面的反射，不是随意旋转。天然不对称不强制镜像。头发层叠/头皮贴合、软体局部厚度等目前依赖灰模视觉审查；未接入 img2threejs 专用头发生成器或自动覆盖检测。

## 可计算检查

`project.py production-check --project TASK` 同时返回契约与几何结果。geometry_checks 中的 ID 必须对应 required:true、kind:numeric、stage:body/assembly 的 Spec.checks。

- distance：`{id,kind:"distance",a:binding,b:binding,min,max}`；检查实际世界点距离，单位沿用模型。
- mirror：`{id,kind:"mirror",pairs:[{a:binding,b:binding}],axis:"x",plane:0,tolerance:0.001}`；比较真实世界点关于平面的反射。
- binding：`{component_id,vertex_index}` 或 `{component_id,patch_id,uv:[u,v]}`。多曲面使用曲面绑定；不允许自由点。阈值在施工前依据尺度和不确定度确定。

几何检查在 body 及后续审批重新运行。checked:0 表示没有声明这类检查，不是全模型几何合格。未知检查类型拒绝。采样不能证明整面厚度、全模型碰撞、法线绕序或真实凹陷；已有 mesh_checks、scene_assembly 和运行检查继续负责其原定范围。

## 视觉证据与来源

body/review 的 review-template 会生成 production_review：reviewer_role=author/independent、execution_reference、coverage_verdict、capture_report、features。每项 feature 需 id、verdict、rationale、views:[{camera_id,artifact_path}]。

使用当前版本 `project.py capture` 的 capture-report.json；捕获报告和图片均列为带哈希 evidence.artifacts。校验 Spec 身份、相机配置、捕获行、文件位置/哈希与可读取图片，体积要求两个不同观察方向。报告由本地工具产生但不是防恶意伪造的数字签名；程序不判断截图美观或评审者是否真正独立。execution_reference 应指向实际评审任务/执行记录，不能只写另一个名字。

没有捕获工具时可继续诊断与人工查看，但不能绕过此标准的正式视觉证据门禁；安装依赖或改变捕获路径前按用户授权处理。

## 修复与回归

先分类：camera / proportion / representation / connection / normals / material / runtime；Spec 错误修改 Spec，实际生成与正确 Spec 不符时修构建器。不要靠改参考、机位或阈值制造改善。

`project.py repair-check --project TASK --record RECORD.json` 校验记录；启用 production_contract 的 `project.py adopt --report FIT --repair-record RECORD` 必须通过。手工编辑源代码不是此工具能自动拦截的操作，仍会使旧审批失效；执行者必须记录修复并重新审查。

记录 version:1、issue_id、hypothesis、change_summary、cause、decision=adopt/rework/reassess；before/after={spec_path,sha256}；protected_components；artifacts=[{path,sha256}]；results=[{scope:target/regression,verdict:pass/fail/unevaluated,method:visual/numeric/runtime,reviewer,artifact_paths}]。路径相对记录文件。adopt 必须全部通过且有目标视觉结果。

固定 references、quality_contract、observations、checks、production_contract 和 cameras；保护组件同时比较解析参数和祖先链。重新标定相机或改变验收定义应作为新的比较基线，明确记录理由并重新审查，不伪装为同基准改善。consecutive_no_improvement 达 reassessment_after（默认2）必须 reassess；当前计数由记录提供，不是自动累计器。

若在阶段证据附 repair_record，必须把记录本身加入哈希 artifacts。记录仍是审查声明，不证明实际改进；照片不可观测部分保持推断。局部通过与整体交付分开。

## 参考准备与局部回归

新项目按 reference-set-standard.md 检查参考覆盖，按 anchor-calibration.md 记录相机与真实几何绑定。关键特征逐项检查，整体平均分不能抵消关键局部失败。厚度、连接与遮挡不以单视图锚点误差代替。测试与故障注入见 reference-validation-plan.md；未通过视觉审查时不标记成品。
