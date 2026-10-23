# 运行环境与验证范围

基础脚本：Python 3.10+，标准库用于 GLB 清单、准备和网页构建。feature_guard、曲面/数值及轮廓工具使用 NumPy；silhouette_review 还使用 Pillow，依赖登记于 requirements.txt。现有 GLB 本地路线无需 Blender 或外部生成服务。

网页：HTTP、WebGL 与 Web Crypto；Three.js 本地依赖附 MIT 声明。自动检查使用 Node.js、现有 Playwright 及可用浏览器，PLAYWRIGHT_MODULE 指向已有模块，--chrome 显式指定可执行文件。详见 [网页契约](web-contract.md)。

Blender：仅用于 .blend 转换及选中的 Blender 工作。通过 PATH 或 --blender 指定。macOS 应用路径是可选探测，不是必需安装位置。Windows 使用本机 Python 命令（python3 示例可对应 python 或 py），带空格路径按当前 shell 引用；无需 POSIX shell 来运行 Python 脚本。Blender 内部脚本由 Blender 的 Python 环境执行。

可选服务：Meshy/Tripo 使用显式服务凭据和网络；提交受任务授权与费用约束。服务实机端到端验证不包含在本地回归中。

验证边界：macOS/Codex 本地脚本与 Chrome 网页执行；Windows 路径、subprocess 参数列表、Python/Node 文件系统 API 静态审查，没有 Windows 实机；Claude Code/OpenClaw 仅 SKILL.md 加载契约审查，没有客户端实际加载；Linux 不作为本轮必需目标。浏览器窄屏不表示物理手机性能。安装后须由当前 Agent 验证加载和依赖，不宣称所有平台已实测。
