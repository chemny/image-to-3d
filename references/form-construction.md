# 参考特征到可重建几何

用于关键局部“位置接近但形状仍不像”的问题。先读图和参考集，再选构造方法；工具不从照片自动推断真实深度。简单规则零件继续用已有基本体，复杂连续车身可用Bezier网络，不强迫所有对象走同一种方法。

## 先决定构造，再精建

对影响辨识度的区域记录：reference ID与原像素ROI；可见轮廓及凹口；厚度峰值/收窄位置；根部与相邻部件的关系；几何方法及选择理由；可调参数；保护组件和原图/深度机位。隐藏厚度写为推断，生成补图只约束已批准设计。

| 观察到的形体 | 优先表达 | 不适用时 |
|---|---|---|
| 沿主轴连续变宽、收窄、弯曲 | 截面放样；曲线轴需明确截面坐标架 | 分叉或截面自交改用曲面网络/可重建体积融合 |
| 厚片、叶片、翼片、鼓起面板 | 平面轮廓+径向厚度分布 | 非星形轮廓、孔洞、反折须换表达 |
| 多瓣且共根的体量 | 明确各瓣轮廓、鞍部和共同根部 | 不把相互穿插的球体当连续融合 |
| 独立装配件 | 独立组件、接合面与运动轴 | 几何相交不自动证明装配合理 |

选方法看轮廓、截面及连接是否能被直接控制，不看代码最短。若连续两轮同类误差没有改善，保留证据后重审表达方式和对应关系，不靠继续细分或重调同一位置参数。

## 已实现的构造器边界

`form_construction.py`确定性输出既有Spec支持的显式mesh；Python和Three消费同一组顶点，不新建一套评分几何。

- `loft`：沿严格递增Y方向的截面中心放样，各椭圆截面平行XZ平面，可有X/Z偏移。通过组件变换放置到对象上。它不是任意曲线的平行移动坐标架，也不自动解决大幅弯折或全局自交。
- `thick_outline`：围绕原点按角度排序的星形XZ轮廓，配径向厚度环。上下表面和侧面构成闭合网格；可表达浅凹口和厚度变化。非星形、带孔、分叉融合不在此构造器能力内。可选inner_outline_ellipse:[rx,rz]及outline_influence_power将内部椭圆截面渐变到原轮廓，让边缘凹口不过度延伸到中心；外轮廓保持不变，内部环交叉会被拒绝。
- 参数是作者从参考拟定的形体假设。编译、闭合和法线通过都不等于照片造型通过。

不要把不支持的结构强塞进构造器。可以通过现有外部作者脚本产生显式mesh，但须保留可重建来源和局部检查，不能声称经过本编译器的参数一致性验证。

## 局部样件及装配验收

先构建最难且影响辨识度的局部样件，检查原图角度、一个能看到厚度的角度、根部上下文，再装配回主体。保护相机、材质与无关组件。改拓扑后旧vertex_index观测不可直接沿用；重新确认语义顶点或明确保留人工轮廓约束，不能删除失败测点后宣称全部通过。

每个关键区域在Spec.checks登记body阶段必需视觉项。每项同时覆盖：

1. 原图轮廓、凹口数量/相对位置和可见遮挡；
2. 侧面厚度峰值、截面变化和分瓣体积；
3. 根部接合及邻近件，无新悬空/穿插；
4. 被保护组件、相机与材质未发生非预期改变。

数值锚点仅覆盖其对应的结构点。位置达标不能覆盖脚趾圆球化、翼片变薄或根部断开。全局IoU不能抵消关键局部失败。多个方向发生矛盾时先审查相机及补充参考的设计一致性，不独立“优化”每个截图。

## 修复与效果测试

先记录原因(camera / placement / representation / thickness / connection / shading)，再改对应层。构造器参数变动后重编译、重建、重拍，旧证据失效。禁止直接修最终mesh再保留旧recipe作为来源。

开发测试冻结参考、相机、材质和保护件，分别记录首个样件、修复轮次、实际耗时及失败项。检查自动构造的有限值、法线、闭合拓扑、参数改变是否真的改变目标截面；人工检查造型。用未参与方法调试的新对象做独立验证前，不宣称适用于所有对象、一次成型或已提升速度。

## 执行入口和构造计划

独立编译（只生成几何，不做参考真实性认证）：

```sh
python3 scripts/form_construction.py recipe.json --out geometry.json --report compilation.json
```

在已有Spec上试验局部，输入和输出Spec须在同一目录，输出必须是新文件：

```sh
python3 scripts/construction_plan.py apply --spec baseline.json --plan plan.json --out candidate.json
python3 scripts/construction_plan.py check --spec candidate.json --stage spec
python3 scripts/construction_plan.py check --spec candidate.json --stage body
```

plan版本1包含parts、protected_components、protected_views。每个part可显式声明transform:{position,rotation,scale}改变目标件放置，scale须正值；无关组件保持不变。每个part包含id、component_id、inline recipe、outline、thickness、root、method_rationale、parameter_links（feature与parameters内真实parameter_path）和local_checks。recipe为version:1、component_id、source:{reference_id,roi}、rationale、method、parameters。用相同目录的新candidate保留已有相对资源路径；工具保留baseline快照和构造receipt。

每个part需至少两个已声明机位的局部检查，分别记录outline/volume/connection。初始status为pending；填写pass/fail时必须附reviewer、notes、evidence:{path,sha256,geometry_sha256,camera_sha256}。hash采用构造脚本digest函数的canonical JSON。检查的是声明和来源一致性，图像是否真正达标仍由实际观察判断。

改变拓扑的目标组件若有旧观测，apply要求明确列出invalidated_observation_ids并从candidate删除。必须在报告明确哪些旧检查失效；不能用剩余测点声称原检查全部通过。当前工具不支持自动语义重绑定，完成新标注需后续独立重建版本和审查。

candidate声明construction_plan后，workflow.validate_spec自动检查实际几何与recipe、保护件和来源；body及后续阶段批准还要求局部检查完成。阶段视觉证据仍由原有workflow核验，不因编译成功而自动批准。已有不使用构造计划的资产保持兼容，不追认通过该工具。

应用后若要修改构造参数，从同一baseline使用新plan输出新candidate；禁止直接改生成顶点。更换保护机位、材质或其他部件是另一项实验，应建立新基线，不能混入同一次构造效果比较。
