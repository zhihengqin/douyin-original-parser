# 2026-11-12：新旧素材原片下发与原生链路复查

## 当前结果

尚未恢复没有历史可信原片记录的部分旧素材首次取址。目标
`7706282108947385626` 的验收文件仍为 33,507,060 字节、1080×1920、
101.667 秒、完整 H264/AAC 原片。本轮没有修改生产解析器、部署或重启服务。
不能把普通转码、分轨文件或录入已知样本身份称为通用修复。

以下本地证据均位于 `output/original-recovery-20261112/`，原始回包和凭据
保留在 Git 忽略的研究目录内，不应随部署发布。

## 新作品的直接成功与原片条目消失

`7707234108203650342` 发布时间为 18:44:45。用户 19:09 的解析及随后
绕过 catalog 的直接请求，均取得官方 original：119,146,775 字节、
1280×720、438.001 秒、完整 H264/AAC。成功来源为 `official_quality`。

19:11 的控制请求确认，默认详情和原样 fplay 已有 normal/low/adapt 三个
转码，原片选择 `force_fids=Base64(original),codec_type=5` 仍独立返回原片；
无效选择器只返回三种转码。因此不能说新作品只是因为尚无转码才回退到原片，
也不能说当前 original 选择器无效。

19:22:32 重放保存的同一签发 URL 和选档查询时，只剩四个转码，没有原片。
已验证的原片身份仍可用于官方实时重签。这个样本证明原片的可列举性确实发生
时间变化，但不能据此归纳统一 30 分钟期限或固定下午四点规则。

证据：`fresh-versus-old-current-summary.json`、`fresh-new-selector-controls.json`、
`fresh-new-invalid-control-summary.json`、`fplay-context-reduction-summary.json`。

`7706466342664277290` 的本地成功也有效：185,591,975 字节、完整音视频，
来源为 `official_play_hash`。该分支使用此前已验证的原片身份实时重签；它与当前
fplay 不再列举原片可以同时成立，不代表此次 fplay 直接返回 original。

## 无 original 标签的当前最大 normal 已作媒体实质比较

旧目标当前最大 normal 为 34,092,503 字节，比已知原片还大。完整下载核对官方
文件哈希后，比较发现：原片为 H264 Main@4.0、约 129k AAC，normal 为 H264
High@5.0、约 64k AAC。音视频逐轨 packet 数据不同，同时间解码画面也不同。
这是重新编码，不能因为文件更大、分辨率相同而认定原画。

`original/source` 是可信来源证据之一，不能作为原片的唯一物理定义；官方
`SourceInfo` 也可以不含 quality 字段。但当前这个 normal 不是原片仅改了标签。
证据：`target-current-normal-media-findings.md` 与对应比较 JSON。

## 精选 41.1.0 的真实原生身份和请求

静态核实官方精选身份为 `aid=568863,app_name=douyin_select`，并使用该 APK
自身安全库、许可证和签名证书完成匿名设备注册；未启动 App、浏览器或流量监听。
七种签名头已经实际生成，注册接口正式下发设备身份。

同一身份的官方详情请求结果：

| 作品 | 实际响应 |
| --- | --- |
| `7695305664234589459` | HTTP 200，正确作品详情及 video_model |
| `7706282108947385626` | HTTP 200，`series_control_filter`，无作品详情 |
| `7707234108203650342` | HTTP 200，`series_control_filter`，无作品详情 |

这排除了“所有签名请求都无效”的解释，但不证明被过滤作品已经删除。
目标 `aweme_type=0` 的有限控制仍被相同过滤；正式批量详情 POST 仅请求目标一个
ID，返回 HTTP 200 空正文。没有查询其他作品、剧集或剧集素材。

另对既有抖音 aid=1128 请求准备了真实 wrapper 默认值的单目标对照，仅将
aweme_type 从0改1、recommend_collect_feedback 从0改-1，复用抖音自身正式
匿名身份、库和许可证。三次离线初始化虽成功，但均未注册 HTTP 签名句柄，
因此没有发到服务器。这项参数影响尚未实测排除，不能把它计成目录或上游失败。
证据：`jingxuan-native-request/douyin1128-wrapper-summary.json`。

后续核对发现旧研究签名工具将第12项 collectMode 误名为 channel。当前抖音
41.0.0 的真实普通匿名默认值为810；独立研究副本修正了该配置、网络回调与
首次初始化不应无条件调用 native c 的行为。但0/810/99999的有限离线对照均未
注册 HTTP 句柄；再按真实 `MSManager.frameSign(url,2)` 直接调用仍返回空结果。
本次没有新增上游请求，wrapper参数影响仍未验证，不能把本地工具失败算作平台
已经拒绝这组请求。生产解析器未改。证据：`douyin1128-repaired-signer/REPAIR-RESULT.json`。

使用精选签名、UA、Cookie 重放 Web 签发的 codec8 fplay，仍为业务未授权。
该次签发查询中的 aid/device_id 尚非完整精选原生上下文；匹配精选 aid/device_id
的下一次对照因离线签名初始化失败而没有发出，不能记成正式网络失败。
因此不能据此宣称验证了所有原生鉴权组合。研究工具只做限定重试，未接入生产。

阳性原生模型仅内嵌两个 DASH 视频档和一个独立音频档，下载相关地址指向
114,962,946 字节普通文件，均非已验证的 528,422,694 字节原片。但它确实另行
签发了匹配精选 aid/device_id 的 fallback，带短 `ptoken` 和 `key_seed`；本轮没有
请求这条 fallback，不能把顶层 token_auth 为空说成完全没有原生播放授权。

该 `ptoken` 只有 8 字符，不是目标 Web 详情里 673 字符的 AWS4/GetPlayInfo
预签查询。当前客户端代码只找到已有 token 的消费和透传，未找到从作品 ID
计算它的算法；不能跨作品借用或假定可通过更换 aid 复用。

证据：`jingxuan-native-request/native-runtime-findings.md`、同目录注册/单详情/
批量详情/codec8 的脱敏 summary、`positive-selected-model-summary.json`，以及
`native-ptoken-comparison.md`。完整响应仅保存在 `*.private.json`。

## 新入口与公开实现核对

- 精选 `/yumme/v2/boot/material/video/` 虽接收 item_id，但实际返回模型仅有
  cover/title/cover_style/author_id/author_name/author_avatar，用于新用户弹窗补封面。
  不是视频原片元数据接口，未为此增加网络请求。
- 合拍 `downloadDuetSourceVideo` 的完整调用链只消费现有普通播放地址或缓存；
  URL 转换仅按 need_set_token 补 Cookie，不生成原片身份。
- 官方云 `GetMediaInfos(Vids)` 确实返回独立 `SourceInfo` 和 `TranscodeInfos`，
  但实际 SDK 使用云账户密钥签名。客户端没有找到可替代它的访客凭据或取址算法。
  `GetOriginalPlayInfo` 的响应类型不等于已经发现可调用的匿名入口。
- 精选客户端中已确认 codec_type 赋值为 ByteVC2→4、ByteVC1→3，格式回退为0。
  未找到数值8的客户端定义，不能命名为原片权限或按位组合盲测。
- `video_model_version` 的直接写入属于播放统计；`meta_video_model_type` 属于直播
  模型。`header_dashinfo` 和 `add_dash_quality_type_in_header` 实际处理播放器内部
  Map/对象，不是详情 HTTP 请求头。没有据此为原生详情增加猜测参数或请求头。
- 公开代码增量检索中的“原画修复”分别为普通 play 地址、去除 ByteVC2 限制、
  豆包已有会话生成文件或第三方接入，均没有提供旧抖音作品的首次原片发现机制。

精准证据：`selected-boot-material-model-fields.json`、
`sourceinfo-routes/sourceinfo-route-findings.md`、`public-delta/FINDINGS.md`、
`public-delta/codec-flags-findings.md`。

## 接续与验收边界

接下来需要新的、可重复的官方入口：从目标作品 ID 首次取得可信原片身份或完整
原片地址，并在未使用本地历史原片记录时通过上述金标准比较。当前调查没有建立
这样的新链路，不能宣布算法恢复。生产继续保留新作品直接取原片与已有可信记录
实时重签的能力；普通档仍返回获取原画失败。

本轮仅新增研究记录和脚本，没有生产行为更改，因此没有重新运行生产测试套件。
