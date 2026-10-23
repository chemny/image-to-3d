# 图片建模接入统一核心

本模块已经位于image-to-3d内，不再查找同级image-three-core或vehicle-configurator。
图片任务使用顶层 scripts/project.py，统一state.json；原生GLB资产工具单独使用本模块入口，保留有效原始数据和证据。
兼容入口 scripts/image_reconstruction.py 转到同包顶层project.py；不调用独立旧Skill。
锁定模板构建使用顶层project.py build --vehicle-config VEHICLE.json --out NEW_WEB；默认内置模板，无需外部--vehicle-skill。
模型审查和案例产品页仍分开，相关采用、版式与交互检查沿用顶层车辆领域规则及当前任务的明确交付约定。
