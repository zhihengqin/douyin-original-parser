# 2026-11-16：官方定位入口、播放授权与批量请求对照

目标仍是只输入作品 ID，首次发现 `7707196543073275177` 和 `7704677676878925119` 的原片。截至本记录中的实测，**两个目标的生产原画解析尚未修复**。本轮取得了可用的官方作者作品定位请求，并证实不同接口会对同一作品返回不同的可见性和播放模型；尚未由此取得目标自己的原片身份。

后续新增的 SDK DASH、两个目标全部普通档容器 VID、继承资源精确 FID 对照见 [同日资源身份实测](original-investigation-2026-11-16-resource-lineage.md)。新增实测仍未取得目标原片。

用户提供的小帅参考文件只用于离线验收，没有作为发现请求输入，没有加入原片 catalog。本轮没有调用第三方解析服务，也没有改变普通档的质量标签。使用的官方主版是 manifest 声明的 41.1.0、version_code 410101，沿用已经注册的同一匿名设备。

## 本轮网页和原生基线

网页复测通过研究子类禁用 `_catalog_original_candidate()`，因此阳性结果属于本轮首次发现，不依赖历史原片记录。

| 作品 | 网页链路 | 原生普通详情 |
| --- | --- | --- |
| `7695305664234589459` 阳性 | `source` 分支取得官方 `original`，528,422,694 字节；生产媒体探测通过，1920×1248、HEVC 视频和 AAC 音频齐全，486.342 秒 | status 0，匹配作品 ID，约 13 KB 完整 `video_model` |
| `7707196543073275177` | 匹配作品 ID，有模型；两个 fplay 分支各返回同一组 8 个普通档，`source_unavailable` | status 0，匹配作品 ID，`video_model` 为空，3 个 bitrate |
| `7704677676878925119` | 本轮已变为 `series_control_filter`，没有作品详情 | status 0，`series_control_filter`，没有作品详情 |

770467 之前的网页基线曾有完整模型和 8 个普通档，本轮不能继续把旧响应写成当前可用状态。过滤原因是接口返回的上下文信号，不能单独证明作品已删除或原片不存在。

## 跑通官方作者作品定位入口

41.1.0 的 `PostAwemeRepo$TabApi.locatePost` 声明 GET `/aweme/v1/locate/post/`，实际 consumer 为：

`ASLambdaS30S0301100_49 → LX/1UaR → LX/1UyW → ASLambdaS170S0301000_49 → TabApi.locatePost`。

首轮按普通参数对象的零游标构造请求，对阳性和目标都返回 status 5“参数不合法”。继续反追实际定位入口后纠正：

- 作者有 `sec_uid` 时，真实业务优先发 `sec_user_id`，不同时发 `user_id`。
- `locate_item_cursor` 来自正在定位作品的 `create_time × 1000`。零值来自未启用定位的普通构造器，不能当作真实定位流程的默认值。
- `locate_query=true` 确实由 `LX/1UaC` 的定位构造分支传入。
- `max_cursor` 来自已有列表，没有列表时可为 0。
- 实验页大小为 5，是官方客户端支持的正数覆盖分支；实际“他人作品加载更多”配置的静态默认为 12，不能把 5 或先前的 20 写成官方默认。
- 已准备请求中没有重复 query 名称。

保留真实固定字段 `publish_video_strategy_type=2`、`source=0`、`time_list_query=0`、`show_live_replay_strategy=1`、`post_serial_strategy=0`、普通来源 `page_from=2` 和匿名无定位 `location_permission=0` 后，结果为：

| 作品 | 校准后的专用定位接口 |
| --- | --- |
| 阳性 `7695305664234589459` | HTTP 200、status 0；返回列表中包含精确匹配作品，`video_model` 为 13,140 字节，含 fallback |
| `7707196543073275177` | HTTP 200、status 3002056、“视频不见了”，无作品列表 |
| `7704677676878925119` | HTTP 200、status 3002056、“视频不见了”，无作品列表 |

另请求不带 locate 字段的普通 `/aweme/v1/aweme/post/`，770719 与阳性作品的作者均返回 status 0 的正常列表。770719 作者的首屏 5 条作品均早于目标，且返回 `not_login_module.guide_login_tip_exist=true`、“看更多最新作品”；阳性作者该标记为 false。阳性普通列表里虽包含阳性作品，`video_model` 仍为空，而专用定位会下发完整模型。这直接证明“不同入口的响应模型不同”，但还不能证明目标原片缺失由登录态造成。

旧版官方 consumer 也曾把 locate 字段加到 `/aweme/v1/aweme/post/`。本轮对两个目标和阳性各请求一次，三者均 status 3002056，阳性也失败，因此这次旧路径结果不能作为目标特异性拒绝的证据。

## 合拍详情的独立对照

APK 中 `DuetAwemeApi.queryDuetDetail` 是 GET `/aweme/v1/duet/detail/`，参数为 `aweme_id`、`enter_from`；返回的 `duet_info` 包含完整 Aweme。研究请求将 `enter_from` 留空，没有编造具体来源场景。

| 作品 | 结果 |
| --- | --- |
| 阳性 | HTTP 200、status 0，嵌套 Aweme 的 ID 匹配，完整 `video_model` 为 13,156 字节 |
| 770719、770467 | HTTP 200、status 3075、`data is empty`，无 Aweme |

该入口在当前请求环境中可以返回阳性的完整作品数据，但没有为目标补出媒体信息。未因结果为空随机变更场景或身份。

## 系列详情明确要求登录

根据官方真实方法调用，GET `/aweme/v1/series/aweme/detail/`，带 `aweme_id` 和 `aweme_detail_type=0`。两个目标与阳性都返回 HTTP 200、status 8、“用户未登录”。因此本轮没有把它记成目标原片拒绝，也没有伪造登录状态。用户尚未提供可用于对照的登录态文件，研究继续使用公开匿名入口。

## 批量详情仍缺有效响应基线

这轮重新按正式通用重载校准 POST `/aweme/v1/multi/aweme/detail/`：query 的业务字段只有 `location_permission=0`，表单顺序为 `aweme_ids`、`origin_type`、`push_params`、`meta_params`、`card_type`、`request_source`、`from_push`、`item_level`。没有混入其他重载的 cids、selected_co_id 或 verification_ids。

MIME 使用 `application/x-www-form-urlencoded; charset=UTF-8`，最终 127 字节 body 的 uppercase MD5 用于 `x-ss-stub`。先 `prepare_request`，再把 header 名称转为小写后签名，符合已审计的 Cronet 头处理顺序。阳性仍 HTTP 200、0 字节。先成功 GET 并取得 `odin_tt`，同一 requests session 再 POST，结果仍为空。

另外使用独立 Chromium 上下文，在同源页面发出相同 POST；通过 Playwright route 捕获浏览器实际 URL、header 和原始 body，再用已有原生 SDK 对该实际请求签名后放行。阳性仍 HTTP 200、0 字节。浏览器上下文在实验结束后关闭。

继续核对真实业务 producer：`X.1IQr.LJ(String)` 先构造 `listOf(作品ID字符串)`，`LIZJ(List)` 使用 `List.toString()` 生成表单值。它确实为 `[7695305664234589459]`，不会给 String 元素添加 JSON 引号，因此当前单 ID 格式有官方依据。该 KMP 路径只添加 `aweme_ids` 一个业务字段。按此形态再对阳性请求一次：35 字节表单、没有其他业务字段和 location query，仍 HTTP 200、0 字节。

上述结果没有提供可解析的批量响应，不能声称该入口不支持原画，也不能把空正文写成已确认的服务端权限拒绝。当前没有证据支持继续排列 ID 引号或空字段变体。

另外核查了 TicketGuard 的匿名分支。虽然 batch 位于签名缓存路径表中，`TokenFactory.LIZLLL` 在无 `X-Tt-Token` 时将常规 guard type 置 0；无登录 sec UID 的对应分支也置 0。静态/缺省配置中 `enable_attest_sign` 和 `enable_tee_static_sign` 均为 false，ATP 默认只覆盖 `/passport/` 前缀。因此在已知缺省配置下，匿名 batch 会在初始化和证书/签名处理之前返回，不能据缓存表推导“匿名 batch 必须补一份 TicketGuard 证书”。线上运行时配置覆盖尚未捕获，不据此断言所有会话都跳过，也不将该审计当作空正文原因已经查明。

外层还可按运行时配置添加独立 `bd-ticket-guard-request-tlb-group` 标签，缺省为空；该标签不等于证书或证明签名。上述结论只涉及已检查的证明签名分支，不是对所有 `bd-ticket-*` 头的概括。

## 原生 IM 详情未建立有效响应基线

原生 `/aweme/v1/im/aweme/detail/` 是 FormUrlEncoded POST，与此前已测的 PC 网页 `/web/im/…` 路径不同。先按通用 wrapper 的可构造默认值请求阳性，返回 HTTP 200、260 字节可解析 JSON、status 5；`aweme_details`、`filter_list` 等容器均为 null。这个结果表明 POST 并非全部只能返回空正文，但不是有效的作品数据。

继续反追 `ExtDetailChatOperatorImpl.LJJJ(List)` 的真实业务 producer，确认 ID 以 `joinToString(",","[","]")` 构造，没有引号；`origin_type=chat`、`request_source=3`、缺省 `cids=[-1]`、`selected_co_id={}`、`verification_ids=[]`，其余上下文字段按实际默认留空或为 0。该 producer 不携带 conversation、room 或 message token。按这份 178 字节表单再请求阳性一次，仍为 HTTP 200、260 字节、status 5、null 容器。阳性未成功，因此没有对目标继续发同一请求，也没有把结果写成目标原片拒绝。

客户端存在这份业务构造不等于服务器承诺任意匿名会话可调用。原生 IM 详情在本轮仍未复现可用基线，不继续猜测场景或列表格式。

## 播放器 VID 分支没有提供新签发步骤

实际模型字段 `Video.i` 的 JSON 名是 `token_auth`，含 vid、auth、token、hosts、version；`Video.k0` 才是独立 `play_auth_token`。`Video.LJIIZILJ()` 只返回 `token_auth.vid`，`X.1I1L.LJFF()` 的 fallback 是 metadata 中有效的 `token_auth`，不会把普通 `play_addr.uri` 当作授权 VID。

播放准备代码在授权 VID 为空时转到普通 URL 播放，非空才构造 `X.1I1U`。取模型 helper 的 version 2 直接消费 `https://<host>/?<已有完整签发查询>`；version 1 是 `<base>/video/openapi/v1/?action=GetPlayInfo&video_id=<vid>&ptoken=<已有token>&aid=<aid>`。没有在这里发现 token 生成、按作品 ID 换原 VID或独立原片申请。

770719 已保存的原生详情和 feed，以及本轮 fresh detail，均缺 `token_auth`、`play_auth_token`、`meta.token_auth`，模型为空。770467 在这些入口没有详情；阳性则已有完整模型。因此手工把普通 VID 填入 helper 不能补出目标自己的 host/token。

`/aweme/v1/play/dash/` 的唯一字面量消费者也已进一步核实：`X.1acJ` 将其加入 TicketGuard 的 `sign_cache_memory_only_path`，`X.1acK.LIZJ(path)` 读取后返回签名缓存类别 1。它是签名内存缓存路径白名单，不能继续称为已经建立的播放请求方法。旧版 `enable_aweme_video_source_id_fix` 开关只将当前作品 aid 写入 Video/URL model 的 sourceId，修复转换缓存一致性；不修改 uri、播放 URL 或 token VID，没有原 VID 映射。

定位异常主链也已追到结尾：catch 记录日志和计时、更新状态，再通过错误回调到 `PostAwemeModelV2.LJJJJJ(Throwable)`，转换异常并通知 `LX/1VL2` listeners。已检查的这条主链没有按 3002056 切换另一取源 HTTP；未据此扩大断言所有 UI listener 都不会触发其他业务。

770719 的 `is_from_ad_auth=true` 也已核查。41.1 的 Aweme 字段直接消费者用于商业授权期间的删除/隐私操作警示、权限面板参数、埋点和 Parcel 序列化，没有发现按它更换媒体身份或请求另一播放模型的消费者。770467 的已存网页详情该字段为 false，故它也不是两目标共同的失败特征。另一个曾成功首次列出原片的 770756 样本也为 `Aweme.original=1`，不能据 original 的 0/1 推导原片可取性。

## 公开实现新增核查与检索限制

本轮新增固定源码核查包括 maomaoxiaokuoai/duck、SiAnWn/douyinbox、w753951/thunderlite-ios、TYLAB404/blibliTYWeb、zhuimingzhenzhou545-svg/video-downloader，以及 like-ycy 的两个公开脚本版本。主要行为仍是已有 VID 的 `/aweme/v1/play/`、已下发档位排序、SSR，或转发第三方服务。duck 的源码注释明确说其 `1080p` 测得与 `normal_1080_0` 同文件，2K/4K 也返回同文件。

短词搜索另找到 `sinnermm/DyQuality-Pro`，固定提交 `ed46f6f7d5286c6ad2b368e0e6be8c44b9338cc7`。该模块 hook 已下发的 `SimVideoUrlModel` bitrate 列表并重排，没有新的原片发现请求。`kd64i/dyparse` 的优先 `download_addr.uri` 线索也核对了目标自身数据：两个目标的下载 VID 与播放 VID 相同，没有新增可请求身份。

历史公开 [MPPlayerDemo Issue #1](https://github.com/maple1994/MPPlayerDemo/issues/1) 于 2020-02-17 给出的普通 540p 缓存播放地址已经包含 `source=PackSourceEnum_PUBLISH`。这个参数名称本身不能作为原片来源证明。

GitHub 源码和提交检索可以读取；国内外普通搜索受站点验证、超时、空结果和无关结果限制，未声称覆盖所有公开资料，也没有把这些检索限制记作不存在算法。

另通过隔离浏览器补查了 Google 和百度：Google 导航 20 秒超时，百度 HTTP 200 但页面标题为“百度安全验证”，没有取得可审结果正文。没有把验证页当作搜索结果，实验浏览器均已关闭。

## 证据位置

本轮脱敏可比较结果索引保存在同目录 `original-investigation-2026-11-16-evidence.json`；详细私有响应、签名与匿名设备信息保存在临时研究目录，不复制进仓库：

`C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/round6-20261116/`。

关键文件为 `fresh-web-baseline-summary.json`、`fresh-detail-*.summary.json`、`post-baseline-*.summary.json`、`post-locate-calibrated-*.summary.json`、`post-legacy-locate-*.summary.json`、`duet-detail-*.inventory.json`、`series-type0-*.summary.json`、`batch-browser-positive.summary.json`、`native-im-*.summary.json`、`vid-player/FINDINGS.md`、`native-im-detail/FINDINGS.md`、`play-route-consumers/FINDINGS.md`、`public-search/FINDINGS.md` 和 `public-search/short-queries/SHORT-QUERY-FINDINGS.md`。定位入口完整字节码证据和参数修正另保存在上级 `batch-transport-offline-audit/USER-POSTS-LOCATE-FINDINGS.md`；同目录的 `AD-AUTH-FINDINGS.md`、`BATCH-ID-PRODUCER-FINDINGS.md` 和 `TICKETGUARD-ANONYMOUS-FINDINGS.md` 保存其余核查依据。

当前可检验的后续方向是目标自身的合法会话/入口下发差异和与其源素材有关的真实映射调用。本轮没有因搜索或阳性成功而声称两个目标已恢复原片。

## 续查：准确 KMP 传输仍没有有效批量基线

进一步追踪 Android SPI、KMP `FormRequestBody`、TypedOutput wrapper 和 Retrofit `@Body` 后，发现一个需要纠正的真实差异：KMP 路径的 MIME 是 `application/x-www-form-urlencoded`，不带 generic Retrofit form 使用的 `; charset=UTF-8`。表单内容仍只编码一次；单 ID 的实际 body 是 `aweme_ids=%5B7695305664234589459%5D`，35 字节，uppercase MD5 为 `F7FDA997A77D8BE69D46BA67BB908967`。没有 JSON 包装或二次表单编码。

沿用同一正式匿名设备，在最终 prepare 后修正 MIME、将头名称转为小写，再签名同一实际 URL 和 headers。阳性结果仍为 HTTP 200、0 字节；初始化、HTTP callback、session 句柄均有效。本次没有继续对两个目标发送同一请求，因为阳性尚未建立可解析的批量响应。旧 MIME 复现不完全等同于 KMP 发送链，纠正后也没有解决空正文，不能把这项校准称为修复。

KMP 默认 `commonParamLevel=0` 与 generic context 的 `-1` 也已核实：实际处理器只处理大于 0 的覆盖，两者均不触发覆盖。没有找到另一 `appid`、`dp`、host 或协议切换的实际调用依据，不继续排列这些参数。

## 续查：播放器刷新复用既有授权，不签发新原片身份

41.1.0 的离线下载刷新 `X.1Ibg` 要求已有 `video_model`，读取模型中的 `dynamic_video_list[0].main_url`，过期后原样 GET 同一模型的 `fallback_api`。`AVMDLURLFetcherBridge` 的旧实现从缓存读取既有 fallback/keyseed，新实现定位现有播放器，再读取它的 `getAPIString()`。普通预加载的两个取模型／授权回调直接返回 null。已检查的刷新消费者没有按作品 ID、VID 或文件 ID 发行新模型的步骤。

另定位到 `X.1flM`、`X.1KsX` 的 legacy Toutiao 时间戳＋MD5＋VID 路由，与两个目标先前已经实测过的 SDK 路线相同。`X.1KsX` 虽保留 `item_id/category/ad_id` 查询分支，当前 APK 的 `PlayEntity.getItemId/getAdId/getCategory` 实际字节码却直接返回 `0/0/null`；Lynx、西瓜导流和直播回放等消费者也没有因此产生额外查询。因此没有把猜测的作品 ID 或广告上下文拼入这条旧路线重复请求。

这里的空模型结论限于目标的当前原生响应：770719 的网页仍有模型，但只列已知普通档；770467 当前网页没有详情。刷新审计没有证明原片被删除或去重机制成立，也没有为网页目录中缺少的原片补出身份。

## 续查：国外原片讨论与资源关系检索

完整核查 [yt-dlp 原片讨论 #4138](https://github.com/yt-dlp/yt-dlp/issues/4138) 的 45 条评论及两页 timeline，以及 [空响应讨论 #13134](https://github.com/yt-dlp/yt-dlp/issues/13134) 的 12 条评论和相关代码。2023 年的 `c2a1bdb` 只更新设备参数以取得部分 1080p 转码，维护者明确说没有取得 source；2025 年的批量请求签名示例恢复的是 TikTok 元数据，没有给出原片身份发现步骤。本项目已经用更新的官方 SDK 和正式匿名设备发送准确请求，没有从该历史示例找到可补入的抖音批量参数。

timeline 引出的固定研究提交 `3878b69d64ef4734fd81c7edc95e102008bb6dde` 也已核查：仍将已有 `play_addr.uri` 交给 `/aweme/v1/play/`，使用 `ratio=default`、`PUBLISH` 等已测参数。其可选 probe 只在下载后排除与已列转码相同的对象或大小，没有第二个身份发现请求。另一个公开研究 [vagvalas/tiktok-hd-research](https://github.com/vagvalas/tiktok-hd-research) 的固定树 `378db08fea9759f614de4bc6204dc874c0f7dd9d` 中，已取得的 `todo.md` 明确承认尚未获得有效设备身份、尚未验证移动高档；没有把它的假设当作可执行解法。

六个新增 GitHub issue 查询覆盖 `dup_video_id`、`source_video_id`、`original_vid`、素材复用及迁移等词，仅审查每项返回的前 8 条。唯一 `source_video_id + douyin` 命中是本地创作工具的资产字段；替换／迁移结果主要为无关产品或已有下载逻辑，没有新的官方映射请求。后续限定 commit 查询遇到 GitHub secondary rate limit，记录为访问限制并停止扩查，没有当作不存在相关实现的证据。`jiuhunwl/short_videos` 当前树仍为此前已审的 `0c826e72ddf362a9b3eaf97d35972ce7a5bfa0cc`，没有新增取址算法。

国内检索重新取得“抖音原画解析接口”的搜狗结果，仍指向公开源码、第三方 API 文档和 Linux.do 镜像；没有调用这些第三方解析 API。镜像、论坛正文及文本读取服务的有界请求均连接失败，本机现有 localhost 代理也返回连接错误；没有改变系统代理设置。搜索摘要不是协议代码，未用它推断“还存在某个已找到的接口”。

本次准确 KMP 请求与新增静态证据位于 `C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/round7-20261116/`。其中 `kmp-exact-mime-positive.summary.json`、`resource-refresh/FINDINGS.md`、`public-issue-audit/FINDINGS.md` 保存主要结果；KMP 完整 Android 传输审计另在上级 `batch-transport-offline-audit/KMP-ANDROID-TRANSPORT-FINDINGS.md`。本次仍没有取得两个目标的新原片候选，没有修改生产解析逻辑或使用参考身份发起发现请求。

## 续查：原资源／去重字段没有提供另一原片 VID

对两个目标已保存的网页响应、770719 当前原生详情和阳性作离线字段对照，再按 APK 的实际字段和方法引用追踪消费者。目标的 `origin_duet_resource_uri` 为空，没有额外的 `original_video_id/source_video_id`、alias 或 dedup 映射身份；770719 原生 `misc_info` 与阳性相同，仅含业务埋点及青少年视频标记。这里的 770467 网页响应来自历史可见时的保存文件，不能替代当前过滤基线。

`origin_video_resource_id` 确有实际 producer，但来源已经闭环：`X.0KyD/0KyE` 读取 `Aweme.getVideo().LJIIL().LJIILLIIL()`；第一个 getter 返回已有有效 `play_addr_265`，否则返回 `play_addr`，第二个 getter 直接返回 URI。之后把这份身份放入 Intent、`ShareToStoryModel`、编辑及草稿模型。它没有向服务器换取另一 VID，不能凭“origin”名称当作原片发现步骤。

`original_video_info` 属于互动视频模型，目标没有对应业务数据；`delete_duplicate_video_id` 的实际消费者按 `Aweme.aid` 统计重复推荐条目，再上报 `follow_feed_monitor`，并非底层素材去重映射。两目标的 `is_source_HDR=1` 与阳性 0 确有差异，但全 57 个 DEX 的精确字段引用核查显示，除序列化外的唯一业务消费者是屏幕亮度策略，没有切换资源或构造 HTTP 请求。

限定审计与 getter 字节码证据保存在 `round7-20261116/source-relation-audit/FINDINGS.md` 及同目录 JSON。这个结果没有排除其他合法会话或服务端内部映射；它只排除了本轮检查字段所能提供的新请求候选。新增证据 JSON、研究脚本语法及文档空白检查通过，生产修复仍未验证。
