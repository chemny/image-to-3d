# 验收与加工边界

优化验收按 [统一集中流程](model-optimization.md) 的优先级进行：整体比例/轮廓 → 分区结构 → 表面/特征 → 材质与运行。参考与相机先核对，已通过且仍有效的成果保留。低拟合点误差、材质更亮或网页可运行都不能提升未通过的整体造型。

正式集中优化按 [验收门槛](optimization-gates.md) 冻结目标并逐项复核；调参点不作为独立通过证据。完整外观验收覆盖屋顶/窗线、主体轮廓、轮系、灯具和特征位置及相关视角，局部数字合格不能推断整个车体。optimization_review.py 的 consistent 只表示记录一致，不自动认证高保真。

已有 GLB 默认先做原生清单检查，并在实际 Three.js 页面查看灰模与原材质：
`python3 scripts/asset_manifest.py inspect --input candidates/a/model.glb --out review/a-native`

需要 Blender 诊断或离线预览时使用：
`blender --background --factory-startup --python scripts/inspect_model.py -- --input candidates/a/model.glb --out review/a --render`

上述脚本只检查/预览，不改源模型；路线及持久化方式见 [tool-routing.md](tool-routing.md)。无论浏览器还是离线渲染，至少查看前、侧、后和主参考角。几何统计和多角度图是证据，不是自动高保真认证；原图匹配视角需按照片相机另行设置，不能直接用标准预览作像素对齐。几何修复交付需重新加载实际派生 GLB，或复核明确声明的运行时几何适配及其依赖。

外观：关闭贴图后看轮廓、窗线、轴距、灯腔、轮胎圆度、轮毂几何。面数高不等于形状准确。灰模严重错误不可用材质掩饰。
材质：车漆可独立换色，不带固定照片高光；玻璃与不透明零件分离；材质已在浏览器核对。
交互：四轮位置/尺度/朝向一致；门动画围绕真实铰链、无明显穿插；全景相机位置固定、无接缝、不跟随鼠标平移。
性能：目标手机/电脑分别测首屏时间、帧率、内存；按结果调整纹理与几何，不能仅报告构建成功。
来源：不可见部位、AI补图、概念内饰明确标注，不能包装成官方车型资产。

建议每个候选记录：verdict（pass/revise/reject）、证据图片、比例问题、零件可用性、加工计划及未验证区域。人工或视觉AI可辅助评分，但单图无法证明隐藏区域真实。


完整首版使用 [首版清单](first-version-checklist.md)，活动件使用 [交互契约](interaction-contract.md)，接缝与浮线使用 [接缝诊断](seam-diagnostics.md)；功能、造型及工程验证结论分开。
