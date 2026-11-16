# 抖音旧素材原画：公开实现与目标实测汇总

2026-11-16 最新续查：准确 KMP MIME 校准、播放器刷新、yt-dlp 原片讨论、编辑“原资源”字段和推荐去重监控均未提供两个目标的新原片发现链。完整新增结果及可复核边界见 [当日官方定位与播放授权记录](original-investigation-2026-11-16-official-locate.md) 的续查部分；`7707196543073275177`、`7704677676878925119` 的首次原片解析仍未修复。

随后完成的 [DASH 与全档容器身份实测](original-investigation-2026-11-16-resource-lineage.md) 补查了两目标各 8 个普通 MP4 和新分轨文件，没有找到第三 VID；以实际内嵌 VID 强制选择原片 FID 的对照在阳性取得 528 MB original，两个目标仍只返回普通档。

日期：2026-11-13，Asia/Shanghai。

## 结论与当前状态

本轮完成用户提供的四个 GitHub 项目，以及主动检索得到的相关公开实现核查。现有证据把缺口定位到：**仅凭作品 ID，发现当前公开播放目录没有列出的原片身份或地址**。本地已列出地址的解密、普通档排序、下载代理均不是两个目标当前失败的环节。

`7707196543073275177` 和 `7704677676878925119` 的未知原片首次发现仍未修复。四个指定项目中，jiji262 有独立原片探测；新增 DokiTool-Go 也有官方原片分发探测。两种路径在这两个目标上均为 HTTP 404。其他实现主要取普通播放档、修复详情签名，或把原画能力委托给未公开算法的第三方。

这个结果仅限于所核查版本、当前请求环境和样本。不能据此判定原片已删除，也不能推出全网不存在方法。生产逻辑没有因本轮研究而改变；原画成功样本与已验证历史原片身份的官方重新分发能力仍应保留。

## 目标与验收标准

| 样本 | 当前已确认文件 | 含义 |
| --- | --- | --- |
| `7707196543073275177`，小帅结果参考 | 132,665,774 字节，720×1282，MD5 `96e395ae426871e3fc3294755d54308f` | 已完整下载，抽样视频及音频与目标相符；用作独立结果的身份对照 |
| 同一作品，当前最大普通档 | 57,651,328 字节，MD5 `34c1614a212475882eec27f6664552c7` | 与参考不同的文件；不能把此档改名为原画来通过验收 |
| `7704677676878925119` | 最大已知普通档 81,999,228 字节，MD5 `4989d51ed3c41bf39050b9d41a533486` | 尚未发现可验证原片；没有该作品的独立原片参考文件 |
| `7707561244894580004` | 已禁用历史 catalog，直接取得 50,161,523 字节官方 original | 现有首次原画发现链路仍能成功 |
| `7695305664234589459`，10 月 11 日发布 | 已禁用 catalog，取得 528,422,694 字节官方 original | 发布时间早不必然导致失败；不能把发布时间等同于素材首次入库时间 |

参考文件的大小、编码和内容关系足以建立验收身份，但不能独立证明它与作者上传前的本地文件逐字节相同。参考对象、MD5 和 SHA256 只用于离线比对；未作为网络发现请求输入，也未加入原片 catalog。

## 四个用户指定项目

| 项目与固定提交 | 实际算法 | 验证方式和结果 | 是否补上目标原片发现 |
| --- | --- | --- | --- |
| [yuchen0x1/Short-Video-Analysis](https://github.com/yuchen0x1/Short-Video-Analysis/tree/20cf5ec4ef64339863aede4228c48a3da19f406d) | 详情取 VID，拼 `play/?ratio=1080p&line=0&watermark=0`；代理转发相同地址 | 执行上游 JS 和官方请求；770719 详情成功、播放地址 404；770467 详情及分享回退失败 | 否 |
| [wenhe-cpu/douyin-downloader](https://github.com/wenhe-cpu/douyin-downloader/tree/a51e631299fbbb553604772bf3e0c415f3342dd8) | 为 yt-dlp detail 补访客、时间戳及 secsdk 签名，再选最高无水印格式 | 执行原 patch 与 yt-dlp 2026.10.26；770719 下载完整文件 57,651,328 字节，MD5 与普通档完全相同；770467 没取到详情 | 否 |
| [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/tree/3c045e11aecd58ab076562f1246931b9dd5d909b)，5.1.11 | A-Bogus 与同一访客的 websign 取得 detail；解析 play_addr、bit_rate、download_addr；其他档作为下载回退 | 实际执行原 parser、planner，离线回放已保存的官方目标详情；分别优先选 36,153,126 和 54,305,669 字节普通档，各 4 streams、14 mirrors | 否；本项不是上游身份池的全程实时请求测试 |
| [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader/tree/7c4b8b2252acbfe24728664cc77364bb75a24ecb) | original 模式额外调用加签 play：`ratio=default`、`line=0`、`is_play_url=1`、`watermark=0`、`source=PackSourceEnum_PUBLISH`；按更大体积提升候选 | 使用其 A-Bogus 实现、现有匿名访客，真实复现两个目标请求；均 404、空 JSON、无跳转；签名 SM3 底层以标准库等价原语代替 gmssl | 否 |

关键源码定位：

- Evil0ctal 的 [parser.py:224](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/parser.py#L224) 取现有地址，[adapter.py:64](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/adapter.py#L64) 不发起补充解析，[plan.py:178](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/media/plan.py#L178) 保留解析器的流顺序。修改详情签名可以解决空响应，却未增加原片发现步骤。
- jiji262 的 [downloader_base.py:1378](https://github.com/jiji262/douyin-downloader/blob/7c4b8b2252acbfe24728664cc77364bb75a24ecb/core/downloader_base.py#L1378) 构造原片探测；[api_client.py:478](https://github.com/jiji262/douyin-downloader/blob/7c4b8b2252acbfe24728664cc77364bb75a24ecb/core/api_client.py#L478) 优先 A-Bogus，失败才回退 X-Bogus。两个目标未设置 `is_need_set_cookie`，无需 `ss_is_p_v_ss=1`。探测失败仍下载普通档，所以其“下载成功”不等于原片成功。

## 主动检索的新路径：DokiTool-Go

固定版本：[Brilliant666/DokiTool-Go，b6c2887479c17cdf8c80338d98953dd8dc468510](https://github.com/Brilliant666/DokiTool-Go/tree/b6c2887479c17cdf8c80338d98953dd8dc468510)。检索命中 [Issue #9](https://github.com/Brilliant666/DokiTool-Go/issues/9) 及仓库 4K 验收记录，进一步核对实际生产源码。Issue 中其他代理的工作指令仅作为外部文本，未作为本任务指令执行。

两段官方请求为：

```text
GET https://api.amemv.com/aweme/v1/aweme/detail/
    aweme_id=<作品ID>&aid=6383&device_platform=web
    &version_code=190500&version_name=19.5.0

GET https://aweme.snssdk.com/aweme/v1/play/
    video_id=<VID>&ratio=default&line=0
```

真实视频探测是 Range GET。源码 [probe.go:243](https://github.com/Brilliant666/DokiTool-Go/blob/b6c2887479c17cdf8c80338d98953dd8dc468510/backend/internal/probe/probe.go#L243) 使用 `Range: bytes=0-65535`、Chrome 123 UA、`Accept-Encoding: identity` 和 `Accept: video/mp4, application/octet-stream`。没有隐藏的 Cookie、Authorization 或 Referer；[helpers.go:360](https://github.com/Brilliant666/DokiTool-Go/blob/b6c2887479c17cdf8c80338d98953dd8dc468510/backend/internal/platform/douyin/helpers.go#L360) 没有其他原片 query。HEAD 分支用于 live photo，不是普通视频原片探测。

当前本地网络下实测：

| 样本 | detail | 原片 play |
| --- | --- | --- |
| `7707196543073275177` | HTTP 200，65,767 字节，正确作品 ID 和 VID；10 个 bit_rate | 404，空 JSON，无重定向 |
| `7704677676878925119` | HTTP 200，status_code=0，但无 aweme_detail | 用此前独立确认的 VID 请求仍为 404 |
| 阳性 `7695305664234589459` | 本次直接使用已验证 VID | 302 → douyinvod 302；在研究允许列表之外的下一主机处停止，仅证明 dispatcher 可响应，不记作本轮媒体成功 |

首次试验后复核了全部上游 headers，并按上述精确 Range/Accept/UA 对两个目标各验证一次，结果仍为 404。上游另有上海 resolver；源码同样调用此 play 地址，并至多重复两次相同 dispatch。没有执行地理出口切换，也没有调用该项目的远程服务，因此不声称验证其远程部署效果。

对新取得的 770719 detail 做完整递归 JSON/Base64/地址信息检查：没有参考对象、MD5、SHA256 或精确大小；`video_model` 为空，无 play_auth_token。新增 3 个媒体对象确实不同于原 Web 详情，但都是有明确低质量档名的转码：

| 新增档位 | 字节数 | file_hash |
| --- | --- | --- |
| low_720_0 | 32,180,517 | `dcf162bfd71421878d14d96ac873937d` |
| low_540_0 | 27,769,362 | `150aca6dcd350555b813e03d79ca083f` |
| adapt_low_540_0 | 18,887,016 | `fade905ff900f6de4af253e48a3f529a` |

最大仍为已知 57,651,328 字节普通档。不能把“接口返回了更多条目”当作恢复原片。

## 其他检索命中的公开实现

以下结论来自固定源码审计；没有对明显仅选择现有转码的实现重复下载目标文件。

| 项目／固定提交 | 核查结果 |
| --- | --- |
| [catscarlet 豆包脚本](https://github.com/catscarlet/Download-Original-Raw-Image-from-Doubao-without-Watermark-Experimental/tree/c719640c79bcb697491d5bac4469bedce0ab80dc) | 要求 fallback 已含 key_seed，去掉 force_fids/logo 后固定取 video_1；目标缺该前提，且没有原片资源发现步骤 |
| [sasigai1/douyinxiazai](https://github.com/sasigai1/douyinxiazai/tree/973b864a02339823ad88039a3ac1050488d44191) | 现有 play_addr、bit_rate 按分辨率排序，把最高 1080p 称为原画 |
| [wqvbjhc/MediaBridge](https://github.com/wqvbjhc/MediaBridge/tree/2a086e9e122ba615b411210973caa0f176943617) | 抖音分支依赖第三方网关；未公开它们的原片发现过程 |
| [Su-1003/douyin-fetch](https://github.com/Su-1003/douyin-fetch/tree/4ea33047c55c48c9ba7182135615b357b4ef1caa) | 修 secsdk detail 签名、默认选 normal_1080_0；[技术说明](https://github.com/Su-1003/douyin-fetch/blob/4ea33047c55c48c9ba7182135615b357b4ef1caa/docs/technical-notes.zh.md#L87)明确说原片可能是 4K，但这里拿不到 |
| [2196475465-cloud/video-extract-tool](https://github.com/2196475465-cloud/video-extract-tool/tree/5088130ecde4601e6a66f17460bfd5ae05f5a365) | CDP 取官方 detail，按 play_addr/265/h264 取首 URL；HMAC 是自身代理鉴权 |
| [KAMIENDER/douyin-downloader](https://github.com/KAMIENDER/douyin-downloader/tree/f05426b4cf8204c1c09e8e8038603b535c4f7a54) | 最高 bit_rate、网页数据与浏览器媒体地址回退，没有额外原片请求 |
| [652036/video-unwatermark](https://github.com/652036/video-unwatermark/tree/ebc8b03378195cb2356ebca2ec8d6e99b2439547) | 多个普通解析／第三方／通用下载引擎竞速，首次成功即返回；没有原片身份验证 |
| [dingwei2028/douyin-downloader-local](https://github.com/dingwei2028/douyin-downloader-local/tree/8a05b4affb4387ad4e46d7ec7adc34f687081bf0) | 原片逻辑与 jiji262 同源，新增同地址重试；没有新的官方路径 |
| [lazymicezhu/Douyin-download](https://github.com/lazymicezhu/Douyin-download/tree/8e89d1b52f66a4c20c49e8a777caae5bc2c14c3e) | 原画仍调用 TikHub high_quality，近期 UI/bot 更新未公开底层原片算法 |

另有标题为《Three Faces of One Clip: An Empirical Study of Tiered Transcoding in Douyin's Delivery Pipeline》的 GitHub 仓库，检查时为空仓库。描述本身不能当成实验或可复现算法。

检索覆盖 GitHub 仓库、Issue、commit、公开代码索引及中英文搜索，关键词包括抖音原画／原片／旧素材、original、source、fplay、force_fids、codec_type=8。搜索引擎部分结果无关或出现验证页，grep.app 后续 429，GitHub 匿名 API 限额；恢复系统默认网络设置后 GitHub HTML、raw 与 codeload 可访问。没有把网络失败或空搜索结果记作“没有方法”，也没有声称检索覆盖全网所有内容。

## 对算法升级、新旧素材两接口假说的判断

1. **整体地址解密失效不符合证据。** 新样本可成功；旧目标保存的所有主备地址也可解码。在现有生产 fplay 链路中，两个目标因回包缺少原画身份而失败，尚未进入原画候选的媒体探测；本轮另外执行的 jiji262、DokiTool 分发入口探测已单独记录。
2. **作品发布时间的单一分界不成立。** 10 月 11 日的阳性仍能首次取得原片。但这不否定用户关于素材重发的观察；素材处理历史与发布时间是不同变量。
3. **“原片仍存在、当前目录不再列举”已有直接样本。** `7707234108203650342` 在 11 月 12 日约 19:11 下发原片；19:22:32 同一签发 URL／选择参数仅列转码，之后已知原片身份仍可官方分发。不能据此推断统一失效时长。
4. **资源复用值得继续定位，但成因未证实。** 两个目标的当前 VID 与普通 MP4 内嵌 VID 不同，已验证可指向同一转码文件；它与旧素材复用相容，尚不能独立证明上传去重或特定迁移机制。
5. **没有找到公开的新旧两套取源算法。** 现有 fplay 路径、模型版本、地址封装相同。服务端同接口内的策略、权限或目录变化仍未排除；目前不能把某个 aid、VID 前缀或桶名写成可靠的新旧路由开关。

当前最有区分力的待补证据是：一个可复现实现仅输入目标作品 ID、禁用原片身份缓存后，哪一步官方响应首次给出参考文件的对象、文件身份或地址。应把该请求的构造来源、签发上下文及响应字段连起来，再通过实际媒体验证。最终 CDN 链接已经证明文件可访问，但不能单独反推出它前面的发现步骤。

## 本地解析器复核与代码处理

生产 `original_parser/client.py` 已包含 original 选择、source 兼容分支、实际媒体 probe 和可信 catalog 的官方重新分发。独立回放两个目标的保存回包，原画选择器均为 source_unavailable；770467 的 16 个、770719 两份回包的 32 个地址全部解码成功，没有被筛掉的参考原画。

额外发现两处与本目标无关的韧性边界：第一选择器网络异常不会继续第二分支；首组原画候选全部 probe 失败后也不会退回另一选择器。但本次两目标的两个分支均已正常返回普通档，修这些流程不会生成缺失原片身份，因此未混入本轮成果。

本轮仅增加研究记录和脱敏证据。没有把普通档放宽为原画，也没有把已知参考对象预置成“首次发现”。验证采用上游函数实际回放、官方接口实测和响应身份对照；未为文档变更重复运行无关应用测试。

## 可复核证据

- 同目录 `public-original-research-evidence-2026-11-13.json`：脱敏的固定版本、离线回放、jiji262 官方请求、DokiTool 官方请求及新增档位对照。
- `original-investigation-2026-11-13-existing-route.md`：已有链路的新旧素材和同会话对照。
- `original-investigation-7707196543073275177.md`：完整参考文件、普通档及内容核验。
- `original-investigation-7704677676878925119.md`：另一个目标的协议与媒体对照。
- `upstream-short-video-analysis-audit-2026-11-13.md`、`upstream-wenhe-downloader-audit-2026-11-13.md`：前两个指定项目的可复核结果。

固定源码、下载清单、独立探测脚本、原始响应及完整审计报告存放于 `C:/Users/EDY/AppData/Local/Temp/douyin-test-7707196543073275177/research-roundup/`。完整签名查询、访客凭据和 token 只保存在私有研究文件中，未写入本汇总及脱敏 JSON。

## 20:xx新增线索：播放分发变体、开放平台与 APK

### `douyin-8k-parser` 的 `improve_bitrate` 变体

固定提交：[lijinrui182/douyin-8k-parser，`eb3a1b1ac0e65e380fbcc31fe46918a0b04201a1`](https://github.com/lijinrui182/douyin-8k-parser/tree/eb3a1b1ac0e65e380fbcc31fe46918a0b04201a1)。其代码从详情 `video.play_addr.uri` 取得 VID，调用现有 `/aweme/v1/play/` 分发口，加入 `ratio=default`、`improve_bitrate=1`、`media_type=4`、`vr_type=0`、`is_play_url=1` 和 `source=PackSourceEnum_AWEME_DETAIL`。它没有查询第二份媒体清单或原片身份；最终只以 CDN URL 是否含 `tos-cn-v-0015c800` 标为“8K / Original”，没有 file hash 或媒体内容验真。

依上游参数对 `7704677676878925119`、`7707196543073275177` 和已验证原画阳性 `7707561244894580004` 实测，当前网络会话下三者均为 HTTP 404、无跳转；改用已有匿名访客 Cookie 和网页签名头结果相同。由于阳性也失败，此次网络结果不能证明该分发变体在所有环境均不可用；固定源码本身则没有给出可发现原片对象的新步骤，因此不构成已验证修复。

### 官方视频来源开放接口

抖音开放平台文档：[查询抖音视频来源](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/douyin-video-origin/)。该接口为 `POST /video/source/`，需要 `video.data` 权限及用户授权；公开响应示例给的是来源类型（例如 `source: ["dcar"]`），不是媒体 URL、`file_id` 或 `video_id`。它可回答平台归属问题，不能从任意公开作品 ID 找回上传原片。本次没有访问依赖用户授权的接口。

### 官方 APK 静态审计

32.2.6 APK 的 34 个 DEX 未发现 `GetOriginVideoPlayInfo` 调用、独立视频 `NeedOriginal` 播放动作或从公开 `aweme_id` 映射到原片的请求。`NeedOriginal` 对应录音的 `needOriginalSound`；`originVideoResourceId` 和 `originalVideoInfo` 是剪辑／分享模型字段。详细证据见 [APK 原片 API 审计](douyin-apk-origin-api-audit-2026-11-13.md)。这限定于该 APK 版本，不能排除其他版本或仅对上传者开放的服务端能力。

### 本机复核和结论

本机再次运行 `parse_links.py`，目标 `7707196543073275177` 仍返回 `source_unavailable`，官方原画选择器回来的 8 档没有 `original/source`。`7704677676878925119` 的现有基线同样是 8 档普通转码。没有改生产代码、没有用参考哈希或小帅直链作为网络发现输入、也没有调用第三方解析服务。

新增公开候选仍未找到旧素材原片首次发现链。当前证据支持“目标的原片目录／授权没有由已测公开请求下发”，不支持把原因定性为某个已确认的算法升级或某条新旧接口分流；这两种服务端变化仍可能存在，但尚未定位其可调用条件。故本轮不能声称解析修复完成。

## 2026-11-14 新版官方移动上下文与公开提交复核

### 新版主版原生签名实测

从官方主版 41.1.0（version_code 410101）恢复并适配原生 MetaSec 签名后，以正式匿名注册设备实际发送官方请求；初始化句柄、HTTP callback、session 和 7 个签名头均验证有效。对照结果：

| 请求 | 7707196543073275177 | 7704677676878925119 | 阳性 7695305664234589459 |
| --- | --- | --- | --- |
| 普通移动详情 | HTTP 200/status 0，正确作品 ID；`video_model` 为空，3 档 | HTTP 200/status 0，但只有 `series_control_filter`，无详情 | HTTP 200/status 0，正确 ID，完整 `video_model` 与 fallback，8 档 |
| `/aweme/v1/feed/` 的 `aweme_id` 和 `aweme_ids` | 两种响应均含目标，仍无 `video_model`，3 档 | 两种响应均未含目标 | 两种响应均含阳性，完整 `video_model`，8 档 |
| `/aweme/v1/play/` 发布源选择 | HTTP 404、无跳转 | HTTP 404、无跳转 | HTTP 302 跳转 |

play 测试仅使用作品详情已经下发的 VID 与公开实现中的 `ratio=default`、`line=0`、`is_play_url=1`、`watermark=0`、`source=PackSourceEnum_PUBLISH`。它没有输入小帅参考对象键、哈希或直链。该结果表明这组官方移动签名能驱动阳性播放分发，但没有使目标的 VID 分发到原片。HTTP 404 只描述这次请求上下文，不能单独证明源文件不存在。

之后再用同一原生签名和完全相同的发布源参数请求两个目标普通 MP4 注释中已知的第二个 VID，结果仍是 HTTP 404、无跳转；阳性仍返回 HTTP 302。当前 VID 与内嵌 VID 都没有在这条已公开的 `/aweme/v1/play/` 路径下发现目标原片。此测试仅使用目标转码自身已验证的 VID，不使用小帅参考文件身份。

详情响应差异说明两个失败目标的服务端媒体模型／策略与阳性不同；不支持“本地签名对所有作品都无效”，也没有证据证明增加某个 HDR、codec 或原画 query 参数可改变详情。新版 APK `DetailApi` 不声明 `video_model`、HDR、codec、`video_play_info_type` 或 `support_dash` 选择字段。播放器 `apiForFetcher` 的 DASH/codec 选项属于独立播放取模型路径。`/api/apps/v1/video/get_video_model` 则是 BDP 小程序设备格式能力接口，body 没有作品 ID、VID 或媒体对象，已排除。

首轮原生详情请求曾把 `origin_type` 设为 `1`，这不是 APK 中已知的通用业务场景值。之后按官方通用调用（空 `origin_type`、`request_source=0`）及正式 `message` 分享场景（`origin_type=message`、`request_source=1`、对应 `meta_params`）重测，结果一致：770719 仍为 3 档且无模型，770467 仍为 `series_control_filter`，阳性仍返回完整模型。批量详情 POST 按 APK Retrofit 表单定义请求时，HTTP 200 但响应体为空，故没有从该次请求推断服务端能力。

770719 的 `Aweme.original=1`、阳性为 0。新版 APK 将其定义为作品响应模型的 long 字段；已定位的业务消费者把它用于密友播放埋点，将 0 标为 `content_source="upload"`、非零标为 `"shoot"`。它不是 VID、file_id 或 URL，也没有取媒体用途，不能单独充当新旧素材分流标志。

完整脱敏记录见 [新版官方上下文审计](original-investigation-2026-11-14-native-context.md)；原生结果及私有原始响应索引位于临时研究目录 `C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/` 的 `native-detail-probe-summary.json`、`native-batch-feed-summary.json` 和 `native-published-play-summary.json`。完整签名 URL 与匿名设备身份未写入仓库。

### 新发现 GitHub “原画接口”提交

匿名 GitHub commit 搜索找到 [jiuhunwl/short_videos 的 2026-09-23 提交 `e5fc81d`](https://github.com/jiuhunwl/short_videos/commit/e5fc81d59c91b92fcdb599b51f146e57804b626a)，标题称更新抖音原画接口。逐项审补丁后，它实际仍由已有 VID 拼接 `https://aweme.snssdk.com/aweme/v1/play/?video_id=<VID>&ratio=default&line=0`，再跟踪 302 并把成功跳转标签设为 `original`；没有第二个公开作品 ID → 原片身份发现请求。其“原画接口”称呼不是已验证能处理旧素材的算法证据。

精确搜索官方 VOD SDK 的 `GetOriginVideoPlayInfo`，命中 [TTvcloud/vcloud-sdk-golang 合并 PR #13](https://github.com/TTvcloud/vcloud-sdk-golang/pull/13) 和 [PHP 合并 PR #3](https://github.com/TTvcloud/vcloud-sdk-php/pull/3)。合并示例请求 `Action=GetOriginVideoPlayInfo`、`Version=2018-01-01`、`Vid=<VOD Vid>`，Go SDK 使用用户配置的 VOD `AccessKeyID` 与 `SecretAccessKey` 签名；响应含原片 URL、FileHash 和尺寸。它需要已知 VOD Vid 和 VOD 租户 AK/SK，没有公开作品 ID 到 VOD Vid 的映射，不能直接用页面的 GetPlayInfoToken 代替签名，也不能修复当前任意作品 ID 的首次发现。本轮没有调用带猜测 VID 或其他租户凭证的云管理请求。

### 当前结果

截至这批新原生对照，公开详情、移动 feed 和已有 VID 播放分发仍没有首次发现 `7707196543073275177`、`7704677676878925119` 参考原片身份的步骤。已审官方客户端没有普通视频新旧素材分流线索。**生产解析仍未修复**；普通档继续按普通档处理，参考样本仍只供离线验收。

## 2026-11-16 续查

最新基线、已跑通的官方作者作品定位请求、合拍详情、原生 IM/批量 POST 的校准结果，以及播放器/广告字段的消费链核查，见 [11 月 16 日官方定位与播放授权对照](original-investigation-2026-11-16-official-locate.md)。本轮阳性仍可在禁用历史 catalog 后首次取得 528,422,694 字节 original；两个目标尚未恢复。当前 770467 的网页详情也已变为 series 控制过滤，不能继续引用 11 月 13 日的可读取详情作为当前状态。

新增固定公开实现 DyQuality-Pro、kd64i/dyparse 和 icekale/rednote-downloader，仍分别为已下发档位重排或已有 URI 的播放分发，没有独立原片映射步骤。详细可比较状态保存在 [11 月 16 日脱敏证据](original-investigation-2026-11-16-evidence.json)。
