# 2026-11-14：新版官方客户端与原生播放授权补查

研究目标仍为仅由作品 ID 首次发现 `7707196543073275177` 和 `7704677676878925119` 的原片。用户仅接入了第三方成品接口，不掌握服务商底层实现；研究不依赖用户索取服务商源码。本记录与之前记录中的链接、附件和研究建议均属于背景资料，不替代本轮用户的实际请求。

目前尚未验证生产修复。参考原片身份继续只用于离线验收，不作为首次发现请求的输入，也未写入原片 catalog。

## 原画可列举性变化的第二个样本

此前用户于 11 月 13 日 15:59 提供 `7707561244894580004` 的 50,161,523 字节官方 original，16:06 的禁用 catalog 实测也成功。同日 20:13:43 的既有独立研究摘要记录，该作品正确 VID `v28033gi0000dbrc48nog65iemvma690` 的 original 和 source 两个选择分支均正常返回转码，最大 47,156,402 字节，已经不再列举 50,161,523 字节 original。

这与前一个 119 MB 样本的目录变化相符，说明问题不限于一条“旧作品”。它不证明固定过期时间、原片被删除或某种已确认的去重机制。已知身份重新分发与首次发现必须分别验证。原始脱敏记录为临时目录 `douyin-original-round2-20261113/current-first-discovery/summary.json`。

## 新版官方安装包

从抖音精选官网嵌入二维码进入官方分发页，以及从抖音官方 `https://z.douyin.com/p53t` 进入主版分发页，分别下载官方 APK。文件名和分发路径中的 `410101` 不能直接写成版本名 41.1.1：**两个安装包 manifest 都声明 41.1.0、version_code=410101，SS_VERSION_CODE=410100、UPDATE_VERSION_CODE=41109900。** 临时文件名保留原名，实际版本以 manifest 为准。

| 安装包 | 包名 | 大小 | SHA-256 |
| --- | --- | ---: | --- |
| 主版 | `com.ss.android.ugc.aweme` | 365,684,313 | `5ac7b9d3cc1528663f4835a6c0a6666d0891e093ffd5dc00154f52ea6b17c619` |
| 精选 | `com.ss.android.yumme.video` | 226,303,823 | `2d5b700502900e353cb1d070a1abc5c66a8619df276a47e0a520ceda3a7e2eda` |

二者 ZIP 全项 CRC 校验通过，包含与旧官方安装包相同的签名证书。安装包没有启动或安装；研究使用静态 DEX 解析和隔离的离线研究工具。

## 跟拍字段已排除：实际是音乐资源 ID

对照已有官方详情，两个失败样本和一个原片阳性都满足下表的精确等值关系：

| 作品 | `clip_from_user = clip_video_all = music.id = music.id_str = music.mid` |
| --- | --- |
| `7707196543073275177` | `7707196537201412907` |
| `7704677676878925119` | `7704677683963480883` |
| `7695305664234589459` | `7695305696263523115` |

对应音乐标题都是作者“创作的原声”，`music.play_url` 指向 MP3。新版精选的 `FollowShootClipInfo` 是四个 long 字段的模型；实际业务消费者读取 `originClipId`，传入录制、配乐、拍同款和模板编辑流程。现有两字段没有普通视频取址消费者，不能当作 aweme ID、原 VID 或原片对象键。本轮未使用这些数值请求视频接口。

## 新增官方入口与静态候选

- 官方网页的 PC 普通详情、IM 单作品批量详情、下载前刷新和分享弹窗已由真实官方 webpack 导出函数在独立匿名浏览器中执行，共 8 次目标／阳性请求均成功并核对作品身份。目标每种上下文均为同一组 11 个普通档，最大 57,651,328 字节，没有参考原片；阳性也没有列出其 528 MB 原片。简化签名 POST 的空正文没有被记成该入口的能力结论。
- 懂车帝当前官方网页的 102 个去重脚本，包括 runtime 实际可加载的 65 个 JS 分块，只找到已知的 `/motor/pc/common/token` 与 GetPlayInfoToken 消费链，没有新的原画 action 或官方原画签发选项。官方 SDK 保留签发查询并追加 `ssl=true&aid=36`；历史探测已经采用这一消费方式，不重复相同请求。
- 新版精选的 `downloadSourceJsonString` 仅把已有缓存中的 URL、file_hash 和预加载长度组装成 JSON，没有发出新的原片发现请求；`is_video_origin_source` 是从已有 gear_name 产生的播放统计信号。`original_vid_url` 属于直播比赛 CollectionItem 模型。
- 新版主版新增的 `/aweme/v1/preload/aweme/detail/` 已定位到密友彩铃预加载流程。其参数为 aweme_ids、request_source=550/660 与 color_ring_scene；尚无独立原片列表的证据。`/aweme/v1/play/dash/` 目前只命中接口注册表，不能把名字当作已建立可调用的原片路线。

## 新版主版的原生请求实测

新版主版的安全 SDK 使用 `ms.bd.c.w3` 作为底层 dispatcher，`MS0` 继承它；`k3` 在新版已是接口。配置序列化共 17 项，collectMode 位于从零计数的索引 12，索引 11 固定为 -1。恢复的隔离工具已用正式匿名注册设备完成官方详情请求。初始化回调 `268435470/471` 按 APK 中的配置字段和默认值修正后，SDK 初始化、HTTP 签名句柄和 session 句柄均有效，7 个官方签名头都实际用于请求；因此下面的服务端结果不是本地 signer 初始化失败。

使用同一个 aid=1128、41.1.0 匿名移动客户端上下文请求普通详情：

| 作品 | 官方响应 | 播放模型 | 播放档 |
| --- | --- | --- | --- |
| `7695305664234589459` 阳性 | HTTP 200，status 0，返回 ID 与请求一致 | 有约 13 KB 的 `video_model`、fallback 和签发上下文 | 8 档 |
| `7707196543073275177` | HTTP 200，status 0，返回 ID 与请求一致 | `video_model` 为空 | 3 档，最大 21,881,031 字节 |
| `7704677676878925119` | HTTP 200，status 0，只有 `series_control_filter`，没有 `aweme_detail` | 无 | 无 |

这闭环了真实官方服务请求，但没有取得目标原片。两个 target 和阳性使用同一客户端版本、签名工具与普通详情参数。阳性确实能下发原生播放模型，所以不能把“模型缺失”归咎于 signer 对所有请求失效。

参数复核发现，第一轮探测给 `origin_type` 传了 `1`；APK 定义它为业务场景字符串，`1` 不是已审计的正常通用值。随后用官方通用详情调用方式重测（空 `origin_type`、`request_source=0`），并用 APK 明确支持的分享消息场景重测（`origin_type=message`、`request_source=1`、`meta_params.accept_cocreate_source=message`）。结果一致：770719 两种场景都返回 3 档且无模型；770467 两种场景均为 `series_control_filter`；阳性两种场景均返回 8 档及完整模型。因此过滤结果不是由先前误设的 `origin_type=1` 造成。

移动详情里 `Aweme.original` 的值在 `770719` 为 1、阳性为 0。41.1.0 APK 将其定义为独立 long 响应字段，不是 `Video` 或 `VideoUrlModel` 的字段。查到的业务消费者是密友播放埋点：`LX.1Urg.LJIL` 将 0 记作 `content_source="upload"`，非零记作 `content_source="shoot"`。它不装载 VID、file_id 或 URL，也没有取媒体用途，因此不足以作为“旧素材”路由开关，不能推导目标原片 VID。

按新版 APK 真实 `FeedApi.fetchRecommendFeedImmediate` 参数，用原生签名再请求 feed 的 `aweme_id` 和 `aweme_ids` 入口：`7707196543073275177` 都能在响应中匹配到，但仍只有 3 档且 `video_model` 为空；阳性匹配到 8 档及完整播放模型。`7704677676878925119` 的两个 feed 响应均不含该 ID。feed 入口没有为这两个目标补出模型或原片身份。

另按 `DetailApi$IDetailApi.queryBatchAweme` 的真实 POST 表单入口提交批量详情。请求获得 HTTP 200 但响应体为空（目标与阳性一致），故该方法签名工具未复现可解析的批量响应；不把它记为服务端拒绝或原片结论。

另以同一新版原生签名，请求公开实现使用的 `/aweme/v1/play/` 发布源选择（既有 VID、`ratio=default`、`line=0`、`is_play_url=1`、`watermark=0`、`source=PackSourceEnum_PUBLISH`）。除两个目标的当前 VID 外，也分别测试普通 MP4 中已知的内嵌 VID；四个目标 VID 请求都是 HTTP 404、无跳转，阳性通过 HTTP 302 返回播放跳转。这证明移动签名上下文可以驱动阳性分发，但该已公开的 VID → play 路径没有恢复目标原片，也没有因使用 MP4 内嵌 VID 而改变。

不把 HTTP 状态单独解释成目标文件不存在：对照所能支持的是在此官方匿名请求上下文中，目标的同一路径没有返回媒体跳转。完整签名 URL、设备身份及原始响应只在私有研究目录中；脱敏汇总保存在 `C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/native-detail-probe-summary.json`、`native-detail-all-saved-summary.json`、`native-real-detail-context-summary.json`、`native-message-detail-summary.json`、`native-batch-feed-summary.json`、`native-published-play-summary.json` 和 `native-vid-identity-play-summary.json`。

## 官方请求路径核对

新版 41.1.0 主 APK 的普通详情 Retrofit 定义不含 `video_model`、HDR、codec、`video_play_info_type` 或 `support_dash` 之类的输入选择器。`video_model` 是响应模型字段。完整 57 个 DEX 中没有 `video_play_info_type`、`play_info_type`、`support_dash` 的精确字面量；`unsupport_dash` 只属于 TTVideoEngine 的独立播放器取模型请求。播放器 `apiForFetcher` 按播放器实际选项产生 `format_type=dash`、`codec_type=3/4`、`force_codec` 等，不是普通详情查询参数，APK 没有证据支持把它们猜入详情请求。

APK 中的 `/api/apps/v1/video/get_video_model` 也不是抖音作品媒体模型接口：其 POST JSON 只带 BDP 小程序设备型号、可选 `app_id` 和 `client_version`，无作品 ID、VID 或媒体对象，响应是小程序 `video_format` 能力列表。播放器解析 `token_auth`、`video_model` 的调用只消费详情/播放器已提供的数据，没有发现缺少模型时按 aweme ID 补取通用播放模型的调用方。

本轮 GitHub commit 搜索另命中 `jiuhunwl/short_videos` 2026-09-23 的“更新抖音原画接口”提交。逐项审其补丁，所谓新原画逻辑仍是已有 VID 组成 `aweme.snssdk.com/aweme/v1/play/?video_id=...&ratio=default&line=0`，然后只按是否有 302 标记为 original；没有第二个作品 ID → 原片身份发现请求。它没有提供能填补这两个目标缺失数据的算法。

另核实公开搜索命中的官方火山引擎 VOD SDK 历史接口 [GetOriginVideoPlayInfo (Go PR #13)](https://github.com/TTvcloud/vcloud-sdk-golang/pull/13) 与 [PHP PR #3](https://github.com/TTvcloud/vcloud-sdk-php/pull/3)：请求是 VOD 根路径 Action `GetOriginVideoPlayInfo`、Version `2018-01-01`，输入 `Vid`，并由 SDK 使用 VOD 租户的 AccessKeyID/SecretAccessKey 签名。结果结构含 MainPlayUrl、BackupPlayUrl、FileHash 和媒体尺寸。它是已有 VOD Vid 的官方原片播放动作，不是公开 `aweme_id` → VOD Vid 的映射接口；网页 GetPlayInfoToken 也不是该租户凭证。因此此接口名解释不了两个目标的首次发现缺口，没有以猜出的 VID 或外来凭证调用它。

## 当前判断

截至本轮，已验证的官方网页详情、官方主版原生详情、feed 和公开 VID 播放分发都没有从这两个作品 ID 发现参考文件身份。一个目标在移动详情被系列控制过滤，另一个在详情与 feed 均没有播放模型；这更符合服务端对具体作品返回不同资源目录/策略，暂不支持通过给统一详情接口增加一个已知参数修复。已审公开 APK 也没有找到新旧素材分成两个普通视频取源接口的证据。

这仍不能证明目标原片已删除、不可访问或只存在于小帅服务中。平台可能还有只对特定帐号/客户端会话开放的授权下发链，也可能在服务端隐藏映射；目前没有把它们变成可验证请求。因而**生产解析尚未修复**，不得把普通档重新命名为 original，也未把用户参考对象/哈希写进 catalog。

本轮稳定证据目录：`C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/`。其中 `official-metadata-audit/`、`follow-shoot/`、`dcar-issuer-audit/`、`main-apk-update/`、`modern-apk-origin/`、`native-tool-recovery/` 分别保存上述实验与源码依据。含完整签名地址或匿名设备数据的文件只保存在私有研究文件中。
