# 通用已有模型修复契约 v1

新建会话默认先执行 [共用参考准入v2](common-reference-admission.md)。底层model_repair.init同样检查；只有显式diagnostic=True/--diagnostic可运行隔离软件或旧资产诊断，记录production_eligible:false且不能附加到生产主流程。

本标准用于已有模型的局部修复和首次建模后的迭代。车辆、玩具、布偶、家具均使用同一核心；领域扩展只补对象特有的比例和结构。不替代 `repair_review.py` 历史版本的拟合审查，也不声称自动判断视觉还原。

## 权威与会话

先在基线中登记本轮已授权参考和固定相机，再初始化修复会话。初始化后，目标、图片、投影机位、容差及保护规则冻结。中途新增设计参考、需要改变验收目标时，建立新会话，并说明变化原因，不能覆盖原契约。

`model_repair.init(spec_path, contract_path, out)` 返回 `{passed,session_path,session_sha256,contract_sha256}`。会话输出必须新建；保存原 Spec、契约与每项声明资源的原始字节。现有展示页面、源码及资源均不覆盖。基线的资源快照不受后来合法源码修改影响；候选的每项资源必须当前存在、与候选登记的摘要一致。不能删除原有 `source_files` 项来规避溯源。

契约源文件本身以及会话冻结副本若被修改，检查失败。修改作者代码后允许更新候选 `source_files.sha256`，但已有捕获和审查随候选及资源变化失效。会话摘要是证据身份的一部分，不是防恶意篡改的密码学签名。

## 必填契约

```json
{
  "version": 1,
  "object_class": "generic",
  "targets": [{
    "id": "profile",
    "component_ids": ["body"],
    "reference_ids": ["original"],
    "problem": "主体宽高比偏离原图",
    "expected": "在冻结机位下复原已标注轮廓并保留附件形状",
    "check_ids": ["profile-original", "profile-depth"]
  }],
  "editable_components": ["body"],
  "allowed_added_components": [],
  "allowed_parameters": ["body_width"],
  "protected_components": [{
    "id": "eye", "mode": "rigid",
    "allow_translation": true, "allow_rotation": false
  }],
  "dependency_edges": [["body", "eye"]],
  "dependency_complete": false,
  "checks": [
    {"id":"profile-original","method":"visual","component_ids":["body"],"view_ids":["reference"],"view_role":"original"},
    {"id":"profile-depth","method":"visual","component_ids":["body"],"view_ids":["side"],"view_role":"depth"}
  ]
}
```

- `editable_components` 必须为基线实际组件。新增组件需预先列入 `allowed_added_components`。v1 不提供删除已有组件的捷径；有删除需求时需在前置范围审查中重建基线。
- `protected_components.mode=exact` 保持实际世界几何及声明不变；`rigid` 允许声明的平移/旋转，保持对应顶点、拓扑与UV；实际渲染法线必须随允许的刚性旋转一致变化，不能翻转或单独改写。依次解析参数及所有父级变换，再比较实际几何。父节点变动不能通过子节点原始 JSON 未变来逃过检查。未列入 editable 的其他组件默认 exact。
- 刚性检查采用所有对应顶点的正旋转最小二乘拟合；不允许缩放、拉伸和镜像。容差固定为数值误差 `1e-9` Spec 单位。几何对称或完全重合可能不能唯一决定旋转，但仍须证明全部对应点保持形状。assembly 无网格时比较实际变换。
- 参数只能修改已授权数字值，不能改变边界或增加参数。`parameters` 命令调用同一真实场景解析器，不产生独立评分几何。相对资源路径存在时，输出候选与基线 Spec 源文件同目录，保持冻结路径身份。
- 材质、变体、相机、参考、观察目标、质量契约、检查、生产契约、坐标系、动作及资产契约默认冻结；未知顶层权威字段同样冻结。`id`、`metadata`、当前源码摘要可以变化。
- 视觉检查至少覆盖原图机位和一个揭示深度或连接的机位。角色用 `view_role: original/depth/connection`；仅不同相机 ID 不够，实际相机位置必须不同。每个 target 组件必须至少被自身 check_ids 中的一项 visual 检查直接引用，不能用无关部件检查替代。非 target 的刚性保护件不强制新增独立视觉项。角色是否能揭示问题仍由评审者核实。
- `dependency_complete=false` 或未提供时，每轮要求所有检查。显式完整依赖按有向边传递重验；目标直接绑定的检查始终保留。遗漏的依赖不会被工具自动猜出，完整性声明必须经过评审。

## 拓扑重建与语义观察

`allow_rebind_observations: ["edge-observation"]` 预授权指定观察的几何重绑定。只允许 `component_id/local_point/vertex_index/patch_id/uv/binding` 变化；ID、特征、参考、目标像素、ROI、容差、角色和相机必须保持。顶点及曲面绑定以实际构建后的三角形/Bezier patch验证；绑定脱离实际三角形失败。拓扑改变但未授权的顶点观察不得继续沿用旧索引。

授权不代表新绑定语义正确，仍须在原图机位人工复核。稳定中心点等 `local_point` 是受控语义点，不声称来自可见表面。

## 数值施工约束

`constraints` 每项绑定 `checks` 中一个 numeric ID。可选支持：

- `distance`：`a/b` 为真实 `{component_id,vertex_index}` 或 `{component_id,patch_id,uv}`，`min/max` 为已冻结区间；世界坐标测量，不接受任意手填局部接点冒充表面。
- `normal`：`component_id,mesh_index,triangle_index,direction,min_dot`，检查实际世界三角形法线与期望方向的点积。期望方向是设计声明，工具不推断内外。
- `topology`：`component_id,contract: closed_shell/open_patch`，复用生成器精确焊接映射及 mesh_checks。布片等合理开放结构用 open_patch；不强迫所有对象闭合。不自动跨独立网格焊接。
- `surface_gap/opening_clearance`：委托 `surface_attachment.evaluate`，详见表面附着工具。宿主和附件使用实际三角网格；覆盖范围为声明采样/射线，不等于完整碰撞证明。

数值检查不能代替局部形体、高光、遮挡和视图复核。

### 表面贴合约束

沿用 `kind:surface_gap`，不新增修复会话类型。旧的自动全件采样仍支持；对于伸出宿主的部件，应明确检查安装根部，而非要求整个部件表面都贴近宿主：

```json
{
  "id":"root-gap","kind":"surface_gap",
  "component_ids":["attachment"],"host_component_ids":["shell"],
  "anchors":[
    {"component_id":"attachment","vertex_index":0},
    {"component_id":"attachment","vertex_index":1},
    {"component_id":"attachment","vertex_index":2}
  ],
  "host_faces":[{"component_id":"shell","mesh_index":0,"triangle_index":0}],
  "min":0,"max":0.002,"side":"outside"
}
```

以上 ID、索引和阈值只是字段示例，须依据当前网格和安装方式填写；数值单位沿用 Spec，不能把此示例作为所有物体的安装公差。

- 不填 anchors 时使用现有自动表面采样（samples 为 3..256，默认 32）；填 anchors 时不再填写 samples。显式根部绑定总数为 3..256，每个声明部件至少三个，不接受重复绑定。支持现有真实 vertex_index 或 patch_id+uv 绑定，经完整父级变换后测量，不接受手填孤立坐标冒充根部。
- 根部样本应分布在安装周边及关键接触区域；最低数量检查不能证明覆盖充分。记录所检区域，不能只挑一个贴合点替代周边检查。修改拓扑后重绑并重新捕获；位置相同的新旧索引也不能自动复用旧证据。
- host_faces 可选；每项指定已声明宿主的真实 mesh_index/triangle_index，不能越界、重复或选择退化面。用于隔离实际安装面，防止附近侧壁或另一层面掩盖悬空。该选择同样适用于 opening_clearance；没有声明时沿用全部宿主三角形。
- min/max 是非负最近距离范围；side 按宿主所选三角形绕序区分法线正/负侧。inside 仅代表负法线侧，不是闭壳内部证明；深埋超过 max 仍失败。法线侧偏移并非实体穿透深度，邻边、尖角和绕序不确定处需另查。每个失败样本记录 above_max_gap、below_min_gap 或 wrong_normal_side，不能仅凭标签判定语义原因。
- 返回采样世界坐标、距离、法线侧偏移、失败样本索引和宿主面数，便于逐点诊断；不自动移动部件。最近距离不验证覆盖重叠面积、全表面碰撞或整个动作过程。

通过现有 repair-start/repair-audit 执行该约束；独立软件调用 `surface_attachment.evaluate(spec, checks)` 使用同一实现。空检查集和重复检查 ID 明确拒绝，不把“没有检查”报告为贴合通过。

## 捕获与审查

`check(session_path,candidate_path,out=None)` 返回 `passed/errors/candidate_sha256/changed_components/affected_components/required_checks/constraints`；未知形体或资源不完整时失败，不回退基本体。

`validate_review(session_path,candidate_path,review_path)` 需要如下记录：

```json
{
  "version":1,
  "session_sha256":"...",
  "contract_sha256":"...",
  "candidate_sha256":"...",
  "reviewer":"实际评审者",
  "decision":"adopt",
  "results":[{
    "id":"profile-original", "verdict":"pass", "method":"visual",
    "notes":"实际观察到的形体及保护项结论",
    "artifacts":[{"path":"capture/reference.png","sha256":"..."}],
    "capture_report":"capture/repair-receipt.json"
  }]
}
```

每个 required check 都要独立结果、说明和当前存在的摘要匹配证据。不能通过平均分抵消失败。视觉证据必须属于 `repair_capture.validate_receipt` 验证过的真实捕获，且覆盖该检查所有 view_ids。receipt 冻结候选、构建包、源码、相机及图像身份。普通截图可以作为补充说明，不能伪装成精确身份捕获。数值和功能证据同样登记文件及摘要，评审者须负责其方法与内容真实性。

该验证器检查记录与身份，不读取图片自动决定好坏；填写 pass 并不证明视觉真的达标。

## 命令与回退

```text
python3 scripts/model_repair.py init --spec TASK/spec.json --contract TASK/repair.json --out TASK/repair-session
python3 scripts/model_repair.py check --session TASK/repair-session --candidate TASK/candidate.json --out TASK/check-01.json
python3 scripts/model_repair.py parameters --session TASK/repair-session --values TASK/values.json --out TASK/candidate-02.json
python3 scripts/model_repair.py review --session TASK/repair-session --candidate TASK/candidate.json --review TASK/review.json
python3 scripts/model_repair.py status --session TASK/repair-session --candidate TASK/candidate.json
python3 scripts/model_repair.py restore --session TASK/repair-session --out TASK/restored-spec.json
```

输出一律新建，避免覆写基线、候选或证据。restore 只导出冻结 Spec 字节，返回原始资源基目录；建议与原 Spec 同目录导出。若原始源码后来修改，该 Spec 的旧摘要将使当前资源检查失败，应使用资源快照构建隔离恢复副本，而不能覆盖活动源码。此安全边界防止一次回退破坏当前工作。

## 测试和边界

单测覆盖参数驱动真实几何、父级变换、刚性允许与变形拒绝、冻结目标/阈值、拓扑重绑定、缺孔及反向法线、未知依赖全验、证据缺项/陈旧和非覆盖恢复。捕获验证器另做真实浏览器集成测试；本模块对其使用严格接口测试。跨对象造型和速度收益由开发回归与独立样例评估，不能由单测数量推导。

依赖现有 scene_build、production_checks、mesh_checks；刚性拟合使用现有运行环境中的 NumPy。没有自动安装、网络服务调用或发布操作。

## 消费端尺度保护

局部几何修复除已有世界几何保护外，按 [运行时尺度校验](runtime-guards.md#运行时尺度) 对照真实顶点边界、实际 accessor min/max、消费端归一化边界、root变换及固定机位。新增附件不能无意改变整车缩放、中心或接地；不能伪造过期 min/max 维持画面。若局部修复合理扩大边界，更新真实边界，并显式保留或重新确认展示尺度基准。
