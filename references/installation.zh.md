# 安装、环境检测与首次使用

适用于整合版 image-to-3d。先确认 Agent 能找到 SKILL.md，再诊断当前解释器；缺什么再准备什么。`doctor` 不安装、不改配置、不启动浏览器；`first-use` 只在显式新目录生成合成测试产物。复制Skill成功不等于运行能力通过。

## 一键入口（先检测，确认后安装）

完整Skill解压到目标Agent的技能目录后使用；这个入口准备运行环境和自检，不会把Skill复制到其他Agent或注册宿主。Mac可双击根目录的install.command，也可在终端执行；Windows可双击install.cmd或在PowerShell执行：

```sh
# macOS：无需激活环境，也无需安装Playwright/Blender
bash ./install.command
# 只检测，绝不安装或生成样例
bash ./install.command --check-only
```

```powershell
# Windows CMD启动器，不修改PowerShell执行策略
.\install.cmd
.\install.cmd --check-only
```

流程只有一条：发现可用Python → 复用doctor → 如有必需依赖缺失则列明来源、环境目录和命令并等待确认 → 安装成功后重新doctor → 复用first-use生成合成样例与报告。依赖齐全则跳过安装，不要求再次确认。支持`--data-dir "自选目录"`，并可用IMAGE_TO_3D_PYTHON指定Python可执行文件完整路径（不是带参数的命令字符串）。

- Python缺失时：Mac仅在已有Homebrew时，确认后执行`brew install python@3.13`；Windows仅在已有winget时，确认后运行`winget install --id Python.Python.3.13 --exact --source winget --scope user`。不会自动安装包管理器，不传自动接受协议参数，不自动提权。Python安装器可能按所选选项注册启动器/修改用户PATH，入口会先说明；由用户处理安装器/协议提示。
- 没有相应安装工具：停止并给出python.org官方安装指引，安装Python后重跑。这是明确的引导式后备路径，不能宣称所有空白机器都可零交互安装。
- 核心库缺失时：显示隔离venv和PyPI安装清单，Mac/核心流程输入INSTALL确认，Windows的Python引导用Y/N确认；默认不安装，非交互核心流程拒绝安装。新隔离环境需要Pillow和NumPy两者，即使系统已有其中一个；已受管环境只补缺失/版本不满足的库。
- 只向受管venv安装，不运行全局pip、不升级pip、不改默认Python或shell配置；只取二进制轮子，没有匹配包就失败，不自动编译或换源。失败记录与部分环境保留，不覆盖未知venv，不删除失败产物；可换一个新data-dir重试。

默认数据目录是Mac的`~/.local/share/image-to-3d`和Windows的`%LOCALAPPDATA%\image-to-3d`（无该变量时退回用户AppData/Local）。依赖需安装时才创建venv及所有权记录；首次自检使用新的first-use目录，保存first-use-report.json与setup-report文件。控制台会打印实际Python和报告位置，后续建模使用同一个Python。该目录位于Skill之外，不随Skill替换而自动删除。

`--check-only`完全只读，缺Python也不调用包管理器。退出码0表示对应检查/自检通过；1表示核心流程不通过、取消依赖安装或所请求的可选能力缺失；2表示Python引导不可用/取消或参数错误。下载失败、磁盘/权限不足、venv或pip不可用时保留错误，不伪报成功。

可选能力仍按后面章节配置已有工具，再显式运行，例如：

```sh
bash ./install.command --capability automation --node "/path/to/node" --playwright-module "/path/to/playwright" --browser "/path/to/chrome"
bash ./install.command --capability blender --blender "/path/to/blender"
```

Windows同样参数，入口换成`.\install.cmd`；参数按独立引号传入。可选工具缺失只报告，不顺带下载安装。不要用一键核心自检的通过结果替代实际WebGL捕获、Blender导入、Agent加载或视觉验收。

**验证边界：** Mac已有启动器、只读诊断和核心首次使用实跑；必需依赖确认/拒绝/安装失败路径有模拟回归，本轮未在干净Mac上联网重装依赖。Windows仅完成Python侧路径/参数模拟与CMD脚本审阅，**CMD启动器、winget安装及Windows首次使用尚未实机执行**。Mac无Python时的Homebrew安装也未实际触发，不能把代码存在当作实跑通过。若macOS阻止下载脚本，先核实来源并按系统提示操作；不自动清除隔离属性或绕过安全提示。

Python引导包标识参考：[Homebrew公式](https://formulae.brew.sh/formula/python%403.13)、[Microsoft winget清单](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/13)。


## 依赖分层

| 层级 | 内容 | 缺失后的行为 |
|---|---|---|
| 核心运行必需 | Python 3.10+、Pillow≥9、NumPy≥1.24、完整Skill文件 | 核心检查失败，先修复解释器/环境或重新完整安装 |
| 人工看模型 | 支持本页面WebGL和解压API的浏览器，以及本地HTTP服务 | 可生成数据/GLB，但不声称看图与交互已验证 |
| 可选自动化 | Node.js≥18、已有Playwright JS模块、可启动的Chromium/Chrome/Edge | 不影响核心建模/导出；现有自动捕获和浏览器验收不能通过 |
| 可选Blender | 本机Blender可执行程序 | 不影响Three.js与GLB导出；不声称实际Blender导入通过 |
| 宿主能力 | Agent加载Skill、原图观察；补图按需使用宿主生图工具 | CLI不能证明Agent发现/看图成功，也不能替代生图权限 |

车辆工具/锁定模板已在domains/vehicle内，不再安装旧vehicle-configurator。既有环境可直接复用；没有必要为了安装核心而下载Playwright浏览器、Blender或额外Skill。新依赖安装、联网下载和环境修改由用户授权后进行；不重写全局PATH或默认Python，不复制到未授权的其他Agent目录。

## 1. 核心诊断（只读）

在Skill目录执行，解释器换成当前机器实际可用者：

```sh
# macOS；不假定系统已自带Python
python3 -X utf8 scripts/environment.py doctor
```

```powershell
# Windows PowerShell；有py启动器时使用，没有则使用实际Python完整路径
py -3 -X utf8 scripts/environment.py doctor
```

成功退出0，失败退出1，JSON打印到stdout，不创建报告文件。检查python.executable及版本、libraries、package、core_ready；可选工具未请求时是not_requested，不影响核心。detected_tools只是PATH或平台路径线索，不证明浏览器/Blender已运行。Windows检测Program Files、Program Files (x86)、LocalAppData中的Chrome/Edge及Blender Foundation版本目录；macOS检测PATH和应用包路径。自定义位置显式传入，不猜测其他用户目录。

CLI输出ASCII安全JSON；子进程启用UTF-8和不写字节码，示例也使用-X utf8，避免Windows默认编码影响中文资源。诊断不遍历全盘、不修改权限或注册表。Python未安装或命令不可用时，先向用户报告并确认准备方式，不能把无法运行诊断说成通过。

## 2. 仅缺核心库时准备隔离环境

下面是用户明确同意后执行的命令，不由doctor自动运行。环境目录与样例目录均位于Skill之外；无须激活venv，后续一直使用同一个解释器。

macOS：

```sh
skill_dir="/path/to/image-to-3d"
env_dir="/path/to/image-to-3d-env"
python3 -m venv "$env_dir"
"$env_dir/bin/python" -m pip install -r "$skill_dir/requirements.txt"
"$env_dir/bin/python" -X utf8 "$skill_dir/scripts/environment.py" doctor
```

Windows PowerShell：

```powershell
$Skill = "C:\path\to\image-to-3d"
$Venv = "C:\path\to\image-to-3d-env"
py -3 -m venv "$Venv"
& "$Venv\Scripts\python.exe" -m pip install -r "$Skill\requirements.txt"
& "$Venv\Scripts\python.exe" -X utf8 "$Skill\scripts\environment.py" doctor
```

pip不可用、网络失败、无匹配轮子或权限不足时保留失败信息，停止安装；不自动提权、改全局环境、换不可信源或无限重试。若原解释器已经满足核心要求，不必新建或重复安装。

## 3. 首次核心使用验证（不需要Node/Playwright/Blender）

```sh
"$env_dir/bin/python" -X utf8 "$skill_dir/scripts/environment.py" first-use --out "/path/to/first-use-new"
```

```powershell
& "$Venv\Scripts\python.exe" -X utf8 "$Skill\scripts\environment.py" first-use --out "C:\path\to\first-use-new"
```

复用现有解释器时直接替换命令中的Python路径。--out必须是新的Skill外目录；已有目录拒绝覆盖，失败的部分产物保留以便诊断。生成合成PNG、Three.js预览、无损压缩数据、sample.glb与first-use-report.json；不使用用户原图/模型，不伪造已接受基线或跳过正式项目门禁。

此项实际验证Pillow图片读写、Spec→网格、运输数据回读一致及GLB文件头。passed只代表软件冒烟检查，不代表还原质量、宿主加载、人工看图或Blender导入。

人工预览按报告中的目录启动HTTP服务，端口冲突则换可用端口，不杀用户现有服务：

```sh
"$env_dir/bin/python" -m http.server 8000 --bind 127.0.0.1 --directory "/path/to/first-use-new/preview"
```

```powershell
& "$Venv\Scripts\python.exe" -m http.server 8000 --bind 127.0.0.1 --directory "C:\path\to\first-use-new\preview"
```

用浏览器打开http://127.0.0.1:8000/，确认样例可见、可换色/选部件、机位/动作控件有效、无加载错误。不要直接双击file://页面；服务关闭后页面自然不可访问。没有自动化时记录人工结果，不填“Playwright验收通过”。本机Agent若有其他浏览器接口可采集等价证据，既有capture.mjs仍需Playwright。

## 4. 自动化按需配置

先复用现有Node、Playwright及Chrome/Edge，显式传已有文件。--playwright-module接受index.mjs/index.js或包含它们的包目录；不搜索全局缓存或借助npx隐式下载。

```sh
python3 -X utf8 scripts/environment.py doctor --capability automation --node "/path/to/node" --playwright-module "/path/to/playwright" --browser "/path/to/chrome"
python3 -X utf8 scripts/environment.py first-use --capability automation --node "/path/to/node" --playwright-module "/path/to/playwright" --browser "/path/to/chrome" --out "/path/to/automation-first-use-new"
```

Windows相同参数，使用`py -3 -X utf8`或venv的python.exe，路径加引号即可。doctor只检查Node版本、模块可导入和浏览器文件存在；first-use才实际调用既有capture.mjs，在临时本地HTTP页面验证WebGL绘制并保存截图。实际环境的启动失败会保留报告并返回失败，不降级伪报通过。

如果用户需要且允许下载，可把工具装到单独目录：`npm install --prefix TOOL_DIR playwright`。需要Playwright自带Chromium时，由现有Node运行`TOOL_DIR/node_modules/playwright/cli.js install chromium`；已有兼容浏览器可不下载。Node/npm缺失先另行确认准备方式，不把它们混入requirements.txt，不自动全局安装。

## 5. Blender按需配置

```sh
python3 -X utf8 scripts/environment.py doctor --capability blender --blender "/path/to/blender"
python3 -X utf8 scripts/environment.py first-use --capability blender --blender "/path/to/blender" --out "/path/to/blender-first-use-new"
```

doctor只运行--version；first-use显式选择后才启动无界面Blender，将合成GLB实际导入并核对已有交换清单，保存blender-report.json。不会打开或保存用户工程。Blender不是pip依赖；没有安装时报告缺失，由用户决定是否安装。两项可选能力可重复--capability组合请求。

## 结果与平台边界

分别记录：Agent识别、核心诊断、核心首次使用、人工浏览器、自动化捕获、Blender导入。不可将not_requested/available_unverified写成实际通过。--capability缺依赖时总passed为false，但core_ready仍独立报告。

本轮Mac实际运行结果与Windows路径/参数模拟回归分开保存。尚无Windows实机结果时明确“检测逻辑已实现，实机未验证”，不能宣称双平台开箱即用或全新干净系统已通过。CLI不注册Agent、不创建定时任务、不推送代码。
