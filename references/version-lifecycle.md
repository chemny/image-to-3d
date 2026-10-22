# 版本生命周期与可恢复清理 v2

用于迭代工程历史占用管理；展示资产压缩仍按 [轻量交付](lightweight-delivery.md)。版本身份、用户认可、成果继承和采用继续使用 [版本交接](presentation-delivery.md#版本核实与成果继承) 和 [采用审查](adoption-review.md)，不另设审批阶段。

## 登记与保留

每次恢复任务、采用/接入新版本和迭代收尾，由执行代理从现有 project/state、案例注册、handoff、成果记录和修复会话整理或刷新项目内的 `version-ledger.json`。新生成不等于已采用，未被案例注册不等于可删。不要覆盖现有工程状态；ledger 是清理用投影，附原记录位置和原因，不取代它们。

状态：active（正式使用）、working（施工/待确认）、accepted（已认可未接入）、rollback（指定回退）、source（原图/源码/参数及重建输入）、evidence（有效审查依赖）、unknown（用途未知）均保护。retired（明确淘汰）及 cache（验证可重建的缓存）才可能列入清理；需已有记录的理由、证据哈希以及依赖覆盖核实。默认建议保留最近两个稳定回退版，可由项目调整；工具不按日期自动降级或删除。

每个 unit 是一个文件或互不重叠的目录，混有来源、待确认成果或共享依赖时拆分登记，无法拆分就保护整个目录。依赖以 unit ID 声明，保护节点沿依赖图传播。相同内容文件仍可能服务不同运行入口，不按哈希相同直接删除。ChatGPT/Claude 等来源使用项目实际来源标识，均纳入清单，不把某来源当作可清理副本。

## 登记格式与预览

路径相对 `--root`，禁止逃逸、符号链接、硬链接和嵌套清理单元。ledger、清理报告、退休证据保存在独立管理目录中。示例路径仅为契约，不是允许清理现有资源的指令：

```json
{
  "version": 1,
  "coverage_complete": false,
  "scan_files": ["case-browser/cases.js", "project/state.json", "task/handoff.json"],
  "protected_paths": ["references", "engineering"],
  "units": [
    {"id":"current","path":"versions/current","status":"active","dependencies":["shared"],"record":"task/handoff.json"},
    {"id":"shared","path":"shared","status":"source","dependencies":[]},
    {"id":"old","path":"versions/old","status":"retired","dependencies":[],
     "reason":"明确淘汰；原图、生成源码和参数另存并已验证重建",
     "retirement_evidence":{"path":"management/retirement.json","sha256":"实际文件SHA256"}}
  ]
}
```

`scan_files` 必须列真实存在的项目记录与入口。工具将其中出现的单元相对路径作为额外保护线索，并绑定文件哈希；它不是 JS/Python 动态依赖求解器，也不理解用户接受记录。执行代理必须补齐运行时请求、相对 import、共享贴图、动态 URL、有效历史审查/会话及重建依赖，核实后才能声明 `coverage_complete:true`。未核实保持 false，所有单元不具备可清理资格。不要通过改为 true 来绕过未知项。

```sh
python3 scripts/version_lifecycle.py inventory --root OUTPUTS --scan-file case-browser/cases.js --out MANAGEMENT/inventory.json
python3 scripts/version_lifecycle.py plan --root OUTPUTS --ledger MANAGEMENT/version-ledger.json --out MANAGEMENT/cleanup-plan.json
```

inventory 只盘点顶层目录逻辑字节、文件系统分配字节和显式 `--scan-file` 中的静态 `outputs/目录` 引用线索，超过4 MiB的文本跳过扫描并报告数量。无引用线索不表示无依赖；任何 inventory 项目均不可直接清理。plan 对登记单元完整哈希，列出保护原因、待隔离大小及零已释放空间；大项目先 inventory，再对范围明确的登记单元做 plan。

旧证据引用的模型若清理后不可复验，必须保留自包含必要证据，或明确将历史报告标为 retired / no-longer-reproducible；不能保留“通过”字样却删除仍有效的证明依赖。用轻量 recipe 替代大型重建产物前，实际重建并绑定源码、输入与结果，不能只声称可重建。

## 可恢复清理与恢复

先向用户展示范围、理由、大小、保留版及恢复方式；取得该计划或明确策略授权后，才允许执行 quarantine。`--approve-sha256` 是绑定已审阅计划的技术参数，不是用户授权证明，代理不得自行生成确认。首次历史清理、用途不明和永久删除仍需具体确认。永久删除使用下文 purge-plan / purge；隔离和永久删除使用不同计划哈希，已有明确同范围删除授权时不重复询问，但不能把工具参数当成人类授权。

```sh
python3 scripts/version_lifecycle.py quarantine --root OUTPUTS --plan MANAGEMENT/cleanup-plan.json --approve-sha256 PLAN_HASH --out MANAGEMENT/quarantine-result.json
python3 scripts/version_lifecycle.py restore --root OUTPUTS --transaction .model-quarantine/PLAN_HASH --out MANAGEMENT/restore-result.json
```

- 执行前冻结相关构建/写入，重算 ledger、入口/证据和单元哈希；过期或改写计划拒绝。项目锁防止本工具并发，不会锁住外部建模脚本，不能宣称能消除任意并发竞争。
- 同文件系统重命名到 `.model-quarantine/计划哈希/`，先落盘完整恢复意图（事务 journal v2），同时绑定旧入口原文、权限/时间及替换内容；部分中断仍可 restore。禁止移动到其他磁盘，不复制大模型占用双倍空间。
- 输出报告使用新文件，放在登记单元外；保留原相对位置和内容身份。restore 预检查全部载荷和退役入口，拒绝覆盖重新生成的模型或用户后来编辑的页面；恢复模型与旧 HTML/JSON 的内容、权限和 mtime，移除本事务新建的退役 sidecar。恢复不保证相同 inode/atime/父目录mtime、ACL/xattr等扩展元数据；不改事务外文件。进程被强制终止后检查 journal/进程，再人工处理遗留锁，不自动删锁继续运行。
- 隔离后按原案例接入与采用回归，检查当前加载资源、必要回退、共享贴图、换色保护、开合/重置/版本切换。失败则停止 purge，并运行 restore 完整恢复；不自动吞掉异常或覆盖冲突。工具不启动浏览器、不执行任意回调/命令、不自动认证视觉或功能。
- 同盘隔离不释放对应模型磁盘空间，`reclaimed_bytes` 固定为零；报告隔离逻辑字节与实际释放量，文件系统压缩/稀疏/快照也会影响最终回收。永久清理需另获明确授权，不因隔离到期擅自执行。

## 旧入口退役：与隔离共用一个事务

在同一 ledger 增加 `retirements`；原 units、扫描、保护与证据规则不变：

```json
{
  "required_checks": ["current_case", "rollback", "protected_state", "retired_entries"],
  "retirements": [
    {"path":"versions/old/index.html", "kind":"html", "unit_ids":["old"], "current_url":"/cases/"},
    {"path":"versions/old/bundle-manifest.json", "kind":"json", "unit_ids":["old"]},
    {"path":"versions/old/retirement.json", "kind":"json", "unit_ids":["old"]}
  ]
}
```

此例 units 中 old 应只登记 `versions/old/model.glb` 等模型文件。入口不能与清理单元重叠；若整目录要清理，目录内旧入口不能同时原地退役，应拆分文件粒度或另设外部入口。每个入口必须明确绑定本次合格单元，不能指向 protected/unknown。不自动猜测哪些 URL 或历史图库应该退役，代理先列全并取得同范围授权。

- `html`：小于1 MiB的HTML文件（可新建，父目录必须已有）替换为无脚本、无模型请求的退役提示及显式当前版本链接；仅支持 HTTP(S) 或根相对地址，转义链接，不加载旧 JS。原始页面完整备份在 journal。
- `json`：对象型JSON（可新建）保留原有内容，添加/更新 `_lifecycle`，标记 retired、model_available:false、历史记录身份及复验边界。原始字节与元数据备份；不删除历史哈希，不把历史 passed 改写成新通过。原审查判定、源码、原图和截图保留在保护范围。
- 仅已明确声明退役的旧入口可以在扫描中解除对其所绑定单元的引用保护；当前案例/其他扫描记录仍引用时继续保护。声明退役不是发现依赖的替代品。
- plan 绑定入口替换前身份、替换内容、保护资源快照和 required_checks。quarantine 在任何移动前保存所有模型与入口的恢复意图，再移动模型并更新入口。任一步失败保留日志；修复原因或 restore，不把半完成操作说成完成。
- 新事务恢复涵盖模型和本事务所有入口、manifest、sidecar；恢复前检查每个入口只能仍是本事务原文或预期退役内容，遇到新改动停止且不覆盖。中断恢复可重复调用；恢复完成后不再允许 purge。
- v1 历史事务仍可用旧 restore 恢复其载荷，但不追认它有入口备份；新增永久删除命令只接受 v2 事务。已经永久删除的历史载荷不能恢复。

## 检查报告与永久删除

隔离后按既有案例接入规则收集真实运行证据。提交报告示例（文件路径相对 --root，report 本身允许作为外部管理文件；证据须在受控根内）：

```json
{
  "version":1,
  "transaction_sha256":"quarantine结果中的实际事务摘要",
  "phase":"post-quarantine",
  "checks":[
    {"id":"current_case", "passed":true, "evidence":{"path":"management/browser.json","sha256":"实际摘要"}},
    {"id":"rollback", "passed":true, "evidence":{"path":"management/rollback.json","sha256":"实际摘要"}},
    {"id":"protected_state", "passed":true, "evidence":{"path":"management/protected.json","sha256":"实际摘要"}},
    {"id":"retired_entries", "passed":true, "evidence":{"path":"management/retired-pages.json","sha256":"实际摘要"}}
  ]
}
```

required_checks 复用项目已声明检查ID；未声明时默认 current_case / protected_state。实际有回退、入口、换色、开合等保护要求时在 ledger 中列全，不以默认两项假装已检查全部能力。报告拒绝缺项、重复、失败、错事务、错阶段和陈旧证据。工具只校验文件与声明一致性，不判断截图、证据真实性或测试是否充分；代理必须真实采集，不能靠手填true或复制旧证据认证。

```sh
python3 scripts/version_lifecycle.py purge-plan --root OUTPUTS --transaction .model-quarantine/PLAN_HASH --report MANAGEMENT/post-quarantine-checks.json --out MANAGEMENT/purge-plan.json
python3 scripts/version_lifecycle.py purge --root OUTPUTS --plan MANAGEMENT/purge-plan.json --approve-sha256 PURGE_PLAN_HASH --out MANAGEMENT/purge-result.json
```

purge-plan只读，输出精确到隔离载荷内文件的不可逆删除清单、逻辑大小/分配量与独立 purge_plan_sha256，不释放空间。取得该永久删除范围授权后才执行 purge；不自动到期删除、不扩展目录、不自动安装服务。

执行时重新核对原登记文件、扫描/退休证据、保护单元、退役页面、报告及其证据、全部隔离载荷与原位置；任何新引用、用户改动、缺失或身份变化均停止。依赖检查只覆盖已登记扫描文件与保护路径，不声称监控了全磁盘；执行前需冻结外部写入，项目锁不能阻止不合作进程并发修改。

永久删除先持久化 `purge-started.json`，再逐个 unlink 清单内文件、清理其已空目录，保留 journal 中的小型入口备份及所有审计日志，不递归删除未知内容、不清空隔离根。**写入不可逆删除开始记录后，完整 restore 即拒绝；不能承诺永久删除后恢复模型。** 中断后只能用原 purge-plan 和原授权参数继续同一范围；剩余文件变更或多出内容时拒绝继续，已删除项不会假装恢复。删除完成可重复执行为零新增删除，不重新扩大范围。

结果分开记录 logical_bytes、allocated_bytes_unlinked_this_run、available_bytes_before/after 与 observed_available_delta_bytes；后者为卷可用空间实测差，包含后台写入、快照与克隆影响，不称作精确文件回收量。隔离阶段仍固定报告释放为零。

所有 --out 必须是新文件，且不能位于受影响模型、入口、保护路径或事务内部，避免报告输出覆盖新恢复的模型或清空删除后的原路径。事务和计划摘要检测意外篡改，不是对抗能修改磁盘的恶意用户的签名或权限系统；用户授权由执行代理依据会话核实。

## 自动化边界

执行代理在恢复、采用/接入和收尾时刷新登记并生成预览；现有 project.py build/export 不自动调用本工具。没有正在运行的 Agent 时技能不会定时工作，周/月清理须另行授权配置调度；不得顺带创建自动化、修改模型或远程发布。通过预览不代表允许隔离，通过隔离不代表允许永久删除。新增 v2 事务工具已支持通用退役/完整恢复/永久删除，但不会自动替调用者发现项目入口、收集浏览器证据或授权删除。

回归见 [分层测试](validation-plan.md#版本生命周期回归)。
