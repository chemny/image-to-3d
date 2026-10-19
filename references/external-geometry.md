# 可重建外部几何验收适配 v1

适用于已有的可信本地 Python 生成脚本，不限对象类别。外部生成器仍输出 Spec 中的实际 mesh，不能另造仅用于评分的代理几何。此适配只补再生来源，不代替参考准入、截面、拓扑、装配、视觉、修复及交付门禁。

## 声明及执行

Spec.external_geometry.version=1，包含：component_ids（真实显式 mesh ID）、generator:{path,sha256}、inputs:[{path,sha256}]、parameter_components:{参数ID:[受影响组件ID]}、position_tolerance（最多1e-7 Spec单位）、receipt（项目内相对路径）。源码、全部输入及回执均登记 source_files 并核对实际字节哈希；参数必须有有限值和可变范围，每个目标必须有有效控制。

生成器协议：接收 --input REQUEST.json --out OUTPUT.json。请求包含 version:1、parameters（绑定参数的数值）、inputs（隔离临时副本绝对路径）、component_ids。返回 version:1、geometries:{组件ID:{type:mesh,positions,triangles,normals?,uvs?}}；不能增删输出组件或使用未支持字段。

先人工审查脚本来源和行为，确认在当前授权范围内，再显式运行：

```
python3 scripts/external_geometry.py --spec TASK/spec.json --allow-execution
```

普通 foundation-check、build 与 review 只核验登记回执，绝不隐式执行外部脚本。临时目录、Python -I 与环境精简用于输入可重复性，不是操作系统安全沙箱，不能据此执行不可信代码。

## 必需验证

1. 生成源码和输入身份一致；两次独立重建完全一致；不能修改源码或输入副本。
2. 重建输出与当前 Spec 实际编译几何匹配：字段、索引及拓扑一致；位置误差不超过预声明容差，法线/UV误差最多1e-9。检查非有限值、数组维度、索引和顶点预算。
3. 逐项扰动控制参数：实际改变组件集合必须与声明严格一致；死参数、遗漏影响、越界作用均失败。
4. 回执绑定契约、参数及当前实际网格；源码、输入、参数或网格变化后失效。整体形体身份同时绑定适配契约。
5. 原有真实截面/曲线绑定、结构距离、参考网格、真实多机位 mask 与外观审查继续执行。重建通过不代表照片1:1还原，也不证明全部曲面连续或无自交。

已有登记回执时用 --out TASK/replay-NEW.json 写新报告，不能静默覆盖。只有新报告通过且旧回执已归档后，才显式采用新报告到契约指定路径并更新 source_files 哈希；保留修复基线及历史证据。改变契约范围、源码或输入需要重开相应冻结范围与审查。

## 能力边界

本版不在 foundation-fit 搜索内部自动调用外部生成器。参数修改后必须先实际重建 Spec，再 replay、capture、compare、review。诊断包保持 diagnostic，不能仅凭 replay 通过变成正式交付。外部脚本未支持的平台/依赖不自动标为可运行；优先使用原生 Bezier/form_recipe。
