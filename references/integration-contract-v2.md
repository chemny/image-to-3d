# Unified implementation contract v2

Existing workflow.py envelope remains schema_version:1. New fields optional to workflow validator but mandatory for reconstruction tools. Components: id,parent,role,material string,geometry,position default[0,0,0],rotation default[0,0,0] XYZ radians. Every scalar throughout geometry/transforms/cameras may be numeric or {"param":"parameter_id","scale":1,"offset":0} (scale/offset optional finite scalars); resolved from parameters[id].value. Parent transforms apply, rotations XYZ in Three Euler semantics. Fixed units and axes: +Y up, +Z forward for built-in adapters, meters or relative; other coordinate systems must be converted explicitly.

materials dict id->{color hex string,roughness,metalness,optional clearcoat,transmission,opacity,emissive,emissiveIntensity}. Geometry: box size [x,y,z]; sphere radius,widthSegments,heightSegments; cylinder radiusTop,radiusBottom,height,radialSegments; mesh positions flat,triangles flat; lathe profile [[radius,y]...],segments; bezier_network network same explicit contract as bezier_network.py, scalar paramrefs supported in control positions. No silent box fallback. component topology_contract open_patch|closed_shell used for explicit mesh checks when available.

scene_build.py: resolve(value,parameters); landmark(spec,observation)->world xyz; build(spec)-> serializable scene payload; emit_js(payload)->ES module factory; CLI SPEC --out JSON --js MJS. Landmark binding: component_id with either local_point:[x,y,z], vertex_index (mesh), or patch_id+uv:[u,v] for bezier_network. geometry is model authority, not independent 3D point labels. Agent writing scene_build owns it and test_scene_build.py only; can add asset runtime module when needed.

cameras dict camera_id->{type:perspective|orthographic,width,height,position:[x,y,z],target:[x,y,z],up:[0,1,0],fov_y_deg (perspective),ortho_height (orthographic),near:.01,far:1000}; scalar paramrefs allowed in camera positions/targets/FOV. image origin top-left. observation{id,reference_id,feature,parameter_ids,component_id,binding as above,camera_id,target:[px,py],role:calibration|validation,sigma_px>0,optional protected:true (calibration only)}. Camera source metadata records inferred/calibrated; numeric fit not automatically certified calibration.

reconstruction.py owned by fitting agent: project(point,camera); predictions(spec,role)-> dict obs id {predicted,target,error_px,normalized_error}; fit(spec,parameter_ids,iterations)-> report{spec,initial/final objective,calibration/validation errors,journal,limits}; bounded param search uses calibration only, actual scene_build.landmark and rejected invalid geometry, no silent target synthesis. CLI analyze,fit. Reference analysis manifest validation can be separate reference_analysis.py same owner. No dependency install; existing NumPy/Pillow available if needed but declare.

actions optional list {id,component_id,axis:x|y|z,angle radians,pivot:[x,y,z] in parent's coordinates}; runtime parts keyed id group/axis/angle/value/target, build uses pivot group preserving closed position. Vehicle bindings explicit: paint materialIDs,wheels component groups per variant, lights emissive materialIDs,actions ids; no unsupported fake interaction. Generic viewer uses buildModel; locked configurator adapter returns buildVehicle exact contract. Tools build ONLY new output dirs.

Root owns project.py orchestrator, generic viewer/capture tooling, docs, installation and integration tests. Review agent read-only independent checks and test outputs in own outputs directory. No live model/page mutation. Runtime Three provided from bundled installed vehicle template or copied licensed vendor, never remote CDN by default.

Connections: [{id,a:{component_id,local_point},b:{component_id,local_point},max_distance,poses:[closed,half,open]}]; active components require declared anchors. scene_assembly resolves same parameters and checks closed positions; capture checks actual Three localToWorld per pose.


## 可选资产合同扩展 v1（外层 schema_version 仍为1）

asset_contract启用分件、变体、来源和交付验证；旧数据兼容不意味着已满足新资产要求。完整字段与约束见 asset-production.md / scripts/asset_contract.py。

- components.kind为part或assembly；assembly只保存父变换和语义，不含geometry/material。part具备真实geometry、material、role及稳定ID。
- selectable、explode_vector、material_slots控制可选取、局部拆解向量及授权材质切换。
- variants按独立互斥子树列出option→组件ID列表及default。不同变体集合不得共享或嵌套控制同一子树。
- mesh的uvs/normals保留到Three和GLB；uvs以glTF方向处理。材质maps必须源文件哈希、色彩空间和来源可追溯。
- asset_contract指定object_class、intended_use、units_source、required_components、required_operations、delivery_targets、source_notes。
- action沿用真实component_id、pivot、axis、angle；不另造一套导出运动数据。

同一Spec驱动payload、网页操作及GLB；Python校验和真实浏览器行为均需通过。专有脚本行为不能假装是GLB标准功能。


## 制作标准 v1 扩展

参见 [通用制作标准](production-standard.md)：新增生产契约、真实表面绑定、采样距离/镜像检查、捕获绑定的局部多视角记录以及显式修复审查。新项目在 Spec 阶段强制完整契约；旧项目保持兼容但不追认。规则完整性与视觉还原质量分别验收，未见对象效果需另做独立测试。
