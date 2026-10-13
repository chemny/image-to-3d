# Spec 与证据

实际字段与验证逻辑以 scripts/workflow.py 为准。字段骨架见 implementation-contract.md，实验几何字段见 surface_model.py 的模块说明及 examples/synthetic-surface-spec.json。后者是软件夹具，不能用作真实参考或用户确认。

常用命令（路径按工作目录调整）：

```sh
python3 scripts/workflow.py validate --spec TASK/spec.json
python3 scripts/workflow.py init --spec TASK/spec.json --state TASK/state.json
python3 scripts/workflow.py next --state TASK/state.json
python3 scripts/workflow.py mark --state TASK/state.json --evidence TASK/review.json
```

review 必须明确 stage、verdict=pass、acceptance=quality_passed、reviewer、rationale、review_scope、spec_sha256、resource_hashes、artifacts 和 check_results。每项 check result 包括 id、verdict、method、reviewer、scope、artifact_paths；stage:<stage> 检查必须存在。visual 检查要求显式视觉方法，但字段不能证明审查者真的看过图，执行代理必须核对内容。

所有 reference/source_files 的路径相对 spec；证据 artifact 路径相对证据 JSON。模型、相机与全部运行依赖应登记；脚本不会自动发现未声明的依赖。校准点与 validation 分开。真实尺度缺失时说明相对比例；生成参考只证明批准设计，不证明工程精度。

掩码 diff 的 alignment JSON 需要 status=validated、camera/model 相对路径及 SHA256、reference_mask_sha256、candidate_mask_sha256。原图与蒙版来源另留任务记录；不能用模型自身投影生成“参考真值”。

参数或源码改变后可运行 `workflow.py rebase --state TASK/state.json`。只有参考身份、任务范围、原批准及证据都未改变时，复用 intake/references 审查；spec/body 及其后阶段重新审查。参考变化不能复用原批准。

软件链路实验：`experiment_bundle.py examples/synthetic-surface-spec.json --parameters height nose_drop --out NEW_DIR`。输出前后 mesh、JS、拟合日志及身份清单；只接受 synthetic-software-test，不能推进真实任务状态。
