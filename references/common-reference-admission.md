# 新建与修改共用的参考准入 v2

适用于车辆、玩具、家具、器具及其他对象。目标是阻止无依据施工与错误验收，不承诺从单图恢复遮挡面的真值。新建使用project.init的v2草稿；旧模型开始新修复也必须先补齐本轮v2准入。旧项目可查看、保留历史结果，不自动追认符合新标准。

## 一个入口，按风险补足信息

1. 声明create/repair、reference_match/design_change/technical_fix与具体goal。匹配参考任务不能改成“比旧版好”。repair明确affected/protected组件与未修改的baseline身份。
2. 以关键区域而非固定图片张数规划outline/volume/connection。逐项登记原像素ROI、可见性、能支持什么、不能支持什么。先复用足够的原图/旧参考；仅为缺口补图。裁切能增加可读性，不能提供新深度。
3. 原图、补图、当前设计版本分别登记。每个区域authority声明生效参考、revision和原因。新用户参考覆盖旧设计时，将旧参考保存在历史基线中，不继续混为同一目标。互相冲突的生效图先解决，不能让模型折中成第三种造型。
4. 原图不可见的新设计，先准备可审查补图再请用户确认；已有明确授权只核对对应图片身份，不重复询问。生成视图是获准设计假设，不能当观察真值。关键缺口写blocking_unknowns并阻止施工，低风险未知写uncertainties及影响范围。
5. 参考准入通过后，可先建立用于比例/机位判断的粗体，并以诊断方式渲染；它不代表正式施工或还原通过。再校准相机、锁定关键特征/截面/连接，随后冻结修复契约。变更目标、机位、容差、范围是新实验，不能混进已冻结会话。

技术修复也需目标/范围与参考覆盖，但可复用已有设计资料与当前几何；工具逐编辑组件比较实际世界三角形表面（坐标量化到1e-10米），允许顶点编号重排/法线修复，不能改变形状；不强制重生多视图。根部不存在接合时connection证据明确说明“独立整体，无外部接合”，不虚构关节。仅凭单图无法确定的隐藏结构不能通过人工一句“合理”变成真实还原。

## 文件与命令

继续使用同一reference_plan、Spec与state，不建立第二条审批链。详细原图/生成图来源和用户批准格式沿用reference-set-standard.md。新建默认生成version:2草稿；旧工作项目明确迁移：

```sh
python3 scripts/project.py reference-prepare --project TASK --mode repair --intent reference_match --goal "匹配已选参考的关键形体" --affected PART_A PART_B --protected PART_C
python3 scripts/project.py reference-check --project TASK --stage references
python3 scripts/project.py reference-check --project TASK --stage spec
python3 scripts/project.py repair-start --project TASK --contract CONTRACT --out NEW_SESSION
```

迁移只生成待填写草稿和不可覆盖baseline，清除阶段批准并保留历史。已附加冻结会话的工程先复制为新工作工程，核对资源相对路径、清除复制的会话/批准后再迁移；不能更改活跃发布页。prepare不授予任何参考或质量批准。v2诊断build也要求参考集准入已完成，不能用--diagnostic绕过图片准备。重复prepare拒绝覆盖。repair-start/attach先校验v2与契约范围、基线几何，失败时不开始施工。

plan.task包含mode、intent、goal、affected_component_ids、protected_component_ids、baseline:{path,sha256}。每个critical_components区域在v1字段之外添加：

- blocking_unknowns：阻止本轮可靠施工的问题；准备完成时必须为空。
- authority:{reference_ids,revision,reason}：本轮依据，不以文件时间自动判断优先级。
- evidence：每项有purpose:outline|volume|connection、reference_id、roi:[x0,y0,x1,y1]、usable:true、visibility:visible|approved-inference、claim、limitation。**这里ROI是端点格式，旧Spec.observations的[x,y,w,h]字段按原契约使用，不能混用。**
- features：唯一id、kind:point|curve|section|connection|smooth_join|visual、component_ids、reference_ids、criterion、severity:critical|supporting。全部声明特征都必须通过，不以severity豁免失败。数值项另有bindings、target、max_error及point/curve的camera_id；人工项须manual_reason说明无法数值量化的原因，review_camera_ids登记上下文/深度观察机位；reference_match/design_change仍需camera_id和校准锁。

bindings只能指实际mesh.vertex_index或Bezier.patch_id+uv，带component_id。不得创建与模型无关的local_point用于形状评分。对真实旋转中心等解析结构点可继续用既有观察契约作诊断，但不混入新版形状数值认证。拓扑重建后按construction_plan重新绑定并明确旧检查失效，不能保留编号假装语义相同。校准点优先放在受保护且可靠的实际结构上；若其语义绑定也须变化，应重新做机位/基线实验，不能借特征重绑修改锁定锚点。

## 机位、约束和施工

plan.calibrations按camera_id登记reference_id、method:landmarks|known-camera|geometry-curves、calibration_ids、validation_ids、max_error_px、rationale、uncertainty、reviewer。锚点须绑定可靠实际几何，覆盖分散位置，校准组和留出组分开。当前锁定工具最少4个校准、2个留出点及横纵分布检查；这只是最低软件门槛，不保证透视参数唯一。共面、遮挡、错误语义或不可靠主体尺寸需先诊断，不用宽容差凑过。

针对相机使用shape_acceptance.fit-camera检查局部可观测性并仅拟合相机参数；实际几何只构建一次，迭代复用其绑定点。一般形体参数继续用reconstruction.analyze/fit。所有搜索只用校准点。相机拟合只允许相机参数，验证实际组件/材质/动作保持不变；留出点不能参与搜索、候选排序或容差选择。拟合结束且语义检查通过后：

```sh
python3 scripts/shape_acceptance.py fit-camera --spec TASK/spec.json --camera VIEW --parameters CAMERA_X CAMERA_Y --out TASK/camera-fit-new.json
python3 scripts/shape_acceptance.py lock-camera --spec TASK/spec.json --camera VIEW --out TASK/locked-plan-new.json
python3 scripts/shape_acceptance.py check --spec TASK/spec.json
```

拟合报告输出候选Spec与参数、校准及留出残差，不自动改变工程；检查候选后采用参数，再锁定计划。参数若影响实际几何/材质/动作或其他机位，拟合入口拒绝；局部雅可比不满秩也拒绝，不能把数值迭代当作相机真值。

锁定命令输出新plan，不暗中覆盖工作依据。确认输出后采用plan并更新source_files hash，再进入repair-start。锁身份包含解析后相机、参考图hash、观测目标/绑定/角色、实际锚点世界坐标和阈值；改变后失效。

point检查投影位置；curve检查实际几何点链与参考像素曲线的双向采样距离；section检查世界坐标截面点链；connection检查两个真实几何点间距；smooth_join使用两个相邻面的六个真实采样点，同时检查位置max_gap和法向夹角max_error（角度）。这只是声明位置的采样连续性，不能当整个接缝的G1证明；设计硬边不套用smooth_join。截面深度和物理尺度从可靠资料或批准的假设得到，记录其不确定性，不能凭单图认定毫米精度。采样曲线不是整个曲面的数学证明。视相关外轮廓使用当前mask红蓝对照和局部视觉检查，不把剪影上的像素强配到固定顶点。

先执行shape-foundation.md的整体验收；整体未过时局部样件仅用于构造可行性诊断。整体成立后，对最难且最影响辨识度的区域做局部样件，按form-construction.md选择表达；无法表达时换构造方式，不能只加细分。继续用既有construction_plan、Bezier共边与mesh_checks，不重复建一个只服务车辆的构造器。声明平滑接合才检查位置/切向及掠射光；设计硬边保留。开孔、内衬、接合和开合动作要看实际几何与多角度捕获。

## 采用与效率

body及后续阶段在原workflow审查外自动重算数值特征，并要求shape_review：intent、technical_verdict、reference_verdict、capture_receipt，以及逐特征{id,verdict,notes,camera_ids,reference_ids}。capture_receipt由既有repair_capture.py从真实当前浏览器捕获创建，作为审查的哈希artifact；每项核对生效参考与当前机位。人工结论不能覆盖数值失败；数值通过也不会自动获得视觉批准。

保护范围、当前资源与捕获身份、局部影响回归继续由既有repair/production检查执行。多方向体积、表面和连接审查沿用production_contract及production_evidence；只检查声明的连接采样点不能声称全面无穿插。每轮只修有证据的首要误差，记录原因(camera/representation/section/connection/shading)、改变项、结果及回退点；连续无改善时重审对应关系和表达，不盲目重复。

真实特征批量解析组件树，减少重复处理；修复几何缓存仍按当前内容身份，不能复用陈旧图片批准。restore输出新工程、复制冻结参考证据且清除批准；含复杂construction_plan的恢复使用既有自包含export基线。材质颜色放在形体通过之后，固定光照、曝光和色彩条件再核对，禁止用光影掩盖结构误差。

## 验证边界

软件正负例：缺参考/ROI错/版本冲突/目标变更/机位漂移/伪评分点/范围扩大/实际几何偏移/陈旧捕获/回退重定位。真实案例：黄色超跑与非车辆对象分别记录准入、校准、造型与技术结果。开发案例可验证通用规则能执行，不能当未见样本泛化证明。时间统计必须覆盖参考准备、建模、修复与审查；未做同条件实验不宣称效率提升百分比。

## 冻结后的合法特征重绑

仅当冻结修复contract已声明allow_feature_rebinding:true，且目标组件真实拓扑改变，才能更新数值features.bindings。task、authority、target、max_error、calibrations及其他计划字段逐项保持原值。原始冻结计划继续保存在会话资源快照，当前计划仍须source-hashed，旧捕获与批准失效。

project.json.reference_binding_review指向{path,sha256}，该回执及其artifact均须登记在Spec.source_files。回执version:1、baseline_plan_sha256、current_plan_sha256以及features列表恰好覆盖每条变化的绑定。每条包括id、old_bindings、new_bindings、method:semantic-review、verdict:pass、reviewer、notes、artifacts以及geometry_sha256（reference_admission.identity(scene_build.resolve(spec.components,spec.parameters))）。

工具检查实际拓扑改变、原新绑定身份、当前几何及证据hash；语义对应仍需实际审查。普通位置调整不能当重新标注理由，不能把失败目标绑定到无关邻点。缺授权或涉及目标/机位/范围变化时，建立新会话。直接调用底层check同样检查冻结计划；底层review也要求独立造型验收。

### 先粗初始化再进入修复

当原生比例与机位混淆时按[联合初始化](coarse-initialization.md)先单独验证并冻结数值基线，再将它作为本轮repair的不可变baseline。geometry-curves使用`shape_acceptance.py lock-curves --spec SPEC --camera CAMERA --contract JOINT --fit-report FIT --resource-root RESOURCES --out NEW_PLAN`，独立复算候选后锁定真实网格边、源图描点与机位，禁止伪装成固定顶点对应。此后仍按原有参考准入/修复契约/逐项视觉检查执行。
