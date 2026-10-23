# 服务接入（接口核对日期 2026-09-12）

优先尊重用户已有账号和服务，模型版本上线前再次核对官方文档。当前内置 Meshy 和 Tripo 适配器；本地模拟通过不等于真实账号调用验证，Rodin 尚未接入。

## Meshy
官方：https://docs.meshy.ai/en/api/multi-image-to-3d
API `https://api.meshy.ai/openapi/v1/multi-image-to-3d`；Bearer 环境变量 MESHY_API_KEY。1–4 张 PNG/JPEG，单独的多角度图片，可 Data URI。meshy-7 第一张作为主/前视图。固定版本 meshy-7，保留高精度网格再做网页优化，不一开始强制低面数。

```
python3 scripts/meshy.py prepare --images front.png left.png back.png right.png --out candidates/a
python3 scripts/meshy.py submit --candidate candidates/a --execute
python3 scripts/meshy.py status --candidate candidates/a
python3 scripts/meshy.py download --candidate candidates/a
```
prepare 不联网不计费，输出只存图片路径/哈希与参数。submit 才读取图片并发送。默认无纹理便于几何评审；需要贴图候选时 prepare 添加 --texture，开启 PBR。不要把无纹理测试模型直接当成材质完成品。候选文件夹独立，不覆盖。
提交标记在请求前写入，异常时保留 `submission.json` 防止重复收费。401/402/429/超时不自动再次提交；不确定是否创建成功时到服务端核对并将实际 task_id 写入 submission.json（不要猜 ID）。status 单次查询，代理自行短间隔轮询并汇报。下载只能在 SUCCEEDED 且存在 GLB URL 时进行。

## Tripo（v3，多视角已实现）
官方：https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard
上传：https://developers.tripo3d.ai/en/docs/files
查询：https://developers.tripo3d.ai/en/docs/task-query
凭据：TRIPO_API_KEY。使用官方 v3 API，不能与旧版 v2 的结果字段混用。免费积分以账号控制台实际余额及有效期为准，不承诺免费调用成功。

```
python3 scripts/tripo.py prepare --front front.png --left left.png --back back.png --right right.png --out candidates/tripo-a
python3 scripts/tripo.py submit --candidate candidates/tripo-a --execute
python3 scripts/tripo.py status --candidate candidates/tripo-a
python3 scripts/tripo.py download --candidate candidates/tripo-a
```
至少两张，必须包含真实对应角度的 front；不要用一张图片重复充数。仅上传 PNG/JPEG，每张不超过20MB。prepare 不联网；submit 上传图片取得 file_token 后提交多图任务。默认 v3.1-20260211、标准几何、无贴图；--texture 开启贴图/PBR，--parts 开启分件，两者互斥。分件结果仍需检查，生成门缝不代表车门可动。

提交前原子创建 submission.json，阻止重复上传和重复付费请求；UPLOADING 表示生成请求尚未开始，SUBMISSION_UNCERTAIN 表示可能已提交。失败不自动重试，核对服务端任务后恢复真实 task_id。不得删除不确定提交标记后直接重跑。status 记录实际消耗积分；download 检查任务匹配、成功状态和 GLB 文件头/长度。输出不为 GLB 时停止并检查，不将其他格式重命名成 GLB。命令行不回显密钥、图片正文或下载签名 URL。

## 后备服务
- Rodin：https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5 。多图/PBR/GLB候选，账户与计费独立。
- 自部署 Hunyuan：https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 。先核对硬件/依赖和授权再安装，不作为普通轻薄电脑默认依赖。

成本记录基于服务实际计费或已核对价格，不捏造费用。默认每轮一个候选、最多两个，超过授权预算前停止。没有凭据时保留准备结果，并提供 [Blender 直接建模](blender-direct.md) 路线。只有用户继续选择 API 时才需要通过安全方式配置环境变量，不让用户在聊天粘贴密钥。网站会员与 API 额度分别核实，不能用网站会员状态推断 API 可用性。限流、网络故障或提交结果不确定不等于额度耗尽；保留已有任务状态，不自动再次付费提交。
