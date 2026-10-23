# 可执行的特征与安装关系保护

用于局部改位、融合车身大面修形以及曾发生门缝/窗线回归的任务。先区分独立构件、融合载体、几何边界和 shader/UV 表达的缝线；对象仍存在不等于边界受保护。

## 选择与施工

从实际网格、角色绑定和当前材质代码识别特征，记录来源、坐标空间及顶点索引。不要从名字自动推断整车分区。重复 UV 顶点属于不同实例，均须保护；材质画出的门缝也会随载体变形，不能因为没有独立缝线对象就漏检。

独立构件位置有误且载体可信时，优先在原载体实际表面重新安装：保持构件 footprint、边缘/厚度，按真实载体相交或可信采样重建安装接触，同步移动密封圈。旧安装区是否有残留凸起、孔洞或语义标记必须检查，不能只改独立部件的 transform。

先检测目标 footprint 与门缝/折线的冲突。依据参考标注精度可在预先声明的允许区间选择不冲突的位置；超出区间仍冲突时回到特征对应/载体分区，不把位置强拉到单个像素。三角射线投影若 miss、多壳歧义或存在旧面交叠，应停止并处理支持条件，不增加偏移掩盖。

必须修改载体时，冻结真实门缝、窗线、轮廓及锐边，允许域应避开这些域或明确指定整片结构的协调变换。窄域大位移可能扭曲近邻缝线；加宽过渡只解决压缩程度，不能自动解决结构回归。任何保护冲突均须先诊断方法。代表区数值与原材质/灰模视觉通过后才扩展。

## 原生 GLB 的确定性检查

`feature_guard.py` 使用已有 numpy，适用**拓扑、primitive/顶点身份和节点矩阵不变**的属性加工；不支持 sparse/normalized 属性、拓扑重建或重新导出索引映射。其他路线应另存映射或以 Blender 分区/重新绑定评审，不绕过身份检查。

```sh
python3 scripts/feature_guard.py freeze --baseline TASK/input.glb --spec TASK/features.json --out TASK/features.lock.json
python3 scripts/feature_guard.py check --lock TASK/features.lock.json --candidate TASK/output.glb --out TASK/features-review.json
```

freeze 在加工前保存 spec 内容哈希与 baseline 哈希，lock 与 spec 同目录；写出文件不覆盖。check 返回0=passed，2=needs_revision，1=身份/契约错误。目标是检查明确选择的结构与资产约束，不是自动识别、修形或照片认证。

spec schema_version=1，baseline_sha256、evidence 必填，坐标和量纲均为 GLB accessor 的本地 authored 空间；所有节点/层级必须保持不变。阈值按当次尺度与测量精度确定。

| 字段 | 定义 |
|---|---|
| allowed_changes | bindingID（n索引:p索引）→{max_displacement, optional indices:[顶点]}；未声明 binding 默认所有属性固定；声明后 POSITION/NORMAL 可变，UV/其他属性仍固定 |
| fixed_regions | [{id,binding,indices:[顶点],tolerance,evidence}]；明确保护边界带，保证选择非空、有来源；这些域在 allowed binding 内也优先保护位置及原法线，防止位置不变但反光/锐边被改坏 |
| clearances | [{id,moving_binding,fixed_region,axes:[0..2],minimum,evidence}]；全部构件顶点与保护带顶点的最小采样距离；二维仅表示该投影平面中的样本间距 |
| centroid_relations | [{id,a:binding,b:binding,axes:[0..2],maximum}]；如把手与密封圈在安装平面中的中心关系 |

检查 nodes/材质/图片/UV/索引、允许域外位置及法线、固定特征位移与法线、单位法线、间距与组装关系。固定区域按模型当前真实顶点选择，车型坐标/材质名不进入工具。节点矩阵、拓扑或角色变化需重新审查，不延用旧冻结结果。

采样间距不能证明面内部无自交；质心关系不能证明整圈密封贴合。另需安装面接触、构件尺寸/方向、面退化/绕向、连续性、同机位相关视角、原材质与灰模视觉检查。用 optimization_review.py 作为 required_checks 的一项并不取代这些验收。

跨案例报告分别注明真实/生成参考、输入是否人为加错、是否使用历史底模。已有真实模型上的人为缺陷恢复可以验证方法和保护，不能宣称恢复了未知实车形状。无底模图片先完成可信主体候选并进行独立视图验收，未通过时保留区域结论，不晋升为高保真整车。

每次流程升级至少覆盖：无需修改的可信输入、带明确注入缺陷的输入、融合材质域输入、无历史底模的图片输入。记录自然缺陷与人为注入的区别；同一车型的不同拓扑不是多个独立车型。分别统计资产保护通过率、真实建模首轮通过率、反馈修复轮次与回归次数，不合并为一个“成功率”。图片构建只读取图片观察与相机证据，评估用的可信几何不可偷偷作为建模底稿。失败门禁被正确触发属于验收机制通过，模型本身仍未通过。
