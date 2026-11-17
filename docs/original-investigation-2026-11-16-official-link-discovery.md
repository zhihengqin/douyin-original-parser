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

## 后续：PC 网页真实请求与精选移动 SSR

本次继续独立研究，没有向用户索取或使用第三方解析接口信息。仅使用作品链接、官方页面正常发出的请求，以及这些响应自己包含的 VID。脱敏结果保存在 [PC 上下文证据](original-investigation-2026-11-16-pc-context-evidence.json)。

此前 `browser_detail.py` 中的手动 `fetch` 固定使用 `aid=392139`，不能用它代表已经检查过 PC 自己的 `aid=6383` 请求。本次用新的匿名 Chromium 上下文正常打开目标作品页，等待页面实际初始化，捕获自然发出的 `/aweme/v1/web/aweme/detail/`：HTTP 200、status 0、作品 ID 和当前 VID 均匹配，确实使用 `aid=6383`。页面最终正常播放，实测视频为 576×1024、326.936961 秒的已知转码对象。

| 同一 PC 会话 | 详情模型 | 详情码率项 |
| --- | --- | --- |
| 阳性 7695305664234589459 | `video_model` 空 | 27 项，没有 original/source |
| 目标 7707993970332290314 | `video_model` 空 | 12 项：8 个普通 MP4、4 个普通 DASH，没有 original/source |

因此“PC 比已有 fplay 返回更多码率项”不等于发现原片；阳性在 PC 详情中也没有原片行。目标 PC 的 MP4 均是此前已知的普通档。此前未读的两个 DASH 对象分别为 31,917,292 和 20,021,334 字节；各读取 32 KiB 样本后解析 moov，均只有 `avc1` 视频轨，没有音频轨，内嵌 VID 仍为当前 VID，没有新素材身份。样本包含首个媒体分片的一小部分，不是整文件下载或整文件哈希核验。

另外，以 iPhone UA 打开官方精选移动页 `jingxuan.douyin.com/m/video/<作品ID>?app=yumme`，取得匹配目标 `gid` 和 VID 的 `_SSR_DATA` 播放模型。原样请求其 fallback 成功，但仍只有同一组 9 个普通档；没有额外原片候选。桌面 UA 会跳回普通 PC 页，不能把桌面重定向结果算作移动 SSR 测试。

对页面实际加载的 99 份官方 JS 继续追踪，发现模块 `491328` 的下载处理器会以 `origin_type=download_video` 重取详情；请求模块 `529599`、包装器 `674462`、参数模块 `566538` 与来源枚举 `976619` 给出了实际调用依据。随后在新的匿名官方页面中，通过该页面已加载的原始 `g8` 包装器，分别对阳性和目标执行只读详情 GET，使用其正常 `aid=6383`、`request_source=600` 及下载来源枚举；没有伪造账号状态或更改签名算法。

两份响应均 status 0、作品 ID 匹配，但 `video_model` 仍为空。目标仍是同样 12 项，`download_addr.data_size=52,471,983`，没有新增原片身份。两者 `allow_download=false`；目标明确返回 `download_info.fail_info.reason=aigc_forbidden`。网页下载入口会先要求登录，并在 `allowDownload=false` 时停止下载。本次只读详情响应不证明登录后的下载行为，也不把这个下载限制认定为 fplay 未列原片的原因。模块源码的官方 URL、SHA-256 及脱敏响应都已加入 PC 上下文证据。

## 后续：补齐 codec8 的实际覆盖与结果分类

`probe_codec_sweep.py` 的旧扫描跳过了 8，不能称为全值域覆盖。本次只做有既往公开实现和阳性结果依据的小范围对照，没有继续排列任意参数组合：

| 请求 | 阳性 | 目标当前 VID | 目标容器观察 VID |
| --- | --- | --- | --- |
| 本轮网页签发 fallback，只改 `codec_type=8` | HTTP 200、status 10，528,422,694 字节 original | HTTP 200、根/内层 code 1、status 2002，无档位 | 未替换目标签名路径的 VID |
| APK VID-only builder 加 `codec_type=8` | HTTP 200、status 10，同一 original | HTTP 200、根/内层 code 1、status 2002，无档位 | HTTP 200、根/内层 code 1、status 2002，无档位 |
| 精选移动 SSR 自己下发的 fallback，只改 `codec_type=8` | 本轮未重复 | HTTP 200、根/内层 code 1、status 2002，无档位 | 未替换目标签名路径的 VID |

这里的 codec8 仅是已验证可处理的研究输入，没有找到官方 consumer 解释枚举值的含义，不能把它命名为“官方原画/HDR/AV1 编码”。目标的 2002 与其他选择器下 status 10、仅有转码档是不同结果；该差异不能确定拒绝原因，也不证明全部官方路径都拒绝原片。

对目标当前 VID 和从其 MP4 观察到的 VID，另检查已有 `ratio=default` 发布源分发；两个均 HTTP 404。阳性该路径先 302 到 `n98-v-ncdncold.douyinvod.com`，再 302 到生产白名单外的 `4b19a02d-9.sjxydc.com`，请求在此停止。因此这组默认档对照没有完成阳性媒体校验，没有把该白名单错误写成源文件不存在，也没有为此扩大生产媒体主机范围。

## 诊断限额的正确性修复

审查发现新 lineage 工具达到 20 对象或 4 VID 限额后，仍可能对部分扫描报告 `audit_complete=true`。现已补充 `object_limit_reached/objects_omitted`、`vid_limit_reached/vids_omitted`，按唯一身份计数；任何截断都令 `audit_complete=false`、退出码为 2。离线用例验证了恰好达到上限、超过上限以及重复身份，截断计数不会追加网络请求。

该诊断修复不等于修复目标原片取址。目标实际只有 9 个媒体对象和 2 个 VID，未触发限额；本次新增官方实验也没有产生可接入生产的原片。修改后项目现有全套检查为 `108 passed, 112 subtests passed`。
