# 内置车辆模块

由原 vehicle-configurator 0.4.0-local 的可复用工具和模板迁入。独立Skill不再是依赖；不复制其独立SKILL.md、Agent发现配置、发布报告或大型案例模型。来源文件摘要保存在本次项目迁移记录；Three.js许可随模块保留。

图片新建、从图修复继续顶层SKILL.md及project.py唯一状态流程。已有GLB/.blend资产整理、材质索引保护与配置器模板使用本模块，不为同一图片项目新建第二份旧project.json或复制阶段通过标记。使用历史资产工具时原project.json是该资产任务记录，不是顶层图片项目的新审批状态。

```sh
python scripts/vehicle.py asset_manifest --help
python scripts/vehicle.py prepare_model --help
python scripts/vehicle.py project --help
python scripts/vehicle.py locked_configurator --help
```

以上python表示本机实际Python 3.10+解释器，兼容带空格路径；工具作用和授权要求不变。Blender与外部付费候选服务均按需，入口不会自动安装、联网或发起付费请求。JavaScript浏览器验收工具仍位于本模块scripts，传入现有Node/Playwright/浏览器路径。

## 功能入口

- 既有GLB/.blend整理：scripts/prepare_model.py、asset_manifest.py；说明见 [加工路线](references/tool-routing.md)、[数据契约](references/data-contract.md)、[网页契约](references/web-contract.md)。
- 特征与接缝：feature_guard.py、fit_camera.py、loft_sections.py、surface_patch.py、section_curves.py；见 [特征保护](references/feature-protection.md)、[接缝诊断](references/seam-diagnostics.md)。
- 既有车辆任务的优化/返工证据：optimization_review.py、fidelity_loop.py、first_version_gate.py，报告接入顶层原流程，不追加平行审批。
- 锁定模板：assets/locked-configurator-v1，顶层project.py build --vehicle-config默认使用此内置位置；无需--vehicle-skill。后者仅供显式选择外部兼容模板。

锁定模板保留迁移前逐文件哈希和固定配置接口，不因迁移重算锁或重设计页面。其既有六色/三轮毂/三场景/八机位是这个模板的接口限制，不是所有模型的通用要求。用户已确认的其他页面/选项/隐藏参考图规则优先；不能为了套旧模板覆盖现有案例。接口不满足时说明并另行授权适配，不伪造车辆部件。

references/default-delivery.md等旧交付文档保留为历史模板契约，仅在明确复用该模板时适用。历史车型的名称、坐标、布局和数量不提升为所有新车型标准。根部贴合、连续曲面、版本/采用/运行时检查以顶层现有能力为准，不重复实现。

examples仅保留来源说明与脚本，不携带车型原图、GLB或final/original素材。历史案例执行前必须提供经过授权的独立素材；缺失时明确不可复现，不能当作内置可运行案例或当前认可模型。
