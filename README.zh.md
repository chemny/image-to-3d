# Image to 3D

[English](./README.md) | 中文

## 项目简介

Image to 3D 是一个根据物体参考图构建可编辑 Three.js 模型的 Agent Skill。它帮助设计师和开发者把图像观察整理成模型 Spec，生成几何，对照参考图检查渲染结果，并打包数字资产。

适用于车辆、玩具及其他物件。Agent 负责理解图片和设计形体，工具负责构建与检查；隐藏面属于设计推断，不保证单图高精度还原或一次成型。

## 效果预览

![六个模型的 AI 润色展厅主图：全尺寸 SUV、纯电 SUV、纯电超跑、布娃娃、茶壶和玩具小鸡](./assets/preview-six-models-polished.png)

与个人网站一致的六模型 AI 润色展厅主图，并非未经处理的模型运行截图。另可查看[早期未润色渲染](assets/preview.png)。

## 核心功能

| 能力 | 它能帮你做什么 |
|---|---|
| 参考图建模 | 从可追溯的组件、材质和相机 Spec 构建 Three.js 场景。 |
| 参考准备 | 规划补充视角与特写，区分实际观察和推断设计，记录确认依据。 |
| 可控形体与连续曲面 | 构造截面、圆滑封边及过渡补面，检查实际网格接缝、截面折转与曲率方向变化。 |
| 视觉对照 | 用固定机位渲染、轮廓和真实几何锚点检查偏差，不暗中扭曲参考图。 |
| 可编辑部件 | 在资产合同支持的范围内选择、换色、替换、拆解和复位部件。 |
| 缺陷分诊与部件贴合 | 区分几何、法线和外观原因，在实际安装根部与指定宿主面之间检查距离。 |
| 版本与成果继承 | 区分当前展示模型与已认可样件，记录继承成果并核对案例接入证据。 |
| 轻量交付 | 完整几何只加载一次，资源去重、默认无损压缩，超预算报告原因，不自动减面。 |
| 资产交付 | 导出 GLB，保留来源与审查依据；可选验证实际 Blender 导入。 |

0.12.5 新增[版本生命周期管理](references/version-lifecycle.md)：依赖清理预览、可恢复隔离、明确的旧入口退役，以及单独授权的永久删除。[运行时校验](references/runtime-guards.md)检查时序稳定性记录、归一化与世界锚点、声明的发布依赖，并生成拒绝冲突的局部回退预览；工具不会自动捕获浏览器、发现全部依赖、写注册表或发布。

本地 macOS 软件回归共 712 项通过，其中运行时校验新增 36 项；测试数量不代表视觉还原质量，也不代表本轮已实测 Windows 或 Claude Code。

## 安装

### 配置要求

核心工具在本地运行。补图、浏览器捕获和 Blender 检查需要 Agent 可用的相应工具。

| 项目 | 要求 |
|---|---|
| Agent 客户端 | 本地已在 macOS Codex 使用；指令不绑定宿主专有接口，但本次未重新完成 Claude Code 运行验收。 |
| 核心运行环境 | Python 3.10 或更高版本、Pillow 和 NumPy。 |
| 预览与捕获 | 现代浏览器；自动捕获还需要 Node.js 和 Playwright。 |
| 可选功能 | 补充视角使用宿主生图工具；导入验证使用 Blender。 |

本次未完成 Windows 实机运行验证。浏览器和 Blender 的可执行路径需按目标机器指定；macOS 路径示例不是跨平台默认值。

已有车辆页面适配还需要独立的 vehicle-configurator skill，通用模型不依赖它。

### 快速安装

向 Agent 发送：

> 帮我安装这个 Skill：https://github.com/chemny/image-to-3d。先检查基础环境，缺什么帮我补齐，再安装并检查能不能加载使用。其他功能等我需要时再配置。

Agent 应说明实际验证了什么、还缺哪些配置，不能仅凭复制文件就宣布可用。

## 快速开始

上传一张清晰的物体图片，然后说：

> 用 Image to 3D 帮我把这个物体做成可编辑模型。先分析主要形体和缺少的视角，再做出第一版，告诉我它与原图还有哪些差异。

你会获得本地模型预览、Spec 和审查文件。接受结果前，请检查原图机位，以及至少一个能够观察厚度的角度。

## 使用示例

### 按参考图制作玩具

> 把这张玩具图做成模型，保留有辨识度的轮廓，把后续可能换色的部件分开。新增隐藏面设计前先和我确认。

### 修复局部形体

> 这个翅膀太平了。保持相机、材质和其他部件不变，重建它的厚度和根部，再对照原图机位与侧面。

### 继续优化已有模型

> 先核实案例实际加载的版本，保留之前认可的形体成果、材质和交互。优化身体过渡，给我看前后对照，改得不如之前的地方保留原版。

### 准备可复用资产

> 把这个经过审查的模型整理成 Three.js 和 GLB 资产，检查部件选择、换色和拆解。如果有 Blender，也验证一下导入。

## 工作原理

1. 分析原图，准备参考集，明确不确定性及生成设计的确认依据。
2. 编写 Spec：组件、几何、材质、相机、装配关系和实际观察绑定。
3. 用 form_construction.py 生成局部形体；construction_plan.py 将构造参数与真实网格、保护部件关联。
4. 通过 project.py 构建、捕获、对照和审查。reference_set.py 检查参考记录，anchor_evidence.py 投影真实几何，workflow.py 检查证据版本和阶段要求。
5. `surface_attachment.py` 检查声明的安装根部及开口射线，`surface_quality.py` 检查实际网格连续性。缺陷分诊由 Agent 根据证据完成，不是自动图像诊断。
6. 复用 `adoption_check.py` 核对局部采用记录，`version_handoff.py` 核对版本、成果继承及浏览器证据；它不自行启动浏览器，也未自动挂入 build/export。
7. 使用资产检查、`lightweight_delivery.py` 和交换工具验证交互、无损运输和导出。诊断模型不等于已验收交付物；案例接入按项目已有接口完成。

工具验证声明的数据和几何，不能自动判断所有图片和造型是否正确；仍需明确范围、来源和实际视觉审查。宿主支持时，可按协作契约分配多个 Agent 工作。

## 目录结构

```text
SKILL.md       Agent 入口
requirements.txt Python 核心依赖
agents/        客户端显示信息
scripts/       构造、项目、审查及交换工具
references/    建模、参考与交付规范
assets/        Three.js 运行库、许可及预览
examples/      可编辑资产的合成功能样例
tests/         软件及可选运行环境回归检查
```

可从[执行指南](references/unified-execution.md)、[参考准备](references/reference-set-standard.md)、[局部构造](references/form-construction.md)和[资产交换](references/asset-exchange.md)开始。内置样例用于功能检查，不是照片重建效果基准。


已有模型优化可参考[缺陷分诊](references/defect-triage.md)、[修复与根部贴合约束](references/repair-contract.md)、[连续曲面](references/continuous-surfaces.md)、[版本继承与案例接入](references/presentation-delivery.md)和[轻量交付](references/lightweight-delivery.md)。

其他契约：[历史接口说明](references/implementation-contract.md)、[Spec 与证据](references/spec-and-evidence.md)。

## 许可

项目代码使用 [MIT 许可](LICENSE)。随包提供的 Three.js 保留[自身 MIT 声明](assets/vendor/LICENSE)。参考图与用户提供的资产需具备相应使用权，不因代码许可而重新授权。规则来源见[来源映射](references/production-rule-sources.md)。

## 关于我

由 [chemny](https://github.com/chemny) 维护。可通过 [GitHub Issues](https://github.com/chemny/image-to-3d/issues)反馈可复现的问题。
