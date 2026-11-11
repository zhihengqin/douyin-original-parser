# 自建抖音原画取址复查：成功与失败样本的链路差异

检查日期：2026-11-06，追加核验至 2026-11-07。环境：Windows，本地 Python 服务及直接官方 HTTP 请求。

**当前行为说明（2026-11-10）：**本文记录当时的调查、实验代码状态和临时降级策略。生产逻辑现已恢复严格原画模式，只接受官方 `quality=original/source` 或可信 `file_hash` 的官方原片分发结果；普通档、桶名推断及其他转码不会作为成功结果返回，失败时报告“获取原画失败”。

**尚未恢复失败作品的真实原画。** `7695305664234589459` 仍能取得原画；现有证据将分歧定位到不同作品的官方原片下发结果，尚不能确定平台侧的具体原因。

本阶段按用户要求研究自建官方取址，公开源码只作静态参考，没有调用 Snapany、muzzz 或其他第三方解析服务。报告记录时，“原画优先，缺失时返回最高可用画质并标明实际档位”的临时策略已经生效；转码成功不计为原画恢复。该临时策略后来由用户撤回。

## 同一客户端流程，为何结果不同

生产实现位于 [client.py](../original_parser/client.py) 的 `source_streams()`，全部作品执行同一流程：

1. 使用详情 `video_model.fallback_api` 的官方签发路径，保留完整查询上下文，删除 `logo_type`，设置 `force_fids=Base64(original)`、`codec_type=5`。
2. 没有可用原画时，使用同一签发路径，请求 `aid=392139&stream_type=source`。
3. 两次均未取得原画后，才复用已经取得的回包，选择最高可用转码，并保留实际档位标记。

`7695305664234589459` 的第一步同样只返回转码，**第二步才返回唯一的 `original`**。失败作品的第二步仍只返回转码。因此，不能把当前差异解释为客户端为成功样本使用了一套专属链路。

| 作品 | 当前原画结果 | 已验证的媒体依据 |
| --- | --- | --- |
| `7695305664234589459` | 旧 source 分支仍返回 `original` | 528,422,694 字节，1920×1248，HEVC，486.342 秒；音视频轨道及远程大小通过校验 |
| `7695411862271315236` | 当前有效回包无 `original/source` | 历史原片为 207,466,034 字节，720×1280，HEVC，489.686 秒；当前最高可用普通档为 82,354,519 字节 |
| `7704212621922159898` | 当前有效回包无 `original/source` | 当前最高可用普通档为 72,980,971 字节，1080×1920，H264；不能据此称为原画 |

历史 207MB 原片的官方对象为 `tos-cn-v-0051/o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE`，官方 MD5 为 `28ea5b18e06c59fe18818a92d39fb984`。目标是重新取得该原片或有充分依据的原画资源。更大文件、4K 分辨率、`tos-cn-v` 路径及第三方“原画”标签，均不能单独代替原片验收。

## 新验证的 PUBLISH 官方播放入口

公开实现中的另一条路线是 `/aweme/v1/play/`，参数为：

```text
video_id=<目标作品自己的VID>
ratio=default
line=0
is_play_url=1
watermark=0
source=PackSourceEnum_PUBLISH
```

直接对 `www.douyin.com` 和 `aweme.snssdk.com` 各做一次 GET 对照，使用匿名会话，不带 Cookie 或 Referer。只读取有限 Range；成功样本匹配历史对象和大小后，进一步读取 MP4 元数据。

| 样本 | www.douyin.com | aweme.snssdk.com | 验证结果 |
| --- | --- | --- | --- |
| 528MB 成功样本 | 302 → CDN 206 | 302 → CDN 206 | 两次均指向 `tos-cn-v-0015c800/oEEi2UEwPioig7QiANXsdIjJXmBC918aLsAP3`，528,422,694 字节，HEVC，音视频轨道完整 |
| 历史 207MB 失败样本 | 404 | 404 | 无跳转，未取得原片 |
| 用户 `7704212621922159898` | 404 | 404 | 无跳转，未取得原片 |

失败样本另各核对一次 `www.douyin.com` 错误正文：均为 HTTP 404、`application/json`，但正文为空，未提供可用于判断具体原因的业务错误。

这条入口已经通过成功样本证明当前仍可工作，也复现了失败样本与成功样本的差异。该证据不支持“只需换成 PUBLISH 即可恢复原画”的修复，也不能证明原文件已删除。这里验证的是公开匿名请求组合；没有验证 `dingwei2028` 实现中的 `a_bogus` 签名组合，不能将两者混同。

继续复核历史记录还确认：2026-10-15 已由正常作品页对 207MB 样本发起相同 PUBLISH 参数的 `fetch`，观察到页面签名存在，结果仍为 HTTP 404、无跳转。证据为 `output/source-diagnostic-20261015/7695411862271315236-public-play-browser.json`。这是历史结果，不计入本阶段请求数；记录只确认存在签名，没有证明与上述实现的 `a_bogus` 组合完全一致。

公开实现另在播放器的 `isNeedSetCookie()` 为真时增加 `ss_is_p_v_ss=1`。2026-11-07 的真实精选 APK 复核确认，该方法实际对应 JSON 字段 `need_set_token`；三个样本的真实精选详情均明确为 `false`，因此没有据此无条件追加该参数。仅检查 `is_need_set_cookie` 是否缺失不足以判断此分支。

此前按 DokiTool-Go 的旧播放入口做 GET/HEAD，以及按 ING-videoDonload 的 `AWEME_DETAIL` 参数做 HEAD，历史 207MB 样本均为 HTTP 404。这些结果与上表分开保存。

## 抖音精选页面与 codec8

参考 parsehub-kmp 的固定版本，读取官方页面：

```text
https://jingxuan.douyin.com/m/video/<作品ID>?app=yumme
window._SSR_DATA.data.storeState.detail.videoData.result.video_model
```

使用 iPhone UA、匿名会话，核对页面 `gid` 与模型 VID 均匹配目标作品，再请求其签发的 fplay。三个页面与六次 fplay 均已完成，结果如下：

| 样本 | 公开实现的 codec8 请求 | 保留上下文、original 选择与 codec5 |
| --- | --- | --- |
| 历史 207MB 失败样本 | HTTP 200；根/内层 `code=1`，`data.status=2002`，`未授权, 禁止访问`，无资源列表 | 根/内层 `code=0`，`status=10`，7 个转码档，无原画 |
| 528MB 成功样本 | `code=0`，`status=10`，唯一 `original`，528,422,694 字节 | `code=0`，`status=10`，16 个转码档，无原画 |
| 用户 `7704212621922159898` | HTTP 200；根/内层 `code=1`，`data.status=2002`，`未授权, 禁止访问`，无资源列表 | 根/内层 `code=0`，`status=10`，11 个转码档，无原画 |

**授权失败与成功回包缺少原画是两个不同结果。** codec8 没有恢复失败样本，不能作为无条件生产重试加入现有流程。

离线比较网页详情和精选模型还确认：

- 对同一视频，两处签发的 fplay 主机与路径完全相同。查询差别只有 `device_id`、`force_fids` 顺序，以及精选增加 `version_code=26.1.0`。
- 两处模型内嵌的档位相同，三个样本分别为 7、13、10 档，均无原画。内嵌档位数与重新请求 fplay 的档位数可能不同。
- 共同上下文包括 `aid=392139`、`device_platform=unknown`、`codec_type=5`、`stream_type=normal`、`vquality=8`、`vps=6`、`logo_type=default`、`is_order_flow=2` 及相同的 `encode_user_tag` 业务标记。

换成精选页面没有使失败样本重新出现原画。

## 历史对照排除了哪些简单解释

- **不是已确认的本地选档代码回退。** 10 月修复中的完整上下文与 original 选择仍在。历史成功时与当前的 VID、签发路径、查询字段一致；此前回放保存的历史上下文也未恢复 207MB 原片。
- **下载限制不能解释这组差异。** 207MB 失败样本和 528MB 成功样本的下载限制相同：`allow_download=false`、`prevent_download_type=1`、下载失败信息 `code=200142` 等。
- **HDR 标记不是本次新变化。** 207MB 样本在 10 月成功时就有 `is_source_HDR=1`；历史原片 moov 显示 HEVC Main、8 位、Rec.709 SDR。528MB 对照为 `is_source_HDR=0`。这只是一项样本差异，不能据此认定 HDR 为根因。
- **历史消失的两个内嵌档位不是原画。** 207MB 样本模型从 9 档变成 7 档，缺少的是 47,202,469 字节的 `low` 和 33,785,430 字节的 `adapt_low`，均为 540p H264 转码。没有从这些文件中找到原片的真实 `file_id`。
- **不支持按发布时间统一失效的简单解释。** 失败样本发布于 2026-10-11 14:08:32 UTC，成功样本发布于同日 07:16:16 UTC；成功样本稍早。两者作者不同，不能据此排除账号或资源策略差异。
- **不能通用地用 VID 代替原片 file_id。** 528MB 对照回包中的原片 `file_id` 等于其 VID；207MB 样本按 VID 或其末四位选择只得到转码，历史原片真实 `file_id` 仍未知。

此前专项检查的原样 play_auth_token、去除画质限制、文件后缀选择、上下文字段隔离及 MP4 容器对照，见 [README 专项记录](../README.md#自建原画专项复查2026-11-06尚未恢复缺失原画)，本阶段未重复请求这些组合。

## 公开源码依据与适用范围

| 公开来源 | 核对结果 |
| --- | --- |
| [parsehub-kmp，固定 SHA 90e48fac](https://github.com/obihs2501/parsehub-kmp/blob/90e48facd985bf31a6de5dbf409ad882d4464025/kernel/src/commonMain/kotlin/com/parsehub/parsers/DouyinParser.kt) | 提供精选 SSR、codec8 与 PUBLISH 入口；上面分别记录了对失败样本及成功对照的实际结果 |
| [douyin-downloader-local，固定 SHA 8a05b4af](https://github.com/dingwei2028/douyin-downloader-local/blob/8a05b4affb4387ad4e46d7ec7adc34f687081bf0/core/downloader_base.py) | PUBLISH 加 Range 探测；其以文件更大提升“原画”的判断不能单独证明原片，签名组合未作本轮验收 |
| [DokiTool-Go，固定 SHA bc7ec7bf](https://github.com/Brilliant666/DokiTool-Go/blob/bc7ec7bfc69eaa64362b1cc6e0a2c81ab8afb3cd/backend/internal/platform/douyin/request.go) | 旧 play 与多节点选择；失败样本有限 GET/HEAD 均为 404 |
| [yt-dlp PR 17826](https://github.com/yt-dlp/yt-dlp/pull/17826)，[固定 SHA 728fe46f](https://github.com/yt-dlp/yt-dlp/blob/728fe46fbaa97d6f03efcaf9e766d4db63338b8d/yt_dlp/extractor/tiktok.py) | 详情 Cookie/UIFID 与网页签名修复，未增加原片发现机制；当前失败样本已经能取得正确详情 |
| [Url-Down-Vedio PR 9](https://github.com/adventurer002/Url-Down-Vedio/pull/9)，head `c4f89eebb3b8209114bd537c6253d1c40964004d` | 匿名浏览器读取网页详情及播放格式，未提供新的原片选择机制 |
| [media-parser 维护者关于画质的说明，2026-10-28](https://github.com/ucmao/media-parser/issues/29#issuecomment-6460781393) | 说明网页普通画质和项目定位，没有提供可直接验证的 App 原画方案；其对私有协议的推测不是本项目已确认根因 |
| [10 月参考的 original 选择，固定 SHA 36e57ff4](https://github.com/ucmao/media-parser/blob/36e57ff489d23e1037050c9de7f0a39598f8caee/src/parsers/doubao_parser.py) | 当时已恢复 207MB 原片的选择方式继续保留，本次未再次取得该原片 |

搜索范围包括 GitHub 仓库、提交、Issue、PR，以及公开搜索引擎。Sourcegraph 返回 403，部分搜索引擎返回验证码；这些受限结果不算有效方案，也不据此声称已经覆盖全部公开资料。没有执行下载的第三方源码或 APK。

## 代码状态、取证与后续验收

本次网络研究新增诊断和文档，未更改生产取址逻辑，也未部署 Linux。此前降级策略与 83 项测试结果属于前一阶段，本阶段没有重新运行这些测试；此次验证是上表中的真实官方请求及成功样本媒体校验。

本阶段请求记录为 3 次精选页面、6 次精选 fplay、3 次初始旧播放对照、6 次 PUBLISH 对照、2 次 404 正文检查；计数不含公开资料搜索、CDN 跳转和媒体 Range 读取。528MB 原片只做元数据与远程大小校验，没有完整下载或重新计算哈希。

本机脱敏证据位于被 Git 忽略的 `output/original-web-research-20261106/`：

- `original-web-research-summary.json`：汇总结果、限制、公开引用与请求计数。
- `*-publish-dispatch.json`、`publish-dispatch-errors.json`：PUBLISH 两域名对照和空正文 404。
- `*-jingxuan.json`：精选签发查询的 codec8 / original5 对照，包含目标身份、业务状态和档位元数据。
- `saved-context-comparison.json`、`sample-availability-metadata.json`：网页/精选结构与作品属性的离线比较。
- `check_public_dispatch.py`、`check_jingxuan.py`、`inspect_saved_context.py`、`summarize_research.py`：自写取证及离线汇总脚本。

完整签发地址、临时 CDN 地址和原始回包仅留在本机 ignored 文件中，不随部署包发布。

下一项有效修复应先证明一个新的官方请求能为失败样本下发真实原画，再修改生产逻辑。对历史 207MB 样本，需核对目标 VID、原片对象、207,466,034 字节大小及媒体轨道；对缺少历史原片证据的作品，至少需要匹配 VID 的官方 `original/source` 标记及媒体校验。平台删除、保存期限、访问授权和下发策略仍是待确认方向。

## 追加官方路由核验（2026-11-06）

用户要求继续只研究自建官方取址。本次新增的官方请求和媒体对象检查仍未恢复失败作品的原画，也没有据此修改生产取址逻辑。

| 检查 | `7695411862271315236` | `7704212621922159898` | 结论 |
| --- | --- | --- | --- |
| 官方 `/aweme/v1/play/`，`PackSourceEnum_AWEME_DETAIL`、`improve_bitrate=1`，比率 `1080p` / `4k` | 两种比率均 HTTP 404 | 两种比率均 HTTP 404 | 官方播放分档没有为失败作品提供新对象 |
| `aid=6383` 官方详情，加发布策略及 H265/DASH 能力字段 | 正确作品 ID，仍只有普通 `bit_rate`，无 `video_model` | 正确作品 ID，仍只有普通 `bit_rate`，无 `video_model` | 不是可替代生产 fplay 模型的原画入口 |
| 历史 CDN 对象名选择（不能视为 file_id 实验） | `force_fids=Base64("o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE")` 后仍为 7 个转码档 | 不适用；没有历史原片 file_id | 此值是 CDN 对象名，并非已确认的官方 file_id；本实验不能得出真实 file_id 选择器无效的结论 |
| 旧版官方 `web/api/v2/aweme/iteminfo` | HTTP 200、空正文 | HTTP 200、空正文 | 未提供额外详情或播放对象 |

在成功对照 `7695305664234589459` 上，同一播放入口的 `1080p` / `4k` 请求仍能从官方域名开始跳转；其中 `1080p` 的 CDN 二跳返回 HTTP 206、87,098,787 字节，对象与已知 528,422,694 字节 `original` 不同，不能作为原画恢复结果。失败样本的官方页面播放快照也只有约 50 MB 的普通视频对象。

再次读取详情中的 `play_auth_token`，确认其签发参数为 `stream_type=video`、`codec_type=0`、`format_type=mp4`。原样调用 VOD GetPlayInfo 返回 `AccessDenied`；把完整签名查询串再作为 `Authorization` 头会被拒绝为 `InvalidAuthorization`，不是有效的认证格式。当前没有从这个字段建立可用的官方新路由。

**file_id 纠正：**上一版将历史 CDN 对象名误称为原片 file_id。它与官方回包中的 `file_id` 是不同字段，实验脚本与结果的旧文件名也不能作为该映射的证据。10 月 16 日的真实成功证据仍成立：`7695411862271315236-production-original-selection-verified.json` 记录生产代码一次 original 选择即取得 207,466,034 字节原片，并通过对象、大小、时长和音视频轨道校验；该记录没有保存原片 file_id。

脱敏新增记录及脚本位于被 Git 忽略的 `output/original-route-20261106/`：`play-ratio-comparison.json`、`aid6383-detail-profiles.json`、`historical-file-id-selector.json`、`vod-token-authorization-comparison.json`、`browser-media-snapshot.json`，以及对应的 `check_play_ratios.py`、`check_aid6383_detail_profiles.py`、`check_known_historical_file_selector.py`、`check_vod_token_authorization.py`。签名地址和原始 VOD 响应仍只保存在 ignored 文件中。

**截至本次调查，失败样本的原画仍未恢复。**现有成功路径与失败路径差异发生在官方为不同作品下发的媒体对象集合；本轮未证明是作品删除、保存期限或具体账号策略导致，也未发现可安全加入生产代码的新入口。当时采用的“原画优先，缺失时返回最高官方可用档并标记实际档位”策略后来已撤回。

### Evil0ctal/Douyin_TikTok_Download_API 源码复查（2026-11-06）

按用户提供的 GitHub 项目检查中文 README 与当前 `main` 源码，检查时仓库 HEAD 为 `5aa03528d2e974a0de23faf86597b5af3420df55`。该项目介绍的是官方提供的无水印流，并没有把“无水印”表述为“原画”。

其抖音详情入口是 `POST_DETAIL = /aweme/v1/web/aweme/detail/`（`AID=6383`）。媒体解析代码的 `_media()` 读取 `video.play_addr`，再枚举 `video.bit_rate[].play_addr`；`video.download_addr` 被注释为带水印的最后备用地址。检查到的代码路径没有请求 `video_model.fallback_api`、`/video/fplay/`、`force_fids=original` 或 `stream_type=source`，因此没有可移植到本项目的独立原画选择链路。

将该实现实际读取的网页详情字段与本机已保存的官方源档证据对照：

| 作品 | 网页 `play_addr` 大小 | 本项目验证过的原画 | 含义 |
| --- | ---: | ---: | --- |
| `7695305664234589459` | 74,188,075 字节 | 528,422,694 字节 | 即使对照作品当前仍能由官方 source 路径取得原画，该项目所读的 `play_addr` 也是普通流 |
| `7695411862271315236` | 56,119,942 字节 | 历史 207,466,034 字节 | 网页普通流不等于 10 月曾成功下发的原画 |
| `7704212621922159898` | 29,083,616 字节 | 当前未取得 | 与当前普通网页流现象一致，不提供原画恢复证据 |

项目维护的访客身份池、网页 A-Bogus 与 UIFID 签名可以帮助其访问详情等 Web API，但这些实现并未连接到原画选档请求。该项目适合作为网页无水印/多码率流解析器参考，不能用于修复当前 `source_unavailable`；本次只审阅源码并对照已保存的官方详情，没有调用其在线演示或任何第三方解析接口，也没有修改生产取址代码。

固定源码链接：[中文 README](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/5aa03528d2e974a0de23faf86597b5af3420df55/README.zh-CN.md)、[Douyin 媒体解析](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/5aa03528d2e974a0de23faf86597b5af3420df55/src/dtk/platforms/douyin/parser.py#L306-L334)、[详情查询参数](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/5aa03528d2e974a0de23faf86597b5af3420df55/src/dtk/platforms/douyin/params.py#L104-L162)、[详情端点注册](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/5aa03528d2e974a0de23faf86597b5af3420df55/src/dtk/platforms/douyin/endpoints.py#L104-L104)。

为了排除单独实现的 A-Bogus 版本差异，另在官方网页浏览器上下文中对 `/aweme/v1/play/` 发起两种播放请求，使用页面实时签名并保持同一浏览器指纹：PUBLISH 与 `PackSourceEnum_AWEME_DETAIL` + `improve_bitrate=1`。`7704212621922159898` 两种请求均返回 HTTP 404、空 JSON 正文；成功对照 `7695305664234589459` 两种请求均返回 HTTP 302。浏览器观察到两种请求都携带 `a_bogus`。对照的最终 CDN 响应无法由页面脚本读取，但同日直连官方路由的 Range 实测已确认其原片大小为 528,422,694 字节。该结果表明把旧签名器替换成抖音页面当前签名、并切换官方播放来源，都没有改变失败作品的结果。

脱敏回放记录及脚本为 `output/original-route-20261106/browser-signed-publish.json` 和 `check_browser_signed_publish.py`；没有保存签名值或媒体直链。本轮共发起 4 次浏览器签名官方播放请求，未调用第三方接口。此复测仍未恢复 `7704212621922159898` 的原画，也未改生产取址代码。

### DokiTool-Go 上海官方取址路线（2026-11-06 追加）

继续检查 DokiTool-Go 的 PR #27、固定版本源码和 Issue #9 生产回执后，发现一条此前未在本项目失败样本上验证过的变量：**请求从上海出口发往官方播放分发器**。这不是第三方解析接口。

PR #27 的上海 worker 通过官方 `https://aweme.snssdk.com/aweme/v1/play/`，请求 `video_id=<详情中的媒体 URI>&ratio=default&line=0`，接收官方跳转，再对 CDN 文件做有上限的 Range/MP4 元数据探测。主解析器只把作品的媒体 URI 发给该 worker；收到候选后还会校验作品时长、媒体对象路径、文件大小与详情声明的转码档，并与本机测量结果区分。代码与运行约束见[固定版本的官方播放入口](https://github.com/Brilliant666/DokiTool-Go/blob/bc7ec7bfc69eaa64362b1cc6e0a2c81ab8afb3cd/backend/internal/platform/douyin/request.go)、[上海候选校验](https://github.com/Brilliant666/DokiTool-Go/blob/bc7ec7bfc69eaa64362b1cc6e0a2c81ab8afb3cd/backend/internal/platform/douyin/shanghai.go)、[worker 探测器](https://github.com/Brilliant666/DokiTool-Go/blob/bc7ec7bfc69eaa64362b1cc6e0a2c81ab8afb3cd/backend/internal/probe/probe.go)及[部署说明](https://github.com/Brilliant666/DokiTool-Go/blob/bc7ec7bfc69eaa64362b1cc6e0a2c81ab8afb3cd/docs/go-migration/douyin-shanghai.md)。

DokiTool-Go 的[生产回执](https://github.com/Brilliant666/DokiTool-Go/issues/9#issuecomment-6622576682)记录：作品 `7673404708262453110` 的解析实际采用一条上海候选，项目将其标为原画，93,733,891 字节、2160×3840、HEVC。**这份回执没有展示抖音 `quality=original/source` 字段；该项目在此路径按播放分发入口与实际媒体参数判断原画，不能把项目标签说成官方质量字段。**该次记录没有下载整个媒体文件；后续[维护者验收摘要](https://github.com/Brilliant666/DokiTool-Go/issues/9#issuecomment-6622990976)另称完整下载过约 500 MB 的抖音视频，但没有把该下载绑定到同一作品或上海采用追踪。这些公开记录提供了可研究的路线，尚不能证明本报告中的两个失败作品可恢复。

本项目已保存的失败样本测试，是从当前本地出口请求同一个旧 `/aweme/v1/play/` 路由；`7695411862271315236` 与 `7704212621922159898` 均未跳转并返回 404。**按用户最新指示，本任务不再验证上海出口，也不把地区/出口作为当前修复方向。**

另一个公开实现 [Cloudn 的 DouyinParser（固定提交）](https://github.com/mengangs/Cloudn/blob/da0f5f3a4c95e8032017a5d4788098c86095d1d7/CloudnKit/Sources/CloudnKit/Video/Parsers/DouyinParser.swift)会在官方详情明确 `video.is_need_set_cookie=true` 时，给同一官方播放分发器加 `ss_is_p_v_ss=1`。本项目保存的两个失败样本详情没有 `is_need_set_cookie` 字段；因此这只是有条件的请求分支，不构成对目标无条件追加参数的依据。

**恢复判断：DokiTool-Go 的路线仅作历史公开源码记录，不再作为本项目的下一步。**Cloudn 的 `ss_is_p_v_ss=1` 仍是仅在详情明确给出 `is_need_set_cookie=true` 时适用的条件分支；目前详情没有该字段，不据此无条件增加参数。只有目标作品经官方原画档位和媒体元数据核实后，才将有效路线接入生产。本轮没有调用对方 resolver，也没有修改生产取址代码。

### App GetPlayInfo 与 `a=392139` 直链核对（2026-11-06）

继续只检查官方接口后，在本机抖音 Android APK 反编译结果里确认 TTVideoEngine 另有 `/video/openapi/v1/` 请求构造：`action=GetPlayInfo`、作品 VID、`ptoken`、`aid`；播放器还会读取 token JSON 中的 `GetPlayInfoToken` 和 `TokenVersion`，并可将提取后的 token 放进 `Authorization` 请求头。这个实现说明 App 播放 API 与网页 fplay 是不同接口，但不能直接把网页字段当作 App token。

对照三条官方网页详情发现，`video.token_auth.play_auth_token` 是包含 `Action`、`Version` 和 `X-Amz-*` 签名字段的查询串；网页详情没有反编译代码所示的 `GetPlayInfoToken` JSON 包装。把这个网页 token 编码为 `ptoken`，分别请求 `open.bytedanceapi.com` 与 `vod.bytedanceapi.com` 的官方 App 路由，三条样本（`7695411862271315236`、`7704212621922159898`、`7695305664234589459`）均返回 HTTP 400 `InvalidAuthorization`。按反编译 URL 模板直接插入未编码查询串，再请求 `vod.bytedanceapi.com`，三条样本均返回 HTTP 404 `InvalidActionOrVersion`。这些实验只证明**网页 token 不适用于这两种 App 路由拼法**；没有取得真正的 App `GetPlayInfoToken`，不能据此判定 App 接口本身无效，也不能接入生产。

用户指出原片链接使用 `tos-cn-v-0051` 桶前缀，这与本项目已通过媒体校验的历史原片 `7695411862271315236`（对象 `tos-cn-v-0051/o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE`）一致，是有效的桶级线索。新示例对象为 `tos-cn-v-0051/oEAA6yQggBAV3e08AwWEOUdigeDtfGAUMC7bAr`。它的 `dy_q/l` 时间为 2026-11-05 11:58（上海时间），比 `7704212621922159898` 的发布时间晚约 20 小时 39 分；链接标注 4,190 kbps，高于该作品当前 3,657 kbps 的普通档，时长也可能匹配。因此该链接**有可能**是该作品仍可访问时签发的原片地址，但 URL 不含作品 VID，无法仅据时间和码率确认身份。检查时该签名链接返回 HTTP 403、无 `Content-Range`，无法读取文件大小或 MP4 元数据。

为核实 `a` 是否是被遗漏的原画开关，使用浏览器官方详情重新取签名，再请求三个作品的官方 `video/fplay`，只汇总脱敏后的档位、对象与查询参数。失败样本 `7695411862271315236`（7 个普通档）和 `7704212621922159898`（11 个普通档）的 CDN 候选全部带 `a=392139`；成功对照 `7695305664234589459` 的 `original`（528,422,694 字节）也带同一个 `a=392139`。`7704212621922159898` 的最高 `normal` 对象为 `tos-cn-ve-51-ce/owSq7yAEm0NNREAIDBFqATbDwaoOFEHLfd6Deh`，与此前用户提供的 Muzzz 链接对象完全相同；`7695411862271315236` 当前最高 `normal` 对象是 `tos-cn-ve-51/oYBKm1OQYjciBy1EgAEiF4SfK2LQriIBR2hAo8`，其已验证历史原片位于 `tos-cn-v-0051`；成功对照原片对象是 `tos-cn-v-0015c800/oEEi2UEwPioig7QiANXsdIjJXmBC918aLsAP3`。用户新提供的 `tos-cn-v-0051/oEAA6yQggBAV3e08AwWEOUdigeDtfGAUMC7bAr` 虽与历史原片共用 `0051` 桶，但没有出现在三个作品当前官方 fplay 候选中，且对象键不同。由此可见，`a=392139` 是这些 CDN 链接共有的应用标识参数，不是区分原画与转码档的条件；当前 fplay 解析也没有漏传它。`0051` 是有依据的原片桶线索，但尚未提供目标作品缺失的对象键或 file_id。

由于新示例可能属于 `7704212621922159898`，另用该 VID 的新鲜官方浏览器详情，保持完整签发上下文并通过回包 VID 校验，尝试将 `force_fids` 分别设为 `Base64(对象名)` 和 `Base64(0051/对象名)`，各自测试原有 `stream_type` 与 `stream_type=source&method=1`。4 次官方 fplay 回包均为正确 VID、`status=10`、11 个候选，仍无 `original/source`，也没有返回示例对象。现有证据说明 API 没有把这两个 CDN 对象名当作可用的 `force_fids` 选择值；这不能证明对象不存在，也不能证明该示例不属于目标作品。

脱敏的 App 路由结果、直链 Range 检查、fplay 档位摘要及 `0051` 对象 selector 结果位于 Git 忽略的 `output/original-route-20261106/`：`app-openapi-ptoken.json`、`app-openapi-ptoken-raw.json`、`fplay-aid-summary.json`、`0051-object-selector.json` 及对应脚本。直链只在进程环境变量中短暂使用，没有写入结果文件；本次未下载整段视频，也未调用第三方解析服务。

**截至本次调查仍未恢复这两条作品的真实原画。**`0051` 桶、发布时间和码率支持该示例可能是 `7704212621922159898` 的原片直链，但过期链接无法验证媒体身份；把其对象名或完整桶路径交给官方 fplay 也没有重新返回它。`a=392139` 在原画与普通档中一致。App API 留下的另一项未验证差异是 App 专用 token 的来源与签发流程；现有公开网页详情不能提供该 token。本轮没有修改生产代码，报告时沿用的最高画质降级后来已撤回。

### 原片桶识别补强（2026-11-06 历史实验，已撤回）

用户补充“原画桶的链接是 0051”后，复核了历史原片对象和当前选档器。已验证的历史原片对象使用 `tos-cn-v-0051`；此前成功对照的官方原片使用 `tos-cn-v-0015c800`，而当前普通转码对象使用 `tos-cn-ve-*`。因此桶前缀可以作为官方地址的辅助原片证据，但不能单独证明一个脱离作品 VID 的临时地址属于某个作品。

当时的实验代码曾在解码 fplay 回包后识别 `tos-cn-v-<桶名>` 路径，并把它作为 `source_evidence=original_bucket:<桶名>`；后来发现桶名不能独立证明实际档位，已从生产逻辑删除。当前接口原始 `quality` 未标为 `original/source` 时，即使对象位于 `tos-cn-v-*` 也会失败。

本次对用户给出的 `tos-cn-v-0051/oEAA6yQggBAV3e08AwWEOUdigeDtfGAUMC7bAr` 直链使用生产 Chrome UA、抖音 Referer 和 Range 请求，并替换 `v11`、`v26`、`v95` 三个镜像主机逐一检查，均返回 HTTP 403，没有 `Content-Range`，所以无法取得媒体大小、时长或 VID 身份。该对象也没有出现在 `7704212621922159898` 的新鲜官方 fplay 回包中；把对象名、`0051/对象名` 或 `a=392139` 作为 `force_fids` 均未让官方接口重新下发它。由此可以确认 0051 是有效的桶线索，但当前没有足够证据把该过期地址绑定到目标作品，也不能凭它恢复原画。

当时的桶推断选档实验曾加入 [client.py](../original_parser/client.py)，相关测试及结果仅反映该历史版本，已由严格原画选档取代。目标作品是否恢复原画仍以官方原画档位或已验证官方原片分发结果为准。

本机没有可启动的 Chromium；使用无 UIFID 的匿名请求读取详情又被官方接口以 HTTP 403 拒绝，因此本轮没有成功完成实时生产解析对照。诊断脚本此前保存的最新脱敏 fplay 摘要仍显示目标 `7704212621922159898` 的 11 个官方候选没有 `tos-cn-v-*` 原片桶，最高档是 `tos-cn-ve-51-ce` 普通转码；成功样本的已验证原片路径则符合 `tos-cn-v-*`。这可用于确认当前生产分支不会意外将该目标普通档标成原片，但不能替代新的官方下发或本轮直播请求。
