# 人工锚点与相机拟合

在原图和模型相机未对齐时，用 `fit_camera.py` 为诊断对照拟合视角。它自动优化已有对应点的相机参数，不会自动找特征、分割轮廓或修改车体。一个小投影误差不能证明整车或隐藏结构准确。

## 输入与执行

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/fit_camera.py -- --model <GLB或blend> --reference <独立参考图> --anchors <任务锚点JSON> --out <新目录> [--render]
```

对应点由代理看图、检查模型后填写。schema_version=1；asset_sha256 / reference_sha256 必须匹配当次模型和图；reference_origin=real/generated/inferred/user_supplied。anchors 至少六个不同点，每个 id、world（三维 Blender 世界坐标，+Z 上）、pixel（原图左上原点像素）、evidence，可选正 weight。使用独立部件中心或确切可定位顶点，覆盖多个方向和高度；不要把模糊反射、遮挡边界或不一致配置当确定对应。重复点、共线点、陈旧资产/参考哈希拒绝；近共面的点对深度约束弱，需要复核，不能只看 optimizer 结束。

拼图可给 reference_roi=[x,y,width,height]（原图整数像素范围），仍传未经改动的原图。所有输入 pixel 均为原图像素；工具转为 ROI 局部坐标拟合，报告同时保存 observed（ROI 相对）与 source_pixel（原图）。对照 SVG 只改变显示范围，原图字节保持，输出渲染/流水线分辨率按 ROI；ROI 不自动证明该视角为正交。

validation_anchors 可另给未参与优化的对应点，字段同 anchors，不使用拟合权重。ID 及三维点不能与拟合点重复，也不能只换名字复用。报告单独给验证误差；有验证点时需要满足 max_validation_error_px（缺省沿用 max_anchor_error_px）才能标 aligned。这只是该批独立人工点的相机诊断；点位误差可混合形状偏差，仍不证明整车准确率。拟合点与验证点应在开始优化前选定，不为通过而事后删点。

camera：初始 position、target、type=PERSP|ORTHO；PERSP 给 lens（mm，默认50），ORTHO 给 ortho_scale。图像像素比1、主点固定图像中心，sensor_width=36，sensor_fit=HORIZONTAL；裁切、镜头畸变和偏轴摄影不自动估计。初始机位须合理，不能期待一次数值优化从任意错误姿态找到正确相机。初始近似正侧图可尝试 ORTHO，透视照片不能默认当正交蓝图。

可设置任务 max_anchor_error_px（人工标注精度与任务目标决定），缺省只标 needs_review，不自动判通过。默认80次迭代，可用 --max-iterations 指定1..200；镜头/缩放和姿态调整有范围，输出实际误差及 Jacobian 秩。达到锚点阈值、参数可约束并且对象包围盒投影在画面内时只标 aligned，作用域仍仅相机，不是 geometry passed。

## 输出与后续

- camera-fit.json：来源哈希、初始/拟合相机、每点观测/投影、RMSE/最大像素误差、秩与画面覆盖。包围盒覆盖是保守检查，不是轮廓相似度；越界或参考/模型形态差异仍要评审。
- comparison.html：原图与标注/投影点叠加，查看误差集中在哪里。
- pipeline-view.json：可以把 view 合入任务 parameters 的 views，采用其 resolution；包含显式 rotation_euler、sensor_fit、sensor_width，流水线支持这些字段，不丢掉拟合的滚转。
- 可选 initial-clay.png / fitted-clay.png：同一材质/灯光，仅相机改变；不修改源模型，不保存覆盖源文件。

先检查人工点是否选错/配置不一致，再区分相机误差与真实形状偏差；不能为了低残差把错误车型特征硬拉到点上。拟合视角进入 Blender 阶段后依旧 awaiting_review，不能替代几何评审。多图须逐图登记来源和相机，不把不一致视图强塞给同一个几何。
