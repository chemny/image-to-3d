# 数据与来源契约（v2）

## 项目
保留旧字段，新增 `schema_version: 2`、`input_kind: model|images`、`inputs: [{kind,path,sha256,original_path}]` 和 `source_model`。`source` 仍指首张参考；纯模型任务指模型，图片 API 应先确认存在图片而非对模型上传。图片列表在 `references`，每项保存 angle、origin、path、sha256、note、consistency。初始化 origin=user_supplied 表示收到的文件，不能据此证明是真实照片；复核后登记 real/generated/inferred。生成图和旧任务中来源不明的参考不改写成 real。所有内部 path 相对项目；original_path 仅作溯源。

`project.py reference` 可向旧项目追加带哈希的参考，不强制迁移其他状态。已有 source/candidates/stages 由旧脚本继续使用。初始化不判断造型，不把 pending 改成 passed。

新项目 `limits.max_repair_rounds` 初始为 `null`，表示尚未按任务确定；正式修复前在任务卡与执行参数中写入有理由的正整数。已有项目的预算值保留。`delivery_acceptance` 可独立记录用户在已知视觉差距下接受某个案例最终稿的指令、资产哈希与未通过项，不更改 `validation.geometry` 或整车形似 verdict。

## GLB 清单与角色
`asset_manifest.py inspect` 只接收自包含 glTF 2 GLB；侧载或远程贴图须先另存为完整 GLB。本地嵌入贴图逐字节提取到 textures/，原 GLB 不改。输出 gltf-source.json 和 asset-manifest.json：

- asset：id、完整 sha256/version、source、bytes、license（未提供则 not_supplied）。
- coordinates：glTF +Y 向上；规范单位不证明源模型真实尺度，forward 需任务确认。
- bindings：`n<node_index>:p<primitive_index>`、实际节点/mesh/primitive、material_index、UV 集、局部 accessor bounds、计数、是否在默认 scene。局部 bounds 不等于世界尺寸。
- materials：完整源定义和 users；images：mime、提取文件、哈希；textures、动画和 required extensions。动画只盘点，模板不自动播放全部 glTF 动画。
- role/evidence、protected_features、runtime_dependencies、limitations、分别评审 verdict。

由代理看图/看资产后填写任务 roles.json，再以新输出目录重复 inspect：

```json
{
  "asset_id": "task-specific-stable-id",
  "forward": "+Z; verified from actual model",
  "roles": {
    "n4:p0": {"role": "paint", "evidence": "实际车身 primitive，查看原材质与多视角确认"},
    "n7:p0": {"role": "glass", "evidence": "透明窗片；禁止随车漆换色"}
  },
  "protected_features": [
    {"name": "window", "targets": ["n7:p0"], "recolorable": false},
    {"name": "handle", "targets": ["n4:p0"], "recolorable": true}
  ],
  "runtime_dependencies": [],
  "limitations": []
}
```

例中索引只是格式示例，不是模板车型值。角色可扩展。一个网格多 primitive、多节点同角色均支持；一个融合 primitive 内多语义区域不能由角色清单自动拆出，需要局部几何分件、遮罩或适配器和专门视觉验证。工具不根据颜色阈值自动宣布语义正确。

## 修复与质量
任务 repair-plan.json 记录问题类型、证据、允许区域/保护列表、源版本、动作、检查、最大回合与回退位置；阶段执行继续使用现有 parameters/job/result/review 契约。UV 和面材质槽纳入网格指纹；材质/贴图另有变更指纹和可选允许列表，动画及未覆盖的自定义节点属性仍需专门核对。不能只凭 unchanged_mesh_count 宣布全部受保护。

集中计划也可用 [optimization-plan-template.md](optimization-plan-template.md) 保存为任务 repair-plan.md；这是代理可读的计划，不是新增必填字段或执行器 JSON。记录最佳基线选择、复用/失效项、动作依赖、保护方式（不变/协调移动/允许重建）、任务阈值与反馈预算。执行仍用现有 parameters/job/result/review，旧项目无需为新流程整体迁移。

涉及正式形似验收时，另按 [optimization-gates.md](optimization-gates.md) 保存 optimization-plan.json、冻结 lock 和 optimization-review.json；optimization_review.py 检查样本独立性、关键覆盖及文件身份。它们是任务侧记录，不改变 project.json/Blender 执行器 schema；consistent 不替代视觉评审。

validation 使用 geometry / materials / function / performance 四项，各自 verdict（passed/needs_revision/not_verified）、scope、evidence、limitations。浏览器脚本验的是结构及交互，视觉由实际查看；真机性能单列未测。资产改动后哈希变化，必须新 version/绑定复核；旧选择默认拒绝，不偷偷迁移。

config_version 是 project.py web 对网页配置和资产清单计算的 SHA256；相同 GLB 的绑定、预设或运行时依赖改变，也会拒绝旧选择。本地保存键包含它，不静默把旧材质配置套到新资源包。

模型准备记录 preparation.json（来源/导出哈希、state、限制）和 .blend 的节点/贴图清单。派生 GLB 重新盘点并填写角色；缺贴图/库资产停止导出。网页 bundle-manifest.json 保存构建文件哈希，config_version 同时包含所复制资源内容；原件保持独立。
