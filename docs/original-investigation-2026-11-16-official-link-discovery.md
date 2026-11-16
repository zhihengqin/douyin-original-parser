# 7707993970332290314：官方首次取址续查（2026-11-16）

只输入 `https://www.douyin.com/video/7707993970332290314`，禁用全部原片 catalog 和参考资产后，本轮仍未发现该作品原片，不能作为生产修复交付。最新约束是完全自建；本轮发现请求均访问官方接口，使用新匿名访客及作品自己下发的元数据。机器结果见 [official-link-evidence.json](original-investigation-2026-11-16-official-link-evidence.json)。

## 同轮校准：现有原画流程仍可工作

以研究子类禁止 catalog 回退，同时把 `_read_original_records` 替换为一旦调用即失败的断言。详情均来自本轮仅按链接取得的官方响应；没有读取参考文件、参考 MD5 或先前保存的原片地址。

| 作品 | original 选择器 | source 选择器 | 实际媒体结果 |
| --- | --- | --- | --- |
| 7695305664234589459，阳性 | 16 个转码档 | 1 个 original | 528,422,694 字节，1920×1248，486.342 秒，HEVC + AAC，Range/moov 校验通过 |
| 7707993970332290314，目标 | 9 个转码档 | 9 个转码档 | `source_unavailable`，没有原片候选 |

这说明目标当前目录没有被生产选档器漏选的 original 行。它没有确定服务端缺少原片行的原因，也不证明其他官方入口均已穷尽。

## 从官方转码容器发现另一个 VID

对目标 9 个官方 MP4 逐一读取 ftyp/moov，按 box 偏移跳过 mdat：

| 实际文件 | moov 内的 `vid:` |
| --- | --- |
| 52,471,983 字节，720×1280 H264 normal | `v28033gi0000dbrj3knog65o00vl2vc0` |
| 其余 8 个 MP4 | `v28033gi0000dbs4nevog65jrl6u1s10`，即详情当前 VID |

这个内嵌 VID 是只凭链接可重现的发现输入；它不依赖已知原片哈希。但容器 comment 不能单独证明父子关系、上传去重、迁移机制或原片身份。

另从官方 SDK 目录取得此前未读的 39,001,222 字节 MP4，其 moov 仍为内嵌 VID，没有发现第三 VID。对两个新 DASH 视频部分读取 moov，28,420,558 与 39,056,996 字节对象都带当前 VID，且只有视频轨、没有音轨。早期主机校验报错随后已在研究范围内按实际下发的官方 CDN 主机完成读取，不能把早期报错当作最终资源不可用。

本轮媒体检查是限定 Range/moov 读取；表中的 FileHash 来自官方目录，没有把这些转码全部重新完整下载来验证整文件哈希。

## 官方 APK 的 VID-only 播放目录

41.1.0 的 `X.1flM.apiForFetcher` 根据时间戳、VID 和其固定派生常量构造：

```text
https://vod-urls.bytedanceapi.com/video/play/1/toutiao/<ts>/<digest>/mp4/<vid>
```

这里的 digest 是 SDK 请求派生值，不是参考原片 MD5。对目标当前 VID 和新观察到的内嵌 VID，均实际返回 HTTP 200、status 10 和匹配的响应 VID：

| 输入 | 默认 MP4 目录 |
| --- | --- |
| 当前 VID | 40,274,983 与 52,471,983 字节，均为 normal |
| 内嵌 VID | 39,001,222 与 52,471,983 字节，均为 normal |

内嵌 VID 的 source 参数对照仍是这两个 normal 对象；DASH 参数分支也没有补出原片。此为已审 builder 的参数子集实验，不声称完整重放 App。

也检查了把实际观察到的 VID 作为 fplay `force_fids` 精确 FID 的分支：保留目标自己的签名路径和查询上下文，`stream_type=source`、`codec_type=5`，仅对 FID 做 Base64 编码。阳性以自身 VID 强制选档，返回 528,422,694 字节 original；目标分别以当前 VID、内嵌 VID 强制选档，均仍返回 9 个转码档。没有用另一个 VID 替换签名路径里的作品 VID。

## 官方网页签发上下文已取得成功基线

复用已审官方懂车帝网页 module 48087 的 `/motor/pc/common/token` 调用，以及 module 8818 的播放消费方式：解开官方返回的 Base64 JSON，取完整 `GetPlayInfoToken` 原样查询 `vod.bytedanceapi.com`，附加其实际 caller 的 `ssl=true&aid=36`。

裸 HTTP 请求最初得到空正文，不能判断视频状态。在新的匿名官方网页上下文中，同一签发入口成功，随后浏览器的正常 fetch 也成功取得播放目录。对阳性、目标当前 VID、目标内嵌 VID，分别让签发方签入以下参数：

```text
stream_type=source
definition=original
codec_type=5 或 8
```

六份结果均为 issuer status 0、模型 HTTP 200、Data.Status 10、响应 VID 匹配。离线解开返回的 token 可确认上述三个参数实际出现在 `X-Amz-SignedQueries` 中；没有在签发后更改这些字段。

**六份目录仍全部为转码，没有 original/source 质量行。** 阳性在这个上下文也没有列出其已知原片，因此只能说该签发上下文没有返回源文件，不能由此认定目标受到专属权限拒绝。参数被签入也不证明其业务取值已经生效；现有结果不能区分参数语义、目录策略或授权范围。

## 撤回“缺 native Authorization 算法”的旧判断

实际方法审计表明，之前从 DEX 字符串邻近关系推断播放 Authorization 的做法不成立。所引常量分别属于上传 SDK 与 QoS；41.1.0 的 version 2/4 播放分支明确向 fetcher 传空 auth。完整证据见[授权消费链审计](original-investigation-2026-11-16-auth-consumer-audit.md)，历史实验脚本的说明也已更正。

旧版真实 consumer `LX/jkl` 使用 `open.bytedanceapi.com` 根路径，因此另对本轮目标与阳性自己的 Web 签发 query 原样做了有效期内消费。两个响应均为 HTTP 200 内嵌 `AccessDenied/100013/resource: []`。这次组合没有建立成功播放基线，不能把错误解释为目标原片不存在，也不能据此重新断言需要 native 签名。

## 可复现工具与验证

新增 `tools/probe_official_vid_lineage.py`，从链接重新取得官方详情和原样 fallback，读取各 MP4 的元数据，再对当前/新观察 VID 请求上述默认 SDK 目录。输出仅保留档位、大小、FileHash、媒体信息和 VID，不保存临时 URL/token，不访问 catalog，不写入原片记录。

在项目目录执行：

```powershell
.venv\Scripts\python.exe tools\probe_official_vid_lineage.py `
  "https://www.douyin.com/video/7707993970332290314" `
  --direct --out output\official-link-research-20261116\reproduced-lineage.json
```

`--direct` 仅表示目录与媒体 HTTP 请求不使用环境代理。工具限制为最多 20 个媒体对象、每对象 2 MiB 元数据预算、16 次 Range 操作、最多 4 个 VID，并且只追踪一层；不会枚举猜测的 VID。它的退出码 0 表示诊断完整执行，**不表示原画已修复**；实际报告同时给出 `audit_complete=true` 和 `repair_verified=false`。

已用目标链接从新匿名会话运行上述命令，9 个 MP4 元数据读取和两个 SDK 目录都完成，重现相同两个 VID，仍无原片。回归用例覆盖不读取 catalog、结果不泄漏签名地址、拒绝大小变化/非 206/过大 moov、SDK 主机允许及外部跳转拒绝。全套检查为 `101 passed, 108 subtests passed`。

当前没有通过验证的新原片候选可接入生产。缺口仍是目标自己的原片身份首次发现；现有参考资产的官方重签能力不能替代这个步骤。
