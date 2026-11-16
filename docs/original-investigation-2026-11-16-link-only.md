# 2026-11-16：7707993970332290314 仅输入链接的验收

## 当前结果

只输入 `https://www.douyin.com/video/7707993970332290314`，本项目仍未取得该作品原片。此前完整下载成功依赖工作区已有参考资产 MD5，属于已知资产恢复，不能作为链接解析修复的验收结果。

本次使用新的匿名访客会话，通过研究子类将 `_catalog_original_candidate()` 固定为 `None`，并将 `_read_original_records()` 替换为一旦调用即失败的断言。没有读取原片 catalog、参考文件或此前保存的原片 URL/哈希，没有调用第三方解析服务。

| 作品 | original 选择器 | source 选择器 | 结果 |
| --- | --- | --- | --- |
| 7707993970332290314 | status 10，匹配 VID，9 个转码，原片 0 个 | status 10，匹配 VID，9 个转码，原片 0 个 | source_unavailable |
| 7695305664234589459，对照 | status 10，匹配 VID，16 个转码 | status 10，匹配 VID，1 个 original | 528,422,694 字节，1920×1248，音视频媒体校验通过 |

目标两个回包的最大档位均为 52,471,983 字节。目录只有 adapt、adapt_low、adapt_lower、adapt_lowest、low、normal。这些档位不能作为已发现原片的证据。对照排除了当前会话中全部请求/地址解码均失效的解释；不能由此确定服务端对目标缺少原片行的原因。

脱敏实测结果：`output/link-only-verification-20261116.json`。

## 官方短链可以由长链接生成

主版 41.1.0 APK 的实际调用为 `LX/0y4d.fetchShortenUrl`：GET `/shorten/`，query 字段 target、belong、persist；`LX/0y4c` 的基址为 `https://lf.snssdk.com/`，persist 固定为 `1`；未指定 belong 时，`DefaultShortHostServiceImpl.LIZIZ()` 返回 `aweme`。

按该调用传入目标自己的分享长链接，接口返回 HTTP 200、code 0 和 `v.douyin.com` 短链；用生产 `resolve_id()` 跟随短链，得到精确的目标作品 ID。这纠正了之前“需要用户另给短链”的判断。

把同一新签发短链作为 url 请求 `https://api.amemv.com/aweme/v1/aweme/download/`，实际返回 HTTP 200、JSON `{"status_code":0,"status_msg":"url doesn't match"}`，没有原片候选。这个错误不能证明该接口只接受短链、必须登录或必须签名；本次没有建立其有效下载调用基线。

脱敏实测结果：`output/link-only-official-shorten-20261116.json`。没有将本轮短链当作原片身份或写入 catalog。

## 详情的播放授权仍未建立有效调用

目标当前详情的 `video.token_auth.play_auth_token` 是 GetPlayInfo / 2019-03-15 的完整签发 query。保留该 query 原样，分别请求此前研究过的官方 `vod.bytedanceapi.com` 和 `vod-luna.douyin.com` 根路径，两个域名对目标和对照均返回 HTTP 200、AccessDenied，没有 Result。

这只能说明该调用方式的授权失败，不能说已枚举完全部原片，不能把 AccessDenied 当作目标原片不存在的证据，也没有通过改签名字段来伪造新授权。

脱敏实测结果：`output/link-only-issued-auth-20261116.json`。完整 token 未写入此记录。

## 后续修复的验收条件

只有从链接提取出的作品 ID 及其官方响应进入流程，禁用历史原片记录和外部参考身份后，仍能发现目标原片并通过媒体校验，才算修复本次需求。生产 `_source_candidates()` 的质量标签、大小和域名校验不能替代缺失的发现步骤。用户最新要求仍为完全自建；同日继续检查的官方 VID、签发与播放目录结果见[官方发现续查](original-investigation-2026-11-16-official-link-discovery.md)。

已知资产能被官方重签，证明了该对象仍可访问；它没有解释第三方如何发现对象，也没有证明所有官方入口已被穷尽。目前应将本项目状态标为“链接首次原片发现尚未修复”。

## 详情自带的 `play_auth_token` 与视频云 openapi 模板（同日续查）

目标详情的 `video.token_auth.play_auth_token` 是一条完整的 AWS4 签发 query：`Action=GetPlayInfo&Version=2019-03-15&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKLT…%2F20261116%2Fcn-north-1%2Fvod%2Faws4_request&X-Amz-Date=…&X-Amz-Expires=3600&X-Amz-NotSignBody=&X-Amz-Signature=…&X-Amz-SignedHeaders=&X-Amz-SignedQueries=Action;Version;X-Amz-Algorithm;…;aid;codec_type;format_type;stream_type;video_id&aid=392139&codec_type=0&format_type=mp4&stream_type=video&video_id=<VID>`。它来自链接自身，不含任何外部身份。

在 `douyin-32.2.6.apk` 的 `classes30.dex` 中找到该接口的服务端模板字符串：

```
%s/video/openapi/v1/?action=GetPlayInfo&video_id=%s&ptoken=%s&aid=%s%s
```

`classes4.dex` 的字符串表里另有 AWS4 与 Authorization 相关常量，但原先仅按字节邻近关系就把它们归入播放协议，依据不足。按真实方法复核后，`AWS4-HMAC-SHA256 Credential=` 属于上传 SDK，带空格的 `, SignedHeaders=`、`, Signature=` 属于 QoS；它们不能证明播放 token 会被重排成请求头。定位脚本为 `tools/probe_apk_playinfo_template.py`、`tools/probe_apk_auth_header.py`、`tools/probe_apk_vod_strings.py`；准确消费者与字节码见[授权消费链审计](original-investigation-2026-11-16-auth-consumer-audit.md)。

按模板实测（只重排字段，不伪造签名，不猜测密钥）：

| 调用 | 结果 |
| --- | --- |
| `GET https://vod.bytedanceapi.com/?<原样 token>` | 200，`CodeN=100013 AccessDenied`，`User is not authorized to perform: vod:GetPlayInfo on resource: []` |
| 同上，query 追加 `Vid`/`vid`/`VideoId` | 同上（未列入 `X-Amz-SignedQueries` 的参数被忽略） |
| `POST https://vod.bytedanceapi.com/?<token>` 带 JSON body | 200，`CodeN=100010 SignatureDoesNotMatch`（body 参与签名，`X-Amz-NotSignBody` 为空即需签 body） |
| `/video/openapi/v1/?action=GetPlayInfo&video_id=…&ptoken=<token>&aid=392139` | 400，`CodeN=100024 InvalidAuthorization`，`Invalid 'Authorization' header` |
| 同上，加 `Authorization: AWS4-HMAC-SHA256 Credential=…, SignedHeaders=<空>, Signature=…` | 同样 400 `InvalidAuthorization` |
| 同一路径打 `api-play.amemv.com` | 200，`code 10409 The sign's format is not valid` 或 `10408 Miss the Authorization header` |

更正：这些请求没有建立 Web token 的有效消费基线，不能据此认定缺少 native 密钥或请求头算法。官方 version 1 的 ptoken 与 version 2 的完整签发 query 是不同输入；41.1.0 的实际 version 2/4 分支明确向 fetcher 传入空 auth，不添加 Authorization。当前缺口是目标自己的可用原片发现上下文或成功请求，而不是已经定位到的 native 签名算法。详见[授权消费链审计](original-investigation-2026-11-16-auth-consumer-audit.md)。

补充：把路径换成 `/video/openapi/v1/` 而 query 原样带 token 时，`vod.bytedanceapi.com` 返回 `100010 SignatureDoesNotMatch`（说明路径参与签名，token 是按别的路径签的）；路径保持 `/` 时是 `100013 AccessDenied`（资源解析为空，`Vid`/`video_id` 都没被当成资源）。`api-play.amemv.com` 对 `/video/openapi/v1/` 一律要求 `Authorization` 头，缺头为 `10408`，格式不对为 `10409`。

## 第二个 HDR 作品 `7708052871413075238` 的现场诊断（同日）

用户拿新作品复验，结果同样是 `source_unavailable`。这次的事实：

| 项 | 值 |
| --- | --- |
| desc / 作者 | 「【完整全集免费看,0元直达大结局】…」/ 不止漫剧 |
| `is_source_HDR` / `is_long_video` | 1 / 1 |
| duration / ratio | 330,867 ms / `540p` |
| VID | `v03033g10000dbs82lnog65ls2l3ol5g` |
| `play_addr` | 960×540 / 45,992,041（`tos-cn-ve-51`） |
| `play_addr_265` | 1024×576 / 24,414,636（`tos-cn-ve-51`） |
| `download_addr` | 720×720 / 68,568,404 |
| 详情额外字段 | 只有 `audio`/`bit_rate_audio`/`meta` 等，**无** `play_addr_hdr`；`meta.gear_vqm={"1080p_720p":-1,"720p_540p":-1}` |
| fplay（`force_fids=original` + `codec_type=5`） | 8 行，全部转码，无 original/source；每行都带 `file_hash`/`file_id`；最大 68,568,404（1280×720，`q=normal`） |

八档明细（`output/rows-770805.txt`）：`adapt_lower` 21,138,968（1024×576，bytevc1）/ `adapt_lowest` 28,405,118（1280×720）/ `adapt_low` 28,053,488（1024×576）/ `adapt` 24,414,636（1024×576）/ `normal` 45,992,041（960×540）/ `normal` 68,568,404（1280×720）/ `low` 44,221,246（1280×720）/ `low` 39,027,679（1024×576）。转码桶一律 `tos-cn-ve-51`，没有一条落在 `tos-cn-v-*`。

**结论：**这条与 770799 同一类（HDR 源、长视频、只下发转码档），不是本项目解析出错；它也没有任何本地原片身份记录，因此 `--allow-external` 对它同样无效。默认策略下返回 `source_unavailable` 是本项目当前唯一正确的行为。

## 770805 的原片直链核验与身份登记（同日）

随后用户提供了一条第三方给出的“原片”直链（`v11-default.365yg.com`，桶 `tos-cn-v-0051`，对象 key `ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8`，query 只有 `mime_type` 与 `expire`）。核验结果：

| 项 | 直链实测 | 与详情对照 |
| --- | --- | --- |
| 总字节数 | 140,778,272 | 平台最大转码档 68,568,404（1280×720） |
| 视频轨 | 1280×720 `avc1` | 详情 ratio `540p`，`play_addr` 960×540 |
| 音频轨 | `mp4a` | `has_audio` 必须有 |
| 时长 | 330.867 秒 | 详情 `duration=330867` ms，完全一致 |
| 码率 | ≈3,404 kbps | 最大转码档 ≈1,658 kbps |

该边缘没有 `Content-MD5` 响应头，因此流式读完整 140 MB 计算得整文件 MD5 `351f10c0e8f038973f2a63c9c749cb41`。用该 MD5 打官方 `https://www.douyin.com/aweme/v1/play/?video_id=<VID>&file_id=<VID>&sign=<MD5>`：官方返回 206 + `ftyp` + 同字节数，说明**平台自己认这个对象**。

关键身份证据：官方重签得到的地址是 `https://v26-chd.douyinvod.com/…/video/tos/cn/tos-cn-v-0051/ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8/?…`，与小帅那条**同一个桶、同一个对象 key**，只有边缘前缀不同。这证明两条链接指向同一份 140,778,272 字节的对象，且该对象可以被官方分发接口重签。

因此新增 `--register-original`：把这条直链的核验结论写进本地记录，避免手工改 JSON。登记前强制四项：完整 MP4（`ftyp`+音视频双轨）、moov 时长与详情一致（容差 1 秒）、总字节数不等于详情里任何已知转码档大小、整文件 MD5 经官方分发重签返回同大小 MP4。登记记录仍标为外部来源，默认不参与取址。

**仍未解决的部分：**目前没有建立对象 key `ogAAMdql…` 与 VID `v03033g10000dbs82lnog65ls2l3ol5g` 的可复现映射；仅凭 key 形态不能证明数学上不可推导。这一步仍依赖“外部已知一条链接”，没有完成从作品 ID 首次发现原片。此前将缺口定位到 `Authorization` 签名的判断已被同日消费者审计纠正。

## 选择器全值域穷举：没有任何组合能列出原片（同日最后一轮）

为排除“参数没选对”，固定 `force_fids` ∈ {`original`, `source`, `hdr`, `origin`}、`codec_type` ∈ {0,1,2,3,4,5,6,7,9}，对两个 HDR 作品共 72 次请求逐一记录档位数量、最大字节数与档位名集合（`output/codec-sweep.txt`）：

- 全部组合只返回 `normal` / `low` / `adapt` / `adapt_low` / `adapt_lower` / `adapt_lowest` 六类转码档；
- 最大字节数固定为 68,568,404（770805）与 52,471,983（770799），与默认 `codec_type=5` 完全一致；
- `fid=hdr` 只返回 **1 行**，`size=0`、`quality` 为空，地址形如 `http://v3-d.douyinvod.com/…/video/s/220<VID>…`，实测 `Content-Range: bytes 0-15/45992041` —— 就是那 45,992,041 字节的 540p 同一文件，不是 HDR 源、也不是原片。

**结论：**上述实际测试组合没有让这两个作品的 fplay 列出 `original/source`，原片对象仍可按已知身份官方重签。它没有证明全部参数或官方入口均已覆盖，也不能确定对象 key 只能来自某类授权接口。尚缺少不依赖参考资产的首次发现流程。

## 五个开源仓库汇总与官方默认档通道（同日后续，已落地代码）

按用户给出的 5 个仓库（`jiji262/douyin-downloader`、`Evil0ctal/Douyin_TikTok_Download_API`、`cv-cat/DouYin_Spider`、`yzfly/douyin-mcp-server`、`yuxie2025/douyin`）逐个读取代址逻辑，只有 `jiji262` 实现了原片探测：`core/downloader_base.py` 1329–1432 用 `/aweme/v1/play/?video_id=<uri>&ratio=default&line=0&is_play_url=1&watermark=0&source=PackSourceEnum_PUBLISH` 加 `Range: bytes=0-0`，跟 302 取 `Content-Range` 尾部总长，并要求"原画必须比所选档更大才置顶"。另外 `cv-cat` 无任何原画逻辑、`yzfly` 是分享页 `playwm→play` 去水印、`yuxie2025` 是 Android 壳工程、`Evil0ctal` 只读到 README（源码目录 `raw`/jsdelivr 恒 `link dead`）。

真机裁决（本轮 8 组实验，`output/play-*.txt`）：

| 实验 | 结果 |
| --- | --- |
| 裸 `ratio=default`（无签名/Cookie） | 目标 404 |
| `ratio=default` + `a_bogus` + 访客 Cookie | **普通作品 206，`bytes 0-0/87979914`，与记录 size 一致**；HDR 作品 404 |
| `sign=<真 MD5>` + `file_id` | HDR 作品 206 / 140,778,272（与用户直链同桶同 key） |
| `sign=伪造/缺 file_id/只 file_id/裸` | 全 404（哈希门禁不可绕） |
| 105 组 `source`×`extra`×`ratio` 矩阵 | 全 404 |
| App 侧 3 个 host × 2 ratio | 全 404（连 1080p 都 404） |
| 详情 4 个 uri 当 `video_id` | 4 个 uri 相同，全 404 |
| 批量对 10 条记录跑 `ratio=default` | 命中 3 条（含 6,932,400,516 的 4K 原片），7 条 404 |

结论：`ratio=default` 是唯一"只凭链接"的官方原片通道，但只在平台为该作品登记了默认档时生效；两个 HDR 源作品属于未登记，因此本项目对它们只能报 `source_unavailable`，并把 404 证据写进失败消息。通道已落进 `client.py`（`_play_default_candidate` + `official_parser/abogus.py` + `probe` 几何回填），离线测试 106 通过。完整算法、判定规则与实测数据见[只凭作品链接取原片的算法汇总](original-source-algorithm-2026-11-16.md)。

