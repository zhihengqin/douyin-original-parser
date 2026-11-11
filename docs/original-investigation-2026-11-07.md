# 官方原画恢复调查：2026-11-07

本日已恢复作品 `7695411862271315236` 的历史真实原片，并完成整文件哈希校验；未知新作品的自动原片发现仍未解决。只验证官方取址链路；没有调用第三方解析服务、没有部署，也没有将依赖历史哈希的样本请求接入生产。前一日的背景和历史证据见 [11 月 6 日记录](original-investigation-2026-11-06.md)。下文未恢复的实测结论均对应各自指定链路；最新恢复证据如下。

## 历史 207MB 原片恢复与完整校验

依据 [yt-dlp Issue #7109](https://github.com/yt-dlp/yt-dlp/issues/7109) 中 `file_id` 可等于 VID、`sign` 可采用文件哈希的旧协议线索，在本日实际验证抖音官方入口。请求 `https://www.douyin.com/aweme/v1/play/`，参数为该作品 VID、`line=0`、`file_id=VID`、`sign=历史原片 MD5`、`is_play_url=1`、`source=PackSourceEnum_AWEME_DETAIL`。无需 Cookie，官方分发入口 302 到 `douyinvod.com`，Range 与完整下载均成功。

| 项目 | 本日实测 |
| --- | --- |
| 作品 / VID | `7695411862271315236` / `v03033g10000db5pgnvog65ped9b7co0` |
| 原片对象 | `tos-cn-v-0051/o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE` |
| 完整文件大小 | 207,466,034 字节 |
| MD5 | `28ea5b18e06c59fe18818a92d39fb984`，与历史原片记录一致 |
| SHA-256 | `558ebf618192edef1b0edf820cc841c90f176b2be26f266a2169f9b536b38002` |
| 媒体 | 720×1280、HEVC `hvc1` + AAC `mp4a`、489.686009 秒 |
| 完整校验时间 | 2026-11-07 18:36:30 +08:00 |

对照中，同一 VID 使用 `file_id=VID`，不传 `sign` 或使用当前普通档的 MD5 均返回 404；只有已知的历史原片 MD5 恢复该原片。当前详情递归解开内嵌 JSON 后仍未找到这个哈希。本结果证明该历史原片仍存在且可从官方入口取回，不能继续把该作品原片不存在作为解释；它也不能证明所有作品都能通过这条路线恢复。

**尚未解决：**怎样为没有历史原片记录的新作品自动取得原片 MD5 或等效的官方签发信息。最新目标 `7704869082255904042` 无 sign 的同类请求仍为 404。没有硬编码样本哈希进生产，也没有把普通档、分轨合并或桶名当成原片恢复。

证据位于本机 ignored 目录 `output/original-recovery-20261107/`：`historical-hash-dispatch-comparison.json`、`file-id-original-comparison.json`、`recovered-original-full-file-verification.json`，完整原片为 `7695411862271315236-recovered-original.mp4`。完整请求和临时 CDN 地址仅保留在 `.private.json`。另一个对照的官方 CDN 跳转至当前白名单之外的 `aigccdn.com` 时诊断停止；该结果属于白名单阻止，不能记成官方入口失败，也没有据此放宽生产白名单。

### 第二份历史原片的独立对照

作品 `7685326449011608873` 的 VID 从本机历史官方签发记录取得，为 `v03033g10000dajrmtvog65gsbhbphj0`。对已在 9 月完整验证过的本地参考 MP4 重新计算 MD5，得到 `3392768053d7ba907f0551218347f768`。没有从第三方取得凭据或地址。

同样的 `file_id=VID` 播放请求，不传 `sign` 返回 404；以此 MD5 作为 `sign` 则由官方入口 302 到 `v11-chd.douyinvod.com`，Range 206，实际大小 **61,314,387 字节**。对象 `tos-cn-v-0000c2287/oYGvnMeGhtrrVL0d63QCEDaQITIBWIfA7wWeES` 与历史一致，远程 MP4 校验确认 1920×1080、H264 `avc1` + AAC `mp4a`、175.149 秒。此轮没有重新下载第二份完整文件，也没有计算其本次远程整文件哈希。

这组结果说明“VID 作为原片 FID、以已知文件 MD5 取址”的机制已在两份历史原片上验证；仍不提供未知新作品的原片 MD5。证据：`second-original-hash-control.json` 和 `second_original_hash_control.py`。

## 真实抖音精选 Android 客户端

从 `jingxuan.douyin.com` 官网二维码进入官方下载页，下载并静态核对 41.0.0 安装包：包名 `com.ss.android.yumme.video`，当前应用 ID 为 **568863**，应用名 `douyin_select`；不是网页模型里的 392139。安装包为 220,342,510 字节，SHA-256 为 `1e8b7cfe93703e245687b98277db141ddd80d2178dd2090b10f68523d687b4e2`。

按该包的真实配置向官方 `device_register` 提交加密注册，取得非零匿名设备和安装 ID，随后复用同一身份。官方详情对三个样本均返回 HTTP 200、`status_code=0`，作品 ID、VID 正确。`7704869082255904042` 没有下发 `video_model`；另两条下发 DASH 模型，签发上下文为 `aid=568863`、`codec_type=3`、`format_type=dash`、`stream_type=normal`、`encode_user_tag=ame_dash_tag_base_r1`。成功注册和详情响应不代表已经验证 native 签名。

对两份模型保留其官方签发路径和真实精选上下文，分别做 original/MP4 和 source/MP4 选择。研究脚本直接使用既有候选校验器，没有放宽生产入口对 aid 的校验。

| 作品 | original/MP4 | source/MP4 |
| --- | --- | --- |
| `7695411862271315236` | 正确 VID，只有两个 HEVC 转码，32,811,196 / 38,919,724 字节 | 同样两个转码，没有历史 207,466,034 字节原片 |
| `7695305664234589459` | 正确 VID，四个转码 | 唯一 `original`，528,422,694 字节 |

成功对照经真实 Range/MP4 校验，1920×1248、HEVC、486.342 秒，视频与 AAC 音频轨道完整。真实精选身份没有恢复失败样本。

## 官方签发播放地址对照

保留详情签发的 `file_id`、`sign` / `biz_sign`，给播放分发请求补齐 APK 对应 common 参数和同一匿名设备/安装 ID。入口为官方 `api-play.amemv.com/aweme/v1/play/`。每个样本依次核对原样普通播放地址、原样下载地址，以及下载地址的 `ratio=default&watermark=0&source=PackSourceEnum_PUBLISH&is_play_url=1` 选择。

| 作品 | 原样普通播放 | 原样下载 | default/PUBLISH |
| --- | --- | --- | --- |
| `7704869082255904042` | 302 → CDN 206，19,267,397 字节转码 | HTTP 404，空 JSON 正文 | HTTP 404，空 JSON 正文 |
| `7695411862271315236` | 302 → CDN 206，56,119,942 字节转码 | HTTP 404，空 JSON 正文 | HTTP 404，空 JSON 正文 |
| `7695305664234589459` | 302 → CDN 206，74,188,075 字节转码 | 302 → CDN 206，114,962,946 字节转码 | 302 → CDN 206，528,422,694 字节已知原片 |

这些结果排除了“该官方主机整体不可用”的解释，也说明当前真实精选访客仍没有得到失败样本的原片。空 404 没有提供具体业务原因，不能据此认定原文件已删除。

## 字段解释纠正

- APK 的 `Video.isNeedSetCookie()` 实际映射 JSON **`need_set_token`**。三个真实精选详情均明确为 `false`。仅检查 `is_need_set_cookie` 字段是否缺失不够；当前样本没有无条件附加 `ss_is_p_v_ss=1` 的依据。
- 历史 207MB 样本本日网页详情的 `is_source_HDR=0`，真实精选详情为 `1`。该标记随详情上下文不同而不同，不能据此认定作品 HDR 状态发生时间变化。历史已验证原片为 8 位 Rec.709 SDR，HDR 标记不能解释本次原片缺失。
- 用户附件里的 59,511,551 字节、1080×1920 视频，对应最新目标官方回包已有的 `normal` 对象。分轨和项目标签都没有补充真实原片证据。

## 可复查证据

本机忽略目录 `output/original-recovery-20261107/`：`jingxuan-apk-integrity.json`、`jingxuan-device-registration.json`、`jingxuan-app-model-comparison.json`、`jingxuan-fplay-comparison.json`、`jingxuan-dispatch-comparison.json`。研究脚本分别为 `jingxuan_device.py`、`jingxuan_models.py`、`jingxuan_fplay.py`、`jingxuan_dispatch.py`。原始详情、身份、签名地址只保存在该目录，不随部署包发布。

## 真正的 GetPlayInfoToken 与官方 VOD 路由

复核懂车帝官方网页的 `motor/pc/common/token` 流程，为三个已知 VID 签发了真正的 Base64 JSON `GetPlayInfoToken`。签发时指定 source、codec 5、MP4、original，返回的 AWS 查询串确实包含这些条件。签名器只采用已校验 SHA-256 的公开本地源码，没有调用第三方解析服务。

使用官方签发的完整查询请求 `vod.bytedanceapi.com` 根路由，三个样本均 HTTP 200、VID 正确、无授权错误，但只返回转码：528MB 成功对照有 4 档，历史 207MB 样本有 2 档，最新目标有 3 档。追加 `NeedOriginal=1&GetAll=true` 没有取得原片。另按 APK 的真实模板请求 `open.bytedanceapi.com` 根路由，207MB 与 528MB 样本也成功返回同组转码；将未被签名的附加 aid 从 36 改为 392139，没有改变结果。

这条路线的限制是：懂车帝签发的 API 版本为 **2019-03-15**；当前火山引擎 GetPlayInfo 文档描述的是 **2020-08-01**。当前文档列出的 `NeedOriginal`、`GetAll` 和 `Definition=od` 不能未经验证就认定适用于旧版本。不能修改已经签名的 Version，也不能把连成功对照都遗漏的业务凭证当成原片不存在的证据。

证据：`dcar-source-token-comparison.json`、`native-open-root-comparison.json`、`open-issued-token-aid-comparison.json`。原始凭证与响应保存在对应的 `.private.json` 中。

## 0051 与其他原片桶的新增成功对照

通过官网精选作品页核对作品 ID、模型 VID，再调用现有生产 `source_streams()` 与媒体探测器：

| 作品 | 实际原片大小 | 结果 |
| --- | --- | --- |
| `7694666016072174888` | 509,617,926 字节 | source 分支返回 `original`；1920×1080、H264、422.415 秒；与历史对象一致 |
| `7686615903282203914` | 983,898,857 字节 | source 分支返回 `original`；1920×1080、H264、793.683 秒；对象键与历史一致，桶从 `0015c004` 变为 `0015c800` |
| `7697214397252422921` | 94,459,108 字节 | 第一次 original 选择即成功；1080×1882、H264、216.922 秒；`tos-cn-v-0051` 对象与历史一致 |

三者均通过远程大小、时长、分辨率及视频/音频轨道校验。因此 **0051 桶整体没有失效，v030 类型 VID 也仍可取得真实原片**。983MB 对照的汇总脚本按完整桶路径比较得出 `source_matches_history=false`，它表示桶变化，不表示原片解析失败。没有重新完整下载这些大文件，也没有重新计算整文件哈希。

该组回包中的原片 `file_id` 均等于各自 VID。随后本日的 MD5 分发实验也验证了历史 207MB 原片使用 `file_id=VID`，详见本文开头；官方 CDN 对象键、MD5 与 file_id 仍不能混为一谈。

证据：`bucket-control-comparison.json` 及 `*-bucket-control-{page,model,fplay-*}.private.*`。

## 其他已核对的入口

- APK 的 `/api/apps/v1/video/detail/` 属于小程序 channel_video 组件，需要实际小程序 `app_id` 与内容 ID 上下文。当前没有据此建立原片路线，也没有把抖音 aid 冒充小程序 app_id。
- 用历史 207MB 对象精确路径请求少量公开对象 CDN，分别返回 403 或连接错误，没有恢复对象；没有加入生产白名单。
- 公开搜索部分受验证码、超时或搜索服务限制，不能据此声称全网没有可用方案。

## 官方签发端的版本协商边界

向懂车帝官方签发端提交 `Version=2020-08-01`、`Vid`、`Format`、`Codec`、`Definition=od`、`NeedOriginal=1`、`GetAll=true`，同时保留此入口要求的旧版字段。签发端成功返回 token，但其中的签名版本仍固定为 **2019-03-15**，新版字段未进入签名查询。原样请求 VOD 根路由，528MB 对照返回正确 VID、三个 H264 转码，没有原片。这次没有修改已签名的 Version。

当前官方 SDK 将 `GetPlayInfo` 定义为 2020-08-01、`GetAllPlayInfo` 定义为 2022-01-01；业务方自行生成这些凭证需要自身 AK/SK，不能据此取得任意抖音 VID 的原片授权。这个公开签发入口不支持所测试的新版参数，继续猜测版本字段没有实测依据。证据为 `dcar-version-negotiation.json`。

## 按客户端原有 DASH 容器补做对照

207MB 和 528MB 样本复用真实精选客户端签发的 DASH 模型；最新目标未获 App 模型，复用身份正确的网页模型并按 SDK 选择 DASH。分别验证 original 与 source，source 分支删除转码 `force_fids` 预选列表，同时完整检查 `dynamic_video_list` 和 `dynamic_audio_list`。

| 作品 | DASH 条件下的 source 结果 |
| --- | --- |
| `7695305664234589459` | 仍直接返回完整的 `original` MP4，528,422,694 字节，媒体校验通过 |
| `7695411862271315236` | 只有 540p / 720p 的 `adapt` / `adapt_lowest` 视频及独立音频，没有历史 207MB 原片 |
| `7704869082255904042` | 只有 540p / 720p 的 `low` / `adapt_low` 分轨转码，没有原片 |

这组结果没有支持“强制 MP4 导致漏掉分轨原片”的假设。没有合并分轨，也没有将其当作原画恢复。

另确认 **DASH 转码也能存放在 `tos-cn-v-0051` 桶**：207MB 样本的 540p / 720p 分轨对象位于该桶，路径带 `media-video-*`，官方标记为自适应转码。桶名必须结合容器、实际档位、媒体轨道及作品身份判断，不能单独作为原片的充分证据。现有生产入口先拒绝非 MP4，因此不会选中本次的 DASH 对象；本次未修改桶识别规则。证据为 `native-source-container-comparison.json`。

## 页面与小程序入口补查

- 官方 `open.douyin.com/player/video` 的播放器 JS 仍从 `aid=6383` 网页详情读取 `video.play_addr.url_list[0]`，没有新原片链路。
- 目标 207MB 作品的头条移动页明确 404，西瓜页面只返回挑战页，均没有可核对 VID 的媒体数据。
- APK 的 `/api/apps/v1/video/get_video_model` 实际是 `getSupportFormat`：POST 正文仅有设备、应用及版本信息，没有 VID 或作品 ID，属于设备格式能力查询，未据此发无意义请求。
- 递归解开详情的 JSON 字符串后，没有发现目标的另一媒体 VID 或历史原片 file_id；VOD 回包的 `EncryptKey`、`CipherText` 均为空，没有从这两个字段找到遗漏的媒体数据。

证据为 `official-alternative-page-summary.json`、`official-embed-js-review.json`、`official-model-refresh-route-refs.json`、`embedded-source-metadata-comparison.json`。

## App 两种播放凭证分支

当前官方 APK 的 `PlayTokenAuth` 分别定义 `auth`、`token`、`play_auth_token`、`tv_token`、`hosts`、`version` 和 `vid`。反编译调用方 `X.0GXz.LIZIZ()` 后确认两种不同协议：版本 2 设置 `setPlayAPIVersion(2, null)`，请求 `https://<host>/?<token-query>`；版本 1 设置 `setPlayAPIVersion(1, auth)`，请求 `/video/openapi/v1/?action=GetPlayInfo&video_id=...&ptoken=...&aid=...`。另一个调用方会把 Base64 JSON 的 `GetPlayInfoToken` 提取出来，直接请求 `open.bytedanceapi.com` 根路由。

版本 1 的业务 ptoken 与版本 2 的 AWS 签名查询不能互换。三条网页详情只含原始查询形式的 `play_auth_token`，真实精选详情没有补发 App 专用 `token` / `hosts`。精确读取 Retrofit 注解后，`/aweme/v1/lvideo/token/` 确认是 `getDrmAuthToken(video_id)`，没有把 DRM 接口当成公共原片签发入口。`origin_video_download` 对应合拍下载事件，使用普通 VideoUrlModel，没有发现新取址口。证据为 `native-token-schema.json`、`native-playauth-field-readers.json`、`native-datasource-callers.json`、`native-playback-api-annotations.json`。

## 新鲜网页凭证与原片选择字段

修正此前“本机没有可启动 Chromium”的环境判断：系统已安装的 Playwright Chromium 可正常启动，项目 `.browsers` 则指向另一修订。研究脚本只在自身进程选择已安装版本，并创建新的匿名浏览器上下文；没有改生产浏览器配置或读取个人浏览器资料。

通过隔离浏览器为三个样本重新取得官方详情，核对 VID、凭证签发时间与剩余有效期，再把原始签名查询分别请求 `open.bytedanceapi.com` 和 `vod.bytedanceapi.com` 根路由。六次请求均 HTTP 200，但返回明确的 `AccessDenied`：`User is not authorized to perform: vod:GetPlayInfo on resource: []`，没有媒体列表。结果包括仍能从 fplay 取得 528MB 原片的对照，因此不能据此断言原片不存在；本次可以排除凭证过期的影响。证据为 `fresh-web-playauth-comparison.json`。

另向懂车帝官方签发端提交 `force_fids=Base64(original)`，签发端忽略该字段；它没有进入 `X-Amz-SignedQueries`。将此字段作为未签名可选参数追加到已签查询，三个正确 VID 仍仅返回转码，207MB 和最新目标最高分别为 82,354,519 与 59,511,551 字节。未把这次实验描述为已获原片条件授权。证据为 `dcar-original-fid-token-comparison.json`。

历史 207MB MP4 注释里的 32 位标识仅存在于 `maiya-copy` 元数据，不是已确认的官方 file_id；分别按完整标识和末四位选择均只取得转码。证据为 `historical-metadata-identifier.json`。

## 完整历史签发上下文回放

比较本机保留的 2026-10-16 官方原始详情与本日新鲜网页详情：207MB、528MB 两个样本的 fplay 主机和完整签名路径均相同，查询仅 `device_id` 与 `force_fids` 列表变化。`stream_type`、`codec_type`、`vps`、`vquality` 等原有条件没有变化。两条的下载限制在历史与当前详情中也一致，不能仅凭当前 `aigc_forbidden` 字段解释此次故障。

对旧签发 URL 分别使用当时修复的 original 选择和保留旧预选列表的 source 选择，207MB 样本均返回正确 VID、7 个转码，没有历史对象。528MB 对照使用历史上下文时两次返回空档位元数据（尺寸与大小均为 0）；不能把过时的预选列表当成当前原片不存在的证据，本日新签发上下文的原片成功实测见上文。回放未恢复失败样本，排除了代码替换签名路径的解释。证据为 `historical-full-context-comparison.json`；完整响应留在 ignored 目录。

## 公开技术资料复查边界

隔离浏览器可以渲染 Bing 结果。搜狗后续请求和百度页面遇到验证码后停止；Sourcegraph 返回 403，grep.app 上轮 429 后未继续请求。搜索结果中声称 8K 原画的知乎文章返回 403；恩山 dyparse 帖仅有宣传介绍，下载内容要求登录及回复，没有可核对的取址实现。新发现的旧 ykdl Issue #481 讨论的是 2020 年西瓜 token / 普通 1080p 与加密 DASH，不构成新原片机制。未调用这些页面上的第三方解析服务，不能据此声称全网没有方案。

## 历史文件 ID 库存补查

10 月模型比当前模型多出的两个文件 ID 尾号 `1a72`、`8df9`，已与保存的完整模型逐项对应：前者为 47,202,469 字节、576×1024、H264 的 `low` 档，后者为 33,785,430 字节、576×1024、H264 的 `adapt_low` 档。两者均不是历史 207,466,034 字节原片，不能把它们当作缺失原片的 file_id。新旧详情的 `download_addr.uri` 都是同一 VID，声明大小均为 82,354,519 字节。

证据：`historical-file-inventory.json`。

## 精选官方移动网页的模型与凭证调用

保存并静态审阅 16 份 `yumme-wap` 官方播放器 JS。通用 SDK 的确包含 `/video/openapi/v1/` 请求实现，并分别处理 Authorization 与业务 ptoken；但目标普通作品组件直接读取详情中的 `video_model`，没有发现为这些作品补发另一原片凭证的调用。其他模式里的 `full` 播放分支、旧版 `ib.365yg.com/video/urls/v/1/toutiao/mp4/` 不能据名称推断为当前普通作品的新原片路线。

另核对 `ucmao/media-parser` 当前提交 `f668da6d3c19847b0b415aaae96cda3fe97390bb`：Doubao 仍使用已经借鉴过的 original/codec5 方法；普通抖音实现仍从 `download_addr` 和 `bit_rate` 取址，没有新原片协议。本阶段没有调用该项目的在线解析服务。

证据：`official-player-upstream-review.json`、`official-player-token-callers.json`，以及 `public/` 下保存的官方 JS 与固定版本源码。

## iOS 开源扩展与用户指定项目的补查

完整审阅 [DYYY 固定提交](https://github.com/pxx917144686/DYYY/tree/39561aef7fff5ac039eb2f6a202dd05beba42d89) 的媒体相关源码后，找到了此前未定位的 `getDYYYSrcURLDownload` 定义，位于 `AWEPlayerPlayControlHandler.xm`。它只遍历现有 `originURLList`，按无水印字符串、扩展名或分辨率标记挑选地址，不向服务器申请新原片。普通视频的 `playURL` hook 则从 `bitrateModels` 中挑选最高码率；该实现没有补充本项目缺失的原片请求。

补读用户指定的 Evil0ctal 项目 [Issue #529](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/issues/529) 及全部评论：讨论提供的是 `video.bit_rate` 中 H265 档位与分辨率排序，不是上传原片发现机制。这条 2024—2025 年的讨论也不能代替当前版本的取址实测。未运行这两个项目的在线解析器。

其他新检索仓库中，`prajna0/Douyin` 的所谓原画依赖 TikHub；`chen-zeong/DTV` 是直播项目；`a2137190676/DYParse` 的 fplay 描述没有对应普通抖音原画实现。未将这些宣传或依赖第三方的结果接入自建。

证据：`source-entry-audit.json`、`upstream-original-discussion.json`，以及 `public/pxx917144686-DYYY-AWEPlayerPlayControlHandler.xm.txt`。

## 官方客户端字段与地址续期接口

通过 DEX 字段注解核对字段所属业务，而非只按字符串名称猜测：

| 字段或入口 | 官方实现所属业务 | 本次结论 |
| --- | --- | --- |
| `original_video_info` | `feed.model.playable.InteractiveVideoInfo` | 互动视频模型，不是普通视频原片地址 |
| `origin_download_url` 的相关引用 | 游戏推广安装包下载与日志 | 没有普通作品原画取址调用 |
| `video_sharp_info` | 画面尺寸、矩形位置与 OCR 数据 | 没有原片 URL、file_id 或凭证 |
| `/aweme/v1/video/permission/check/` | `VideoMicroAppAnchorPermissionApi` | 小程序锚点权限检查 |
| `/aweme/v1/im/resources/url_renewal/` | 私信资源 URL 续期 | 请求项包含 `server_msg_id`、`conv_short_id`、`msg_type` 等消息上下文，不是普通作品的公共续签接口 |

本次只读代码，没有伪造会话或消息 ID 请求私信接口。证据：`native-original-field-map.json`、`native-renewal-route-annotations.json` 及 `apk-current/native-url-renewal-{body,item}.java`。

## 官方静态对象域名的有限对照

从官方 APK `classes54.dex` 找到三条真实静态对象 URL，对应 `sf5-hl-cdn-tos.douyinstatic.com`、`sf5-hl-ali-cdn-tos.douyinstatic.com`、`sf6-cdn-tos.douyinstatic.com`。只对这些实际引用的域名做 Range 读取，没有枚举主机。

三个域名均能读取 APK 内置对象：HTTP 206、完整大小 4,184 字节，正文为非 MP4 的文本；这只是路由可达对照，不能称为原片播放成功。使用历史 207MB 原片的精确对象路径时，三者均返回 HTTP 403 JSON，没有媒体数据。该结果没有恢复原片，也不能证明对象已删除。

证据：`native-source-object-references.json`、`native-public-object-probe.json`。

## 14:21 官方取址与媒体校验复测

复用本日已取得且身份匹配的官方网页详情，执行当前生产 `source_streams()` 的两条原有请求；额外发送 `Cache-Control: no-cache`、`Pragma: no-cache`。没有重新取网页详情，没有增加第三方调用，也没有新增参数组合。回包的 `url_expire` 已更新；不能仅凭请求头声称绕过了所有服务端缓存。

| 作品 | original 优选回包 | source 兼容回包 | 本轮实际结果 |
| --- | --- | --- | --- |
| `7704869082255904042` | 9 个转码 | 9 个转码 | 无原片；最高 `normal` 为 59,511,551 字节、1080×1920 |
| `7695411862271315236` | 7 个转码 | 7 个转码 | 无历史原片；最高 `normal` 为 82,354,519 字节、720×1280 |
| `7695305664234589459` | 16 个转码 | 1 个 `original` | 528,422,694 字节、1920×1248、HEVC 原片仍可取得 |

成功对照再次通过实际 Range/MP4 校验：时长 486.342 秒，视频 `hev1`、音频 `mp4a`，实际文件大小与官方声明一致。两个失败样本回包的 VID 都正确，仍缺少原片条目；没有把普通档输出计为恢复成功。

证据：`original-freshness-recheck.json`；完整响应为 `*-freshness-fplay-*.private.json`。

## 真实客户端运行环境检查

已知工具目录中只有 MuMu 安装器和准备脚本。ADB 当前没有连接设备，未发现已安装或正在运行的 Android 模拟器；系统向当前会话报告 `VirtualizationFirmwareEnabled=false`、`SecondLevelAddressTranslationExtensions=false`。没有运行安装器、没有部署 Frida，没有操作个人设备或读取个人浏览器资料。上述检查不等于已经捕获真实 App 请求。

**以上 14:21 及客户端环境检查阶段仍未恢复两条失败作品的原画。** 随后的历史 MD5 分发实验已恢复其中的 207MB 原片，详见本文开头；最新目标仍未恢复。生产取址代码未改动、未部署，也没有因此重复运行已通过的生产离线测试。尚缺的是未知作品的原片元数据来源；当前证据不足以确定具体下发策略变化。

## 针对原片哈希来源的公开资料与新对照

继续检索 GitHub Issues / 提交、CSDN、掘金及公开搜索引擎，读取固定版本源码；没有调用解析服务。检索有实际限制：DuckDuckGo 返回人机验证、博客园要求验证，均停止；Bing 的部分技术查询结果明显偏题，不能据此认定互联网上不存在方案。

| 可核对的资料 | 实际实现及结论 |
| --- | --- |
| [TikTokDownload #399](https://github.com/Johnserf-Seed/TikTokDownload/issues/399#issuecomment-1506474564) | 2023 年从 URI 拼接改为使用已签发的 `url_list`；没有新原片哈希发现方式 |
| [parsehub-kmp 固定版本](https://github.com/obihs2501/parsehub-kmp/blob/d2fd88c1b7cb6684c7d059b07dcd1b161b7d4576/kernel/src/commonMain/kotlin/com/parsehub/parsers/DouyinParser.kt) | 原画仍依赖既有 fplay codec8 或 PUBLISH 302，不提供原片 MD5 |
| [PureSnap 固定版本](https://github.com/CGW-Dev1/PureSnap/blob/dfa338be6623d5572095ddb974a642f0d5711b1a/app/src/main/java/com/puresnap/app/data/parser/MultiPlatformParserEngine.kt) | SSR / RENDER_DATA 地址及 `ratio=1080p`；源码中的“原画”文字不能代替原片证据 |
| [dyvine 固定版本](https://github.com/memenow/dyvine/blob/f38756c53011ff4f4f0750a883ad58285cdfb767/src/dyvine/services/posts.py) | F2 详情、`bit_rate` 和 `play_addr`，没有新的原片信息来源 |
| [SocialMediaStreamDownloader 固定版本](https://github.com/WangYan-Good/SocialMediaStreamDownloader/blob/aa9b6623003370e05cc2eb1f5cb1fab6683d9841/backend/src/platform/douyin/douyin_aweme_external_info.py) | 在详情的 `bit_rate` 列表中按像素面积和码率选档，没有补发原片元数据 |
| [you-get 的头条实现](https://github.com/soimort/you-get/blob/develop/src/you_get/extractors/toutiao.py) | CRC32 签名的 `/video/urls/v/1/toutiao/mp4/VID` 文件列表路线，亦存在于精选官方播放器 SDK；实际请求返回正确 VID，但 528MB 对照为业务 2003、207MB 为 2002，均无档位 |

另将新证实的原片 FID 用于既有 fplay：分别传入完整 VID 与其四位尾号作为 `force_fids`。207MB 和最新目标均只有原有转码；source + 尾号选择下，528MB 对照仍返回并通过完整音视频轨道校验。这组实验没有恢复失败样本的自动原片列表，不应将“已知 FID”误当作自动发现已经解决。

对当前详情签发的 `download_addr` 另保留其官方 `biz_sign`，显式补充 `file_id=VID`，并对照 `ratio=default&watermark=0&is_play_url=1`。207MB 和最新目标的两种请求仍均为 404，未证明业务签名可以替代原片 MD5；528MB 对照在同组显式 FID 请求中仍为 302 → CDN 206，大小与已知原片一致。

此前 APK 字符串扫描中的哈希字段也已追到具体业务：`SourceMd5` 属于私信媒体上传 / 加密内容，`originMD5` 所属模型为私信 `FileContent`，`source_md5` 出现在安装包缓存日志。没有把这些名称当成普通公开作品的原片信息接口。

证据：`vid-fid-selector-comparison.json`、`vid-source-fid-selector-comparison.json`、`issued-biz-sign-original-fid-comparison.json`、`legacy-urls-metadata-comparison.json`、`native-original-hash-members-round34.json`、`native-hash-string-callers-round35.json`，以及 `public/` 下 round29—round44 的公开资料快照和 `apk-current/source-md5-*.java`。未向生产加入样本哈希或未验证路线。
