# 网页资源与恢复契约

`python3 scripts/project.py web --out <新网页目录> --model <自包含GLB> [--manifest <资产清单> --config <任务配置>]` 复制本地 Three.js MIT 依赖和模板，保留 GLB 原字节。用本地 HTTP 服务预览，不直接双击 HTML；浏览器资产哈希检查需要 localhost 或 HTTPS 的 Web Crypto。无语义映射时换色隐藏，旋转和保存仍可用。

## config.json v2
- schema_version=2；asset={id,version,config_version}，version 是 GLB 完整 SHA256，project.py web 自动填充。可选 assetManifest 由传入 --manifest 后设置，浏览器复核角色/保护。
- presentation.headline：可选主标题，模板内置 Automotive Studio 展示文案供起步；title 设置浏览器标题，description 显示在资产说明中。内置模板采用左侧看车、右侧配置、左侧底部视角与分层保存操作；完整配置器默认采用该分区，并将开合/灯光操作放在模型下方，完整选项见 [默认交付规范](default-delivery.md)。已有产品布局按用户要求适配并单独验证；模板未实现项须补齐。
- title / description：真实来源与质量边界。model：相对 GLB；rotationY：显示弧度；cameraDirection：默认机位。前后左右以模型 +Z 朝前为默认，必须按实际朝向确认 rotationY 或 views，不声称自动识别车头。
- paintTargets：`["n4:p0","n8:p1"]`，用 GLB 清单的源索引，不猜节点名。声明角色 paint 且固定保护不冲突才通过清单检查。每个目标克隆材质实例再改 base color，保留贴图、色彩空间和其他属性；带原始颜色贴图的模型可能只是乘色，须实际看图判断是否需要局部处理。初始显示原材质，不自动把首个色板当原车真值。
- paints：`[{"id":"blue","label":"深海蓝","color":"#24455b"}]`。id 稳定；“原始材质”导出 paint_id=null。
- scenes：`[{"id":"studio","label":"展厅","background":"#e4e1db","floor":"#d6d2c9","exposure":1}]`。可选 hemi / keyPower 为 0–20 的灯光强度，keyColor / fillColor 为十六进制颜色。完整配置器默认提供自然光、日落暖光和深色展厅三种场景，用户明确范围时可调整；宽幅程序反射环境、尺度适配的投影阴影与接地阴影是展示起点，不是原车材质校准真值。
- views：`[{"id":"quarter","label":"斜前","direction":[1.2,.45,1.8]}]`。自动按模型 bounds 和视口 fit；恢复相机时清除阻尼残留。
- originalPaintId / originalPaintLabel：可选，将已确认等同源外观的色板展示为原始材质入口，避免重复色板；原材质选择仍导出 paint_id=null。未确认等同性时不要填写。
- wheelSummary：可选 `{label,description}`，仅展示有证据的原模型固定轮毂信息，不启用更换；无证据时留空。
- referenceGallery：可选 `[{label,image:"./references/front.png",note:"来源与推断范围"}]`，使用本地 PNG/JPEG，传 --resource-dir 打包。完整配置器须打包当前批准参考并在模型区右上角常驻入口，查看/放大及当前模型对照按 [默认交付规范](default-delivery.md)。模板自动提供基础多角度参考弹窗，记录资源哈希并实际解码；没有参考时使用资产信息入口。
- rims：`[{"id":"a","label":"轮毂A","nodes":["Rim_FL","Rim_FR","Rim_RL","Rim_RR"]}]`。绑定真实四轮组含需要联动的胎/卡钳，选项之间不能重复节点。完整配置器默认制作三套真实变体；未具备时配置留空且记为未完成，不能以隐藏选项宣称默认规格已交付。
- doors：`[{"label":"左前门","node":"DoorPivot","axis":"y","openAngle":-1.1}]`。节点、轴心、厚度、门内侧和角度先检查；旋转不代表真实机械装配验证。
- interiors：`[{"id":"brown","label":"驾驶位","panorama":"./interior.jpg","yaw":0,"pitch":0}]`。真实完整 2:1 球形全景，固定座位拖动转头；缺资产留空。比例检查不证明接缝正确。传 --resource-dir，由 project.py 复制 config 声明的相对全景图片；缺文件在创建网页前停止。轮毂包含在 GLB 中，不以文件名假装已有变体。

旧 paintMaterials 名称绑定仅保留单一目标的兼容路径；同名共享多个 primitive 时拒绝并要求改为明确索引。旧无版本选择不能自动导入；任务可另行迁移，不能按展示标签悄悄套用。GLTFLoader 可清洗点号等名称，索引绑定不依赖其命名；门/轮毂仍须核对实际浏览器节点。

## 运行时材质依赖
融合区域或特殊着色器由任务本地模块处理，通用模板没有车型坐标。

```json
{"runtimeDependencies":[{"module":"./case-adapter.js","reason":"解释为什么 GLB 不足","files":[{"path":"case-adapter.js","sha256":"完整哈希"},{"path":"mask.png","sha256":"完整哈希"}]}]}
```

清单和 config 的依赖必须一致。传 `--runtime-dir <本地代码和资源目录>`，脚本检查哈希及安全相对路径、复制声明文件；浏览器再次检查字节。适配器是受信任的任务代码，需读源码；不是沙箱。导出 `async bind({THREE,gltf,model,renderer,config,paintBindings,dependency})`，每项 paintBinding={id,material,setColor,restore}，可改写声明目标的 setColor/restore 并加局部 shader。不准静默扩大车漆范围或破坏保护部件；所有适配后的材质要重新做视觉与保护检查。缺失模块/遮罩或版本不同给出错误，不能假装加载成功。清单必须包含模块自身及全部辅助文件；单独 GLB 的表现限制写到交付说明。

## saved selection v2
JSON/localStorage 共用：schema_version、asset{id,version,config_version}、paint_id、scene_id、view_id、rim_id、interior_id、mode、doors、camera{position,target,aspect}、auto_rotate、panorama{yaw,pitch}。使用 ID，不存 ready、凭据、贴图或模型。原材质为 paint_id=null，缺资产 rim/interior=null。

导入先完整校验版本、选项、有限相机/有效距离、布尔门状态与资源，再应用；失败不改变现有选择。本地保存按 asset id/version 分键，重载仅恢复同版本；保存动作失败有提示。相机跨视口按原 aspect 调整视距，选项不变。PNG 从实际渲染 canvas 导出；需读取下载内容而非只点击按钮。

## 实际验收
有现成 Playwright 时：

```sh
PLAYWRIGHT_MODULE=/path/to/existing/playwright/index.mjs node scripts/validate_web.mjs --url http://127.0.0.1:PORT/ --out <新证据目录> --chrome /path/to/existing/chrome
```

验证实际解码、每种色板、固定材质快照/特征索引、启用视角/场景/轮毂/门/全景、鼠标旋转缩放、环绕、实际 JSON/PNG 下载、文件输入恢复、本地保存重新载入、非法配置原子拒绝、390×844 布局。保存截图、下载件、耗时/渲染统计与错误日志。`window.vehicleConfigurator` 提供 getState/exportSelection/importSelection/inventory/performance 供检查；这些数据不替代实际看图和目标设备验收。图片格式、接缝、轮组真实装配需要专门目视评审。

内饰母版导出用 `render_panorama.py`，眼点需实际在封闭车厢中；先低分辨率确认接缝/遮挡，再正式输出。

config_version 是 project.py web 对网页配置和资产清单计算的 SHA256；相同 GLB 的绑定、预设或运行时依赖改变，也会拒绝旧选择。本地保存键包含它，不静默把旧材质配置套到新资源包。

编辑任务 web-config.json 后重新用 project.py web 构建到新目录，以更新 config_version；不要手改已验收目录再沿用旧版本。静态模型阴影在首次渲染缓存，门动画/恢复姿态时更新；自定义动画适配器也须显式标记 renderer 阴影更新，或自行采用持续更新。

新生成包包含 bundle-manifest.json。浏览器复核 config.json、asset-manifest.json、GLB 和使用中的全景；配置/角色清单被手工改动时停止并解释，避免旧 config_version 被继续使用。它是本地包一致性检查，不是来源签名。新 config_version 也包含资源内容哈希。旧无 bundleManifest 字段的包仍可读取。

异步导入在资源准备后检查当前操作序号；新的导入或配置按钮会使较慢的旧导入失效，失效请求不改当前选择。保存外观模式中的 interior_id 后再次进内饰，使用该项而非默认项。观察角度超出 OrbitControls 限制时拒绝，不悄悄夹到另一机位。

多内饰回归可用 validate_recovery.mjs，与 validate_web.mjs 相同参数。它要求至少两个真实可加载的 interior IDs，测试记忆选择、后来的导入/场景点击胜出、非法相机原子拒绝以及跨视口恢复。

## 布局与渲染对齐

成熟案例可作为展示验收基准：固定同一资产哈希、视口、任务相机、车漆和场景，对比实际模板输出与参考。相机、曝光、灯光、反射和接地阴影分别记录；UI 截图与纯 canvas PNG 都检查。当前模板以 FOV 33° 为展示起点并按模型包围体拟合；实际机位、单位和车头方向仍需任务确认。对照不代表新车型形似通过。

采用原案例依赖时须全部交付并校验；不可只把旧页面截图嵌入 README 而让模板输出另一套布局。保护材质不串色、保存/恢复版本一致、图库关闭/切换以及窄屏均复测。可用 vehicleConfigurator.presentation() 记录实际曝光、FOV 与光强，不凭配置文本假定渲染生效。

## 预设视角过渡

点击底部视角按钮时，默认约 800ms 以缓入缓出球坐标环绕，方位角走最短路径；不能直线插值穿过车辆。连续点击以当前相机姿态重新起步，只保留最后目标。手动拖拽／滚轮、重置、导入方案和内饰切换应正确取消过渡；过渡期间暂停自动环绕推进，结束后恢复。窗口尺寸变化先完成目标落点再重新适配画幅。遵循 prefers-reduced-motion。浏览器验证必须等待 view_transition=false，并核对方向、半径、连续点击及用户接管，不能只检查按钮高亮。

预设视角的标签应简短、能辨识具体方位，避免“另一侧”等依赖当前姿态的相对称呼。名称与实际落点须一起核对；车顶视角应从上方看车，不能只换标签。案例的视角集合是配置参数，不要求所有车型固定使用同一组坐标。


部件开合、直接点击、手势防误触、状态同步和展开取景按 [交互契约](interaction-contract.md) 执行。现有基础模板并未自动实现其中全部能力，新增项须任务适配与实测。
