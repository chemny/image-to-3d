# 连续截面、封边与转角施工

新建与修复共用本规则；对象可以是车辆、玩具、外壳或家具。只在参考和边界要求支持的区域使用。不得把所有设计硬边改成圆角，不用平滑法线冒充几何过渡。

## 制作顺序

1. 保留可重建基线。先通过参考覆盖，区分原图、已批准推断与未知；冻结本轮目标、保护件、机位及容差。
2. 把边缘标为设计硬边、平滑连接、独立装配缝或未知。记录轮廓、厚度/截面、根部、相邻面，以及支持它们的参考ID与像素ROI。
3. 按shape-foundation.md先确定整体形体。整体未通过时，转角样件仅用于构造可行性诊断；通过后再进入局部精修。为最难转角做局部样件。选择真实可控表达，明确边界位置、切向方向和厚度；不能只给“更圆滑”的文字指令。先做共享面，再贴灯、饰条等附件；变形后重新计算附件落点。
4. 编译实际网格，检查拓扑和声明的局部几何。原图角度检查轮廓，深度角度检查厚度/连接，再用掠射光和条纹反射检查折痕、鼓包、收尖。条纹只辅助观察，不能证明全局G2。
5. 比较保护区域与附属件，记录改善和失败。拓扑改变必须使旧索引证据失效；从recipe重建，不能偷偷修改最终网格。通过修复审查后才能采用，诊断预览不能替代生产验收。

## 通用构造入口

`form_construction.py`保留旧`loft`、`thick_outline`，并调用`surface_construction.py`提供下列方法。recipe仍为version 1、component_id、source:{reference_id,roi}、rationale、method、parameters；ROI是原图像素xywh。工具生成显式mesh，Three.js、资产导出和检查消费同一组几何。

| 方法 | 参数要点 | 几何与适用边界 |
|---|---|---|
| smooth_loft | sections:[{center:[x,y,z],radii:[rx,rz]}]，严格递增Y；max_chord_error；可选cap_depths | 标量自然/夹持C2样条连接平行椭圆截面。区间驻点检查半径为正；自适应误差只覆盖采样的纵向包络。圆滑椭圆端帽强制端点零斜率形成解析G1，不能同时指定end_slopes。任意轴架、全局自交仍需另查。 |
| rounded_outline | 星形XZ outline；rings:[{fraction,half_thickness}]覆盖0..1；edge_width；可选join_slope≤0 | C2厚度与C1保形周期轮廓；真实椭圆卷边，保留中面外轮廓。join_slope指定厚度对归一化半径的端点导数，按各方向真实半径匹配卷边切向，避免默认水平收口产生凸唇。它不是任意孔洞或恒定测地倒角。 |
| blend_strip | a、b边界曲线，以及a_inward、b_inward导数字段；segments:[nu,nv] | 沿边界样条和横向Hermite过渡。b_inward朝内，终端导数取反。导数长度控制过渡，不能只写方向；与邻面的连续性须另测。 |
| corner_patch | boundaries:{u0,u1,v0,v1}，各4个Bezier控制点；continuity | 四边兼容的双三次补面。position模式只保证边界；tangent模式须四组cross_derivatives朝内字段，矛盾控制条件直接拒绝，不平均掩盖。不支持任意多面节点或自动G2求解。 |
| rounded_corner | center、正radii、octant:[±1,±1,±1]、segments | 三个正交平面之间的椭球八分体，三角网格无塌陷极点。可与兼容椭圆柱面形成解析G1；不自动裁切或贴合已有模型。 |

采样增加用于实现已定义的曲面精度，不能替代错误形体表达。C2标量曲线或单个解析G1连接，不代表整件模型全局G2。相邻面未共享真实边界时，生成圆角工具也不能自动消除缝隙。

端帽需要先预留长度。cap_depths追加在首末截面外；要保持已确认顶端/底端位置，应缩回基础截面再接圆帽，不能在很细的末截面外直接追加而制造针尖。保护外包络时在surface_contract声明bounds:{min:[x,y,z],max:[x,y,z],tolerance:数值}，实际顶点越界即拒绝；这是局部坐标包围范围，不能代替完整轮廓及根部检查。

```sh
python3 scripts/form_construction.py recipe.json --out geometry.json --report compilation.json
python3 scripts/surface_construction.py recipe.json --out NEW-geometry.json --report NEW-compilation.json
python3 scripts/surface_quality.py --help
node scripts/capture.mjs --bundle BUNDLE --out NEW-CAPTURE --playwright-module PLAYWRIGHT --poses closed --modes beauty,zebra,grazing
```

两个编译入口都拒绝覆盖已有输出，使用新文件名保留基线。construction_plan仍管理recipe、参考ROI、保护件和局部检查，编译receipt现在包含被委托的曲面/网格工具哈希；任何相关源码变化都需从基线重新构造。

## 接入构建的曲面检查

显式mesh组件可以声明`surface_contract`，`scene_build`在实际构建时执行，失败即拒绝。不要在不支持的基本体或assembly上填写。它只使用组件局部坐标；跨组件世界坐标接合继续用装配/mesh_checks契约。

```json
{"version":1,"topology":"open_patch","profile_checks":[{"id":"rolled-edge","vertex_indices":[0,1,2,3],"max_turn_deg":12}],"seam_samples":[{"id":"join","a":[0,1,2],"b":[3,4,5],"max_gap":0.001,"max_angle_deg":8}]}
```

示例索引仅说明格式，必须替换成当前实际几何索引。profile路径须沿实际网格边；接缝三元组须分别构成实际唯一三角形，起点为采样接点。检查间距、真实三角面法向夹角、折转和离散曲率变化，忽略可伪装折痕的平滑着色法线。阈值按单位、分辨率和设计要求事先声明；没有声明阈值的指标只是信息，不自动成为美学通过。有限采样不证明全局G2、自交安全或还原。

### 曲率方向突变

复用现有 `profile_checks`，可选 `max_curvature_vector_jump`：至少四个真实边路径顶点，限制相邻离散曲率向量差的模长。向量为相邻单位切线之差除以两段平均长度，单位为 Spec 长度的倒数。指标只对当前采样路径生效，能补充 `max_curvature_jump`（无符号大小差）可能漏掉的弯曲方向反转。

例如 `{"id":"transition","vertex_indices":[0,1,2,3],"max_curvature_vector_jump":0.1}` 的索引和阈值需实际制定。指标在整体刚性旋转下不变，模型等比放大后按长度倒数缩小；不能忽略单位和分辨率复制阈值。圆弧的曲率向量本来会随切线转动，光滑 S 形也可能是设计特征，不能统一要求向量差为零。

未声明此上限时沿用旧行为，仅报告方向变化；不会自动磨平原有设计硬边。声明后复用 `surface_quality.inspect_geometry` 和 `scene_build` 的现有 surface_contract 构建检查，无需另建质量阀。新增上限不证明解析 G2、全局无折痕或与参考一致。

## 参考标定失败时

机位拟合必须把校准与留出分开，并保证校准位置分散；连续半边圆弧容易过拟合，平均误差小不能覆盖另一半的失败。轮廓极值随视角移动，不能假绑成固定顶点。轮圈、轮胎、轴距等粗比例分别核对；标定不通过先保留失败、诊断几何比例或可观测性，不提高容差，也不直接按个人理解采用修复。隔离样件可继续验证工具，但生产修复和还原验收仍须通过共同参考准入。

通用审查bundle支持内部捕获zebra与grazing模式，不增加产品页面按钮。前者以当前着色法线生成反射条纹，后者使用固定低角度侧光；二者都须配合实际三角面/边路径检查，不证明几何连续性。旧bundle或车辆自定义查看器不支持该API时会明确失败，不能静默捕获成beauty。使用当前通用诊断bundle验证，保留原配置器；默认捕获模式保持兼容。

## 局部变形的支撑域

曲面变形不能按“顶点是否恰好等于解析面”作二元筛选；开口裁切产生的插值点也必须连续变形。使用明确的连续支撑权重并同步关联边界/附件。实际网格上的法向突变、条纹和掠射光均需复验；参数函数连续不证明离散模型连续。失败候选保留，不能仅凭装配/保护检查通过采用。
