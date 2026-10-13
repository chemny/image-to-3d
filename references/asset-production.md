# 可编辑资产施工

用于需要选件、换材质、替换件、拆解或动作的产品资产。先冻结用途与参考，再建立 `asset_contract.version: 1`；旧 Spec 无此字段仍属 legacy，不能因兼容构建成功而称为专业资产。

## 输入与施工选择

记录原图文件身份、可见面、遮挡、参考来源、实测尺寸及比例锚点。`units_source` 只选 relative/measured/inferred；由照片估算的米制数字仍是 inferred。保留原图，生成补图注明生成来源和推断区域；生成的背面不能充当真实背面的验证真值。多视角先检查是否属于同一设计，再标定相机与透视；结构矛盾需解决后再细化。

先按功能装配及可见分界拆件，再选形状表达。下列是选择依据，不是强制固定模板：

| 对象/局部 | 优先表达与检查 |
|---|---|
| 汽车连续外覆盖件 | 共享边界的曲面网络或可控显式网格；先校轮廓、曲率与高光，再做门缝、内衬、真实枢轴 |
| 自行车车架与轮组 | 管状骨架和截面控制；检查轴距、头管角、节点连接、辐条与轮胎截面，避免用车身曲面套用 |
| 摩托车 | 管架/机械体与整流罩分别表达；先校轮轴、转向和悬架空间，再处理壳体曲面及装配间隙 |
| 玩具或一般产品 | 遵循实际分模线、铰链、关节与壳体；旋转对称件用旋转体，有机轮廓用曲面/显式网格，盒状功能件可用基本体 |

基本体用于匹配形状和早期体量，不以增加数量代替轮廓识别。需要贴图的部件使用显式 mesh 与逐顶点 UV，或使用生成器提供 UV 的 torus/tube；其他没有 UV 的形状先完成几何再显式展开，不能静默忽略贴图。模型精细度服从目标画幅、观看距离和用途。

## Spec 约束

`asset_contract` 声明 object_class、intended_use、units_source、required_components、required_operations、delivery_targets、source_notes。类别支持 generic/car/bicycle/motorcycle/toy；用途支持 display/configurator/disassembly/animation。required_components 非空且指向实际 ID；操作按用户需求填写 select/material/variant/explode/action，可为空；交付目标在 threejs/glb/blender 中选择。source_notes 明确已知与推断，不把填写文字等同于核实证据。

- 每个组件有稳定 ID、语义 role 和无环 parent；`kind: assembly` 只承载变换与子件，不承载几何和材质；默认 kind 是 part，必须有 geometry 和主 material。
- selectable 显式为布尔值。material_slots 是槽名到已定义材质 ID 的映射，主 material 保持实际网格材质；换色只作用于目标部件，不改共享全局材质。需要多材质面组时拆成子件，不伪造当前契约未定义的面槽绑定。
- explode_vector 使用有限 XYZ 数值，拆解前保留装配变换。action 绑定实际组件、轴、局部 pivot 与非零 angle；装配节点动作影响子树，必须检验全程而不只看终点。
- variants 每组有唯一 id、至少两个命名 options 与有效 default；每个 option 是非空根节点 ID 列表。根及其后代在所有选项/组之间独立，不能让父子分别被不同开关控制。
- 每个材质明确 source.kind（reference-inferred/measured/designed）和 source.note。maps 支持 map/normalMap/roughnessMap/metalnessMap/aoMap/emissiveMap，含资源根内相对 path、64 位十六进制 sha256 与 color_space。颜色/自发光用 srgb，数据贴图用 linear。元数据校验不检查文件字节；交付校验必须检查实际哈希、UV和资源加载。

## 校正与交付

先验证参考身份、相机、坐标与比例，再从主体轮廓 → 关键件相对位置 → 局部曲面/高光 → 材质与灯光迭代。每次记录改动、误差变化和剩余问题；冻结留出机位，不能通过改目标标注或阈值制造改善。若连续迭代无有效改善，诊断错误部件语义、遮挡不可观测、相机偏差或曲面表达不足，再决定补参考或换表达。

使用同版本 Spec 生成 Three 场景与 GLB；Blender 目标必须真实导入检查后才能称可用，未提供或未验证的编辑工程不能声称已交付。记录哈希、资源清单、部件/材质/动作/相机与变体保留情况；变体可见性及特殊材质需在目标应用复验。最终按 [资产验收](asset-acceptance.md) 分类报告，不承诺任意照片高还原、不可见结构准确或固定时间一次成功。


## 四部分交付清单

1. **来源与可编辑施工资料**：原始/批准参考、analysis、Spec、参数、部件语义、材质来源、推断与质量合同。export保留 reviewed-spec.json，并提供重定位的rebuild/spec.json及配套toolchain；重定位副本重新起未批准状态，不能冒用原路径证据。
2. **模型与资源**：scene.json、GLB、默认可见零件、UV/法线/贴图、材质、层级、枢轴和动作。完整备选件在Spec/Three工厂；通用GLB不自动提供交互换件。
3. **Three运行与展示**：model.js、Three依赖和许可、相机、通用操作检查界面；车型可另接已锁定配置器，保持已批准版式。
4. **验收与交接资料**：参考对照/红蓝差异、功能报告、真实导入报告、哈希清单、未验证事项与复现命令。分别列视觉、功能、交换和设备性能结论，不用一张截图替代全部验收。

以上是浏览器展示/可编辑资产生产规范，不冒称已具备机械制造级CAD、骨骼蒙皮、布料仿真或DCC原生修改器历史。新增对象的特殊需求先纳入合同，再按实际目标实现和测试。
