# 整体形体控制与验收 v1

新建与修复共用：参考/机位 → 结构控制 → 主曲面/拟合 → 整体验收 → 精修/整体回归。仍使用现有Spec、reference_plan与workflow；不增加独立的几何真值。技术、参考还原分别通过，任何关键失败不能由均分抵消。来源不足的深度/隐藏面是推断，生成参考不成为实物测量。

## 唯一控制数据

新init默认quality_contract.foundation_standard:1并创建Spec.foundation草稿。旧项目新一轮形体修改执行 `project.py foundation-prepare --project TASK --level global|region|detail|technical`；另存原Spec且清除旧批准，不编辑活跃发布页。旧项目仍可查看，不追认已符合标准。后续必须填写：

- level：错误属于整体、区域、细节或技术。phase：foundation或detail；整体未通过保持foundation。
- primary_components：决定整物体辨识度的实际组件。不能只列问题边框避开错误的主体；作者对范围语义负责。
- controls：id、kind:curve|section、真实mesh.vertex_index或Bezier.patch_id+uv bindings、reference_ids、parameter_ids、rationale。曲线至少4、截面至少3个分布采样；这只是最低门槛。可选max_turn_deg按设计预先声明，硬边不套用平滑上限。不得绑定自由local_point假标签或孤立顶点。
- relations：实际bindings的两点距离min/max，可核对宽度、厚度与部件位置；距离正确不证明全部体积正确。
- dependency_edges：[主体,受影响件]，包括必要边界、附件、装配与控制依赖。禁止环；遗漏依赖由作者审查，不声称工具自动发现。
- required_views：至少两个实际非平行的观察方向；只改变距离或前后反向的同轴机位不构成独立深度证据。这只是退化筛查，不保证可观测性；按参考覆盖选择，不强制汽车五视角。required_features列ID，feature_definitions逐项填写id、kind:outline|internal|volume|surface、criterion、reference_ids、view_ids；四类都要覆盖。
- scale_gauge：固定参数parameter_id（min=value=max）与reason。不从单图声称物理尺寸。
- 可选fit_curves：每项id、control_id、reference_id、camera_id、target_px折线、role:calibration|validation、sigma_px、tolerance_px。拟合真实物理特征曲线的双向加密折线距离；视相关剪影不得假绑固定点，仍用真实mask对照独立验收。本版不直接优化渲染蒙版像素。
- fit_groups：按proportion→curves→sections依次列parameter_ids，变量不重复；可以只用所需组。真实几何用原生参数引用，不能另造仅评分网格。

连续主体优先复用原生Bezier共边网络与连续截面。Bezier控制网直接参与scene_build，边界控制ID共用，原生构建检查声明的C0/G1/C1；物体的设计硬边保留。其他表达继续用现有旋转体、构造recipe等完成局部构造；本版整体再生与拟合支持原生Bezier网络和form_recipe，后者将已有连续截面/圆滑封边等recipe作为Spec.geometry直接编译成同一实际网格。参数引用先解析，再构建/投影；控制点必须绑定生成表面。可信外部 Python 生成器按 [外部几何验收适配](external-geometry.md) 显式双重再生、真实参数扰动与几何身份校验后，可接入来源门禁；仍需全部原有质量检查。其他未适配表达不静默认证。显式网格控制用于观察实际曲线/截面，不代表已经拥有可生成该形状的上层控制网。复杂网格需先建立可重建来源，不能仅补声明声称重构完成。

`shape_foundation.evaluate`从真实表面采样，报告折转、声明距离及身份；native Bezier另给解析一阶/二阶导数、法向与主曲率/曲率半径。符号由参数方向决定。显式网格不假报解析曲率。当前没有全局自交证明、任意轴放样或自动整物体G2求解；现有局部曲面工具边界继续有效。

## 工程入口

```
python3 scripts/project.py reference-grid --project TASK --reference original --pixel-step 50 --out NEW_GRID
python3 scripts/project.py foundation-check --project TASK
python3 scripts/project.py foundation-fit --project TASK --iterations 60 --out NEW_FIT.json
```

网格分析层与干净原图分开。覆盖网格用于防漏，像素网格用于定位，锚点工具用于实际投影差；都不能单独证明三维真值。红蓝绿对照使用project.compare；alignment同时登记reference_id和reference_image_sha256。相机/蒙版/模型身份核对不等于机位一定正确，正式参考匹配仍须共同参考准入校准锁。

拟合复用reconstruction有界坐标搜索，不安装新依赖。只调整真实几何控制参数，相机冻结；相机与粗比例仍混淆时先用coarse_initialization。至少两个机位的calibration与两个validation观测，每项绑定真实表面并声明tolerance_px；校准数据决定搜索，留出只在完成后判断。局部可观测性检查失败即停止。每步检查声明构造约束和受保护件；连续无改善报告需要诊断，不宣称最优。报告不自动采用。

## 整体验收和精修准入

先由project.build --diagnostic与project.capture生成当前真实WebGL截图和二值mask，再repair_capture.create生成身份回执。所有验收机位都要beauty与mask捕获及轮廓对照；双面mask有像素不能证明正常材质面可见，需实际检查朝向、遮挡和外观。内部、体积、表面逐项实际看图。只裁切或描线不增加深度证据。

单独保存与捕获同字节的 `accepted-foundation.json`（和spec.json同目录，资源相对路径不变）。whole-form-review.json包含：

- foundation_identity（foundation-check输出）、baseline_spec:{path,sha256}；技术与参考technical_verdict/reference_verdict、reviewer、notes。
- capture_receipt:{path,sha256}，真实当前捕获，不能把普通截图伪装成标准回执。
- results逐项{id,verdict,notes,view_ids}覆盖required_features及其全部观察视角；每项失败均阻止采用。
- grids:[{reference_id,path:相对grid.json,sha256}]，每个比较参考都具备像素网格。
- comparisons:[{camera_id,path:相对metrics.json,sha256}]，来自project.compare，蒙版像素必须等于回执对应机位的真实mask，模型必须是同一捕获bundle。

```
python3 scripts/project.py foundation-accept --project TASK --review whole-form-review.json
```

此命令核验身份和声明，不自动理解图片；填写pass不证明诚实评审。成功登记到project.json后才将phase改成detail。正式build拒绝无整体批准的detail；body及以后批准拒绝缺整体审查，诊断包仍不能交付。主体、控制、父变换、参考、观察标准或机位改变时旧批准失效；附件改变后还要现有装配与局部审查。整体身份缓存不代替当前捕获。

## 验证

用有真值的合成连续外壳测试参数恢复、解析曲率、共边失败和可观测性；故障注入覆盖错比例、局部顺滑但主体错误、留出泄漏、机位吸收、保护件改变、陈旧图与缺证据。真实超跑和非车辆另记软件、准入、还原与功能结果；开发案例不证明未见照片泛化。没有独立样本时第六阶段真实泛化验证保持pending，不虚报完成或自动选择新设计。
