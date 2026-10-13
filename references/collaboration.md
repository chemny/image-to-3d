# 多 Agent 协作契约

主代理统一 Spec、坐标系、共享边界及验收；禁止多人同时修改同一控制文件。任务写清输入哈希、可写文件、只读依赖、交付格式、测试及限制。代理无权改用户批准参考和降低阈值。

适合并行：输入分析、独立诊断、冻结接口后的部件施工、不同检查维度。参考生成仅在有授权/一致性约束时并行。先冻结公共接口再分工，依赖未完成时只能准备方案，不提前合并。

合并者检查任务输出文件范围及输入版本、运行集成测试，再检查实际模型；源文件改变使相关证据失效。冲突回到所有者修复，保留单写入者。独立审查代理只给缺陷与证据，不写被审查实现。

当前已实现文件范围与交付检查；通用租约/自动合并调度器不在当前能力内。实际使用宿主提供的 subagent API，缺该接口时顺序执行，不伪装并行。

## 已实现的检查入口

assembly_handoff.py 的 init 从 plan 捕获 inputs/contracts 和明确 review_paths 的文件哈希；claim 返回任务的精确可写文件清单；check 比对 receipt 与实际新增/删除/修改，拒绝少报或未知文件变化。metadata_paths 仅列 manifest/receipt 等记录，不能排除源码或共享输入。

Plan 必须包含 root（绝对工作目录）、inputs/contracts 路径列表、tasks:[{id,writes:[精确文件]}]、review_paths、metadata_paths。Receipt 包含 task_id、manifest_sha256、changed_paths、artifacts（路径→SHA256，显式删除为null）。其他并行任务的合法变化也需独立 receipt，不能把单任务通过当整体验收。

该检查只能发现声明范围内的变化，不能证明实际编辑者身份，也不提供操作系统隔离。重要共享源码仍采用单写入者，其他代理交付建议/独立文件。

全部交付后运行 `assembly_handoff.py check-all --manifest MANIFEST --receipts A.json B.json`。缺少任务receipt、重复任务或任一校验失败均拒绝；`integration_ready:true` 仅表示声明范围内源码交付完整性通过，后续仍须构建、运行和视觉审查。
