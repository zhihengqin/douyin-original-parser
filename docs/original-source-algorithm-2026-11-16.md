# 只凭作品链接取抖音原片：五个开源实现的取址算法汇总与本项目落地

> **后续更正与当前实现：**本页保留早期实验记录。下文关于“默认档404证明没有登记原片”“sign是必需门禁”“必须取得未知32位原片FID”的定性超出证据，已被后续单变量实验纠正。当前代码新增内嵌模型选档、逐路媒体校验、即时原画身份重新分发，并修复QuickTime校验和默认档下载；真实恢复样本与仍失败的目标请以[最新修复验收](original-investigation-2026-11-16-astar.md)为准。

记录日期：2026-11-16。适用范围：`douyin-original-parser` 的取址层（`original_parser/client.py`）。
本文只收**官方接口**路线；所有结论都在本机真机上跑过，命令与原始输出见第 8 节和 `output/play-*.txt`。

## 0 结论摘要

| 通道 | 是否只需要"作品链接" | 命中范围（本机 10 条作品样本） | 是否需要整文件 MD5 |
| --- | --- | --- | --- |
| P1 fplay `force_fids=original` | 是 | 老作品，平台下发了 original/source 档 | 否 |
| P2 fplay `stream_type=source` | 是 | 同 P1 的兼容备用 | 否 |
| **P3 官方 `/aweme/v1/play/?ratio=default`** | **是** | **10 条里 3 条；其中一条是 3840×2160 / 6.93 GB 的 4K 原片** | **否** |
| P4 `/aweme/v1/play/?sign=<原片MD5>` | 否（要先有哈希） | 已登记过身份的作品 | 是 |
| P5 失败出口 | — | HDR 源作品（`is_source_HDR=1`） | — |

一句话：**五个仓库加起来只有一条真能"只凭链接拿原片"的官方通道，就是 `ratio=default`；它在平台给该作品登记了"默认档"时直接 302 到上传原片，没登记时一律 404。HDR 源作品属于"没登记"，所以本项目在 HDR 作品上仍只能说清楚原因、拿不到原片。**

## 1 五个仓库各自到底怎么取址

| 仓库 | 关键文件 | 取址语句 | 是否给原片 | 本项目是否采纳 |
| --- | --- | --- | --- | --- |
| `jiji262/douyin-downloader` | `core/downloader_base.py`（原画探测 1329–1432）、`core/api_client.py`（签名 475–512）、`utils/abogus.py`、`utils/xbogus.py` | `GET /aweme/v1/play/?video_id=<uri>&ratio=default&line=0&is_play_url=1&watermark=0&source=PackSourceEnum_PUBLISH` + `Range: bytes=0-0`，跟 302，要求 200/206 且 `Content-Type: video/*`，总长取 `Content-Range` 尾部 | **是**（唯一实现原片探测的） | 采纳，见 P3 |
| `Evil0ctal/Douyin_TikTok_Download_API` | `crawlers/douyin/web/{abogus,xbogus,web_crawler}.py` | README 明示用 `X-Bogus`/`A-Bogus` 打 Web API，风控要求自备已登录 Cookie；具体取址语句未取到（`raw.githubusercontent` 与 `cdn.jsdelivr` 对该目录恒返回 `link dead`，同站 README 可取） | 未读到，按其为"网页档位 + 去水印" | 只采纳签名思路 |
| `cv-cat/DouYin_Spider` | 全仓 grep `原画|原片|is_source_HDR|HDR` 只命中 protobuf 脏词 | 无原画/HDR 处理，偏 creator 与直播 API | 否 | 不采纳 |
| `yzfly/douyin-mcp-server` | `douyin_mcp_server/server.py`、`douyin-video/scripts/douyin_downloader.py` | `iesdouyin.com/share/video/<id>` → `loaderData["video_(id)/page"]["videoInfoRes"]` → `data["video"]["play_addr"]["url_list"][0].replace("playwm","play")` | 否，只去水印 | 不采纳（本项目实测该分享页已是 72,914 字节空壳，无 `play_addr`） |
| `yuxie2025/douyin` | Android 工程模板（`base_lib`/WebView） | 无任何抖音接口取址逻辑 | 否 | 不采纳 |

`jiji262` 那份实现里两句注释值得原样记住：

- "`/aweme/v1/play/` 的 `ratio=default` 会 302 到上传原片。web detail API 的 `bit_rate` 阶梯不含该档（实测最高档可比原画小 8 倍），原画只能走这里。"
- 原画探测结果必须**和所选档的 `data_size` 比大小，"原画更大才置顶"**，并给了反例 `7508597705644985612`：某转码档 47.4 MB > 原画 31.7 MB，盲选会降质。

这两句构成本项目 P3 的两条判定规则（见 4.3）。

## 2 五个仓库的交叉结论

共识（三家有实质逻辑的仓库一致）：

1. 都**不靠 MD5**取址；都是"作品 ID → Web 详情 → 官方播放端点"。
2. 都要用 `a_bogus`（或 `x_bogus`）对查询签名，纯裸请求会被挡。
3. 都不碰 `bit_rate` 阶梯当原片（阶梯是转码）。

差异：

1. 只有 `jiji262` 实现原片探测，且带降质防护；其余两家是"去水印 + 最高转码"。
2. `jiji262` 明确禁止用 `download_addr` 当原片回退（付费作品会是 CENC 密文）；本项目同样不用 `download_addr`。
3. `jiji262` 默认 `video_quality=highest` 时**不探原片**，只有显式 `original` 才探；本项目始终要原片，因此把 P3 放进固定链路。

## 3 本项目把每条候选路线在真机上判死

样本 A：`7708052871413075238`（`is_source_HDR=1`、`is_long_video=1`、330.867 s、VID `v03033g10000dbs82lnog65ls2l3ol5g`，原片 140,778,272 B / 1280×720）。
样本 B：`7707993970332290314`（`is_source_HDR=1`、VID `v28033gi0000dbs4nevog65jrl6u1s10`，原片 38,562,411 B / 720×1280）。
样本 C：`7706430541934972201`（普通作品、VID `v0d00fg10000dbpbpovog65kfjne0f3g`）。

| 路线 | 做法 | 实测结果 | 结论 |
| --- | --- | --- | --- |
| fplay original/source | `force_fids=Base64("original")` + `codec_type=5`，以及 `stream_type=source` | A/B 共 8/9 档，全是转码，无 original/source 行 | HDR 作品不下发原片档位 |
| 裸 `ratio=default` 无签名 | 裸 requests，无 Cookie、无签名 | A：`default/1080p/720p` 全 404 | 必须签名 |
| `ratio=default` + `a_bogus` + 访客 Cookie | 见 4.3 | A 404；**C 206、`Content-Range: bytes 0-0/87979914`，与记录 size 完全一致** | 通道成立，但取决于作品是否登记默认档 |
| `ratio=default` + `sign=<真 MD5>` + `file_id` | 样本 A 用 `351f10c0e8f038973f2a63c9c749cb41` | **206，`bytes 0-0/140778272`**，落点 `v95-aw-chd.douyinvod.com/.../tos-cn-v-0051/ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8/`，与用户给的直链同桶同 key | 哈希门禁真实存在 |
| `sign=随机 32 hex`、`sign=真MD5 但无 file_id`、只给 `file_id`、全裸 | 4 组 | 全 404 | sign 不可伪造、不可省略 |
| 参数矩阵：`source`×`extra`×`ratio` | 5×7×3 = **105 次** | 全 404 | 与 source/format_type/stream_type/aid/codec_type 无关 |
| App 侧 host | `aweme.snssdk.com`、`api-play.amemv.com`、`api.amemv.com` × `default/1080p` + `aid=1128` | 全 404（连 1080p 都 404） | 该 VID 在 play 服务上不是按 ratio 键注册的 |
| 详情其它 uri | `play_addr` / `play_addr_h264` / `play_addr_265` / `download_addr` 四个 uri 分别当 `video_id` | 四个 uri 完全相同，全 404 | 无第二条注册键 |
| 详情找 `play_addr_hdr` / original vid | 遍历 `video` 全部键 | 无 `play_addr_hdr`、无 original vid 字段 | 平台不下发该身份 |
| VOD `GetPlayInfo`（`video.token_auth.play_auth_token`） | `/video/openapi/v1/` + AWS4 query、POST JSON、raw token 当 `Authorization`、`api-play.amemv.com` 同路径 | `100013 AccessDenied` / `100010 SignatureDoesNotMatch` / `10408 Missing Authorization header` | 这些请求未建立有效消费基线；“缺 native Authorization”的推断已撤回，见[真实消费链审计](original-investigation-2026-11-16-auth-consumer-audit.md) |
| 登录态 | — | 本机无可用 Cookie 文件，未验证 | 待用户提供登录 Cookie 后复测 P3 |

追加一轮（第三个 HDR 作品 `7707964786692083007`，VID `v28033gi0000dbs329vog65m4ip4vss0`，145.381 s，详情 `bit_rate` 只有 16,418,362 / 24,305,152 两档而 fplay 给 5 档，`output/play-deep-7707964786692083007.txt`）：

| 追加维度 | 结果 |
| --- | --- |
| `aid` ∈ 6383 / 1128 / 2329 / 2906 + `ratio=default` | 全 404 |
| `ratio` ∈ hdr / hdr_720p / 2160p / 4k / source_hdr / bytevc1 / dash | 全 404 |
| `ss_is_p_v_ss=1`（jiji262 的 `is_need_set_cookie` 分支） | 404 |
| `stream_type` ∈ source / hdr / origin | 全 404 |
| `codec_type` ∈ 0..5 | 全 404 |

即：`v28033gi*` / `v03033g1*` 这两族的 HDR 作品，play 端对它们的 `video_id` 没有任何 ratio 注册；`ratio` 语义、`aid`、`codec_type`、`stream_type`、`ss_is_p_v_ss` 都不是开关。三个 HDR 作品（`770799`、`770805`、`770796`）结论一致。

批量裁决（`output/play-default-batch.txt`，对 `original_metadata.json` 全部 10 条跑 `ratio=default`）：

| 命中 3 条 | 大小对得上记录 |
| --- | --- |
| `7706430541934972201` | 87,979,914 = 记录 YES |
| `7706477018388536499` | 27,668,186 = 记录 YES |
| `7707264789998849307` | 6,932,400,516 = 记录 YES |

其余 7 条 404，其中 HDR 两条、`v28033gi*` 前缀 5 条。命中者的 VID 前缀是 `v0d00fg1*` / `v0200fg1*`，未命中的多是 `v28033gi*` / `v03033g1*`。

## 4 汇总算法（已落地版本）

### 4.1 决策树

```
链接/ID
 └─ L0 作品 ID（resolve_id：链接、modal_id、分享文案、短链）
     └─ L1 详情（aid=392139，x-secsdk-web-signature）→ 拿 video.uri(video_id)、duration、bit_rate 档位尺寸、is_source_HDR
         ├─ P1 fplay force_fids=Base64("original") + codec_type=5   → 只收 quality=original/source
         ├─ P2 fplay stream_type=source（同一签发路径，仅切参数）      → 只收 quality=original/source
         ├─ P4 本地已验证 file_hash → play?sign=<md5>&file_id        → 大小/MP4 头必须对得上
         ├─ P3 play?ratio=default（a_bogus 签名，只凭 video_id）      → 见 4.3 四条判定
         └─ P5 source_unavailable + 证据（hdr_note / play_default_note / 外部来源提示）
```

优先级说明：P1/P2 是平台自己声明的原片档（身份由平台给出，最可信）；P4 是本地已验证的精确哈希（大小必须精确相等）；**P3 兜底**，因为它给出的是"默认档"，需要自己排掉"其实是转码"的情况。P4 在 P3 之前，是因为 P4 有精确字节数可比，误判概率更低。

### 4.2 P1/P2：fplay 原片档（原有实现，不变）

保留平台签发查询、删 `logo_type`、覆盖 `force_fids`/`codec_type`；失败再切 `stream_type=source`；两次都只出转码就进 P4/P3。判定：`quality ∈ {original, source}`、`vtype=mp4`、无 `encrypt/spade_a/encryption_method`、元数据完整、地址能解出且域名可信。

### 4.3 P3：官方默认档（本轮新增）

请求：

```
GET https://www.douyin.com/aweme/v1/play/
    ?video_id=<video.uri>&ratio=default&line=0&is_play_url=1&watermark=0
    &source=PackSourceEnum_PUBLISH
    &a_bogus=<ABogus(user_agent=self.user_agent).generate_abogus(query, "")>
Range: bytes=0-15
Referer: https://www.douyin.com/video/<aweme_id>
```

四条判定（缺一不可）：

1. **响应必须是 206 + `bytes 0-15/(\d+)` + 前 16 字节 `[4:8] == b"ftyp"`**；404 记"该作品未登记默认档"，200 但非 MP4 记"默认档不是可校验的完整 MP4"。
2. **字节数不能等于任何已知转码档尺寸**（`bit_rate[].play_addr.data_size`、`play_addr/265/h264/download_addr.data_size`）。等于某一个 → 平台把转码登记成默认档，拒绝。
3. **详情必须给出作品时长**，后续 mp4 时长与它差 ≤ 1 s（工作由既有 `probe` 完成）。
4. **分辨率不采信详情声明值**：原片几何可能与转码档不同（实测 1920×1440、1080×1920、3840×2160 三种都有），候选里 `width/height` 置 0，由 `probe` 读 moov 的 `tkhd` 回填；身份仍靠"时长一致 + 字节数不等于任何转码档"。

拒绝后不留垃圾状态：失败原因写进 `parser.play_default_note`，最终错误消息里原样带出，便于判定"是参数问题还是平台没登记"。

### 4.4 P4：本地已验证哈希（历史补救，默认屏蔽外部来源）

`/aweme/v1/play/?video_id&file_id&sign=<md5>&ratio=默认` → 206 + `bytes 0-15/(\d+)` + `ftyp` + `size == 记录 size`。这条**不是**解法的正解：它要求事先知道原片哈希，用户已明确否定（"我都拿不到原画我怎么有原画的md5呢"）。保留只为已登记作品的稳定复取。

### 4.5 P5：失败出口

`source_unavailable`，消息里必须带：上游实际档位数量与原因、`is_source_HDR=1` 标记、P3 的 `play_default_note`、外部来源记录被拦的提示。绝不降级到转码、绝不按 CDN 桶名或"更大就是原片"猜。

## 5 本轮代码改动

| 文件 | 改动 |
| --- | --- |
| `original_parser/abogus.py` | 新增：原样收录 `johnserf-seed/f2` 的 `utils/abogus.py`（Apache-2.0，经 `jiji262` 传入），唯一外部依赖 `gmssl` 的 SM3 |
| `original_parser/client.py` | 新增常量 `PLAY_URL`、`PLAY_DEFAULT_PROVENANCE`；新增 `OriginalParser._a_bogus_signer`、`_a_bogus_query`、`_transcode_sizes`、`_play_default_candidate`；`source_streams` 在 P4 之后接入 P3，并把 `play_default_note` 写进失败消息；`probe` 允许候选未声明分辨率（读到 moov 后回填）；`parse` 的"原画解析成功"消息纳入 `official_play_default` |
| `requirements.txt` | 新增 `gmssl>=3.2` |
| `tests/test_parser.py` | 新增 `PlayDefaultTests` 5 例：只用 video_id + a_bogus 命中、转码尺寸拒绝、404 诊断、缺档位尺寸时跳过、probe 回填几何 |
| `tools/verify_play_default.py` | 真机验证脚本：详情 → P3 → moov 校验，输出`output/verify-play-default.txt` |
| `tools/probe_play_default_alt_vid.py` | 备用 uri 补测脚本 |
| `tools/probe_play_ratio.py`、`probe_play_abogus.py`、`probe_play_variants.py`、`probe_play_sign_variants.py`、`probe_play_matrix.py`、`probe_play_hosts.py`、`probe_play_default_batch.py` | 判死实验脚本，输出在 `output/play-*.txt` |

离线测试：`pytest -q` → **106 passed, 108 subtests passed**。

## 6 本轮真机结果（`output/verify-play-default.txt`）

| 作品 | HDR | 转码档尺寸 | P3 结果 | 媒体校验 |
| --- | --- | --- | --- | --- |
| `7706430541934972201` | 0 | 2,600,066 / 2,960,665 / 6,621,637 / 9,432,705 | 命中 87,979,914 | 1920×1440、46.208 s、有音轨 |
| `7706477018388536499` | 0 | 1,951,702 / 2,224,211 / 5,706,289 / 7,439,558 | 命中 27,668,186 | 1080×1920、31.069 s、有音轨 |
| `7707264789998849307` | 0 | 27,131,445 / 31,405,914 / 63,098,895 / 106,479,445 | 命中 6,932,400,516 | **3840×2160**、480.073 s、有音轨 |
| `7708052871413075238` | 1 | 24,414,636 / 28,405,118 / 45,992,041 / 68,568,404 | 404 | — |
| `7707993970332290314` | 1 | 18,473,036 / 21,409,165 / 40,274,983 / 52,471,983 | 404 | — |

结论：P3 让"普通作品"从"必须查原画档位"变成"只凭 video_id 直接拿原片"，且拿到的原片分辨率高于任何转码档（4K 那条 6.93 GB，转码档最大只有 101 MB）。**HDR 源作品仍是一条死路**，原因不是参数没试到，而是 play 服务对该 VID 没登记任何 ratio（连 1080p 都 404）。

## 7 仍未解决，以及下一步能做什么

1. **HDR 源作品（`is_source_HDR=1`）**：原片对象确实存在（`tos-cn-v-0051` / 同桶同 key / 140,778,272 B），但官方只按 `sign=<原片真实 MD5>` 寻址。项目内没有任何能"从作品 ID 推出这个哈希"的官方来源。已判死的入口见第 3 节全表。
2. **VOD `GetPlayInfo`（`video.token_auth.play_auth_token` 是完整 AWS4 签发 query）**：后续按实际消费者复核，已检查的 version 2/4 播放分支传入空 auth；此前搜索到的 AWS4 常量属于上传 SDK 和 QoS。“只差 native Authorization”及“应逆 `libc++_shared` 找密钥”的推断已撤回。2026-11-17 的 Ghidra 分析进一步确认，MDL `_getAuth` 为本地代理地址计算 CRC32，并非服务器播放授权。当前仍需找到目标自身有效的原片身份和取址上下文，详见[真实消费链审计](original-investigation-2026-11-16-auth-consumer-audit.md)。
3. **登录态未验证**：本机没有可用 Cookie 文件，P3 只在访客身份下测过。若拿到已登录 Cookie，值得在 HDR 作品上复测一次 P3——`jiji262` 的 README 明说需要登录 Cookie，这一点本项目目前无法排除。同日 `docs/original-investigation-2026-11-16-login-result.md` 记录的登录对照是另外两个作品（`7707196543073275177`、`7704677676878925119`），三阶段目录完全相同，**没有覆盖 HDR 作品**，所以该分支仍未排掉。
4. **不做的事**：不用第三方/他人的整文件 MD5 作常规取址依据；不凭第三方"原画"标签放行；不按 CDN 桶名推断原画；不改 `br`/分辨率；不把普通档改名 original；不硬编码样例地址。

## 8 追加验收：登录态与 App 侧（2026-11-16 晚）

用户扫码登录后（`tools/capture_login_cookies.py` 抓取 13 个字段，含 `sessionid`/`sid_tt`/`ttwid`，落在 gitignore 的 `credentials.json`），两条此前未排掉的分支全部实测：

| 分支 | 做法 | 结果 |
| --- | --- | --- |
| A 登录态默认档 | 用登录 Cookie 打 `ratio=default`，对 `770805`/`770799`/`770796` | 三个仍 **404**（`output/verify-play-default.txt` 首行标注登录态） |
| B1 App 侧详情是否下发 `token_auth` | `api.amemv.com`/`aweme.snssdk.com`/`api5-normal-c-lf.amemv.com` 的 `aid=1128` 详情，带登录 Cookie、不带 `X-Gorgon` | 三家均 **HTTP 200 + 完整 56 KB 回包**（说明 App 链不是签名墙），但 `video.token_auth`、`video.meta.token_auth` 都不存在，`need_set_token=false` |
| B2 `play_addr_hdr` 是否存在于客户端 | 对 270 MB APK 全量 dex/so 做字节扫描（`tools/scan_apk_strings.py`） | `play_addr_hdr` **0 命中**；`is_source_HDR` 仅 2 处，`PlayTokenAuth`/`GetPlayInfo`/`video/openapi/v1` 集中在 `classes30.dex`；`x-gorgon` 只在 `libsscronet.so` |
| B3 下载策略是否差异点 | 对 `770805`/`770799`/`770796`/`770726` 取 App 侧 `video_control` | 四条全是 `allow_download=false` + `prevent_download_type`，原因分别是 `290002 isolation_content`、`200142 aigc_forbidden`；**能取到 4K 原片的 `770726` 也一样**，所以不是分水岭 |
| B4 短剧剧集侧入口 | 取 App 侧 `series_basic_info`/`series_paid_info`/`chapter_list` | `series_basic_info={}`、`chapter_list=null`、`media_type=4`，该作品在接口语义上不是可枚举剧集，没有剧集侧入口 |
| B5 `xigua_base_info` | 同上 | `{"status":0,"item_id":0,...}` 空壳，没有西瓜侧 vid |

**结论：**A 排除（登录态不给默认档）；B 的前提被推翻——客户端自己也没有 `play_addr_hdr` 或 `token_auth`，HDR 短剧这类作品在抖音 web/app 播放链里只下发转码档，原片对象只能按 MD5 寻址。第三方能取到，靠的是别的产品线（红果/番茄等短剧产品）或自建客户端，不是"抖音接口里还差一个参数"。

### 8.1 后续三条补充实验（同日晚）

| 实验 | 做法 | 结果 |
| --- | --- | --- |
| VOD 错误码取全 | `tools/probe_vod_error.py`：web `play_auth_token` 打 3 host × 2 path，打印完整 `ResponseMetadata.Error` | `/` 为 `100013 AccessDenied`（`User is not authorized to perform: vod:GetPlayInfo on resource: []`），`/video/openapi/v1/` 为 `100010 SignatureDoesNotMatch`。token 的 `X-Amz-SignedQueries` 只有 `aid;codec_type;format_type;stream_type;video_id`，是**播放域令牌**，权限模型上调不了 `GetPlayInfo`，不是缺参数 |
| 换客户端身份是否能拿到 VOD 令牌 | `tools\probe_client_aids.py`：aid 1128（抖音）/2329（极速版）/1112（火山）/6383（web）取同一作品详情 | 四家全部 200 有详情，`video.token_auth` **全部为空**，`need_set_token=false`；服务端对该作品不签发 VOD 令牌，与客户端身份无关 |
| 详情自带哈希是否等于原片 MD5 | `tools\check_file_hash.py`：比对 `play_addr`/`play_addr_265`/`download_addr`/`bit_rate` 行的 `file_hash`/`file_cs` 与已知原片 MD5 `351f10c0…` | 全部不等，`file_hash` 是**各转码档自己的 MD5**（`b6baa1ad…`=720p、`de0bb56d…`=540p）；`file_cs` 是 `c:0-<字节数>-<crc>` 形态的分段校验。官方详情里的哈希不能用于原片寻址 |
| 抖音→西瓜映射 | `tools\dump_app_raw.py`：原始 App 详情全文检索 `ixigua`/`365yg`/`xigua`/`sync_to_toutiao` | `xigua_base_info` 空壳、`xigua_task.is_xigua_task=false`、`sync_to_toutiao=0`、无任何 ixigua/365yg 链接。用户给的原片链接挂在 365yg/ixigua 域，不是"抖音→西瓜"映射出来的，而是 VOD `GetPlayInfo` 输出的 TOS 形态 URL |

### 8.2 官方档位清单与 play 门禁机制（同日晚，决定性）

`tools\dump_fplay_gears.py`、`tools\probe_fplay_codecs.py`（8 个 `force_fids` × 9 个 `codec_type`，共 72 组）、`tools\probe_play_sign_mech.py`、`tools\probe_hdr_slot.py`：

1. **档位清单**：`7708052871413075238` 的 fplay 只注册 **8 个转码档**（去重 8 个 `file_id`），最大 68,568,404 字节 / 1280×720；原片实测 140,778,272 字节。72 组组合里的并集仍是同样这 8 个 `file_id`，**原片的 `file_id` 与 `file_hash` 不在任何官方响应里**。
2. **play 门禁机制**（决定性）：`/aweme/v1/play/` 里 **`file_id` 决定取哪个文件对象，`sign` 只是门禁位**。实测——
   - `file_id=73a71219…` + `sign=ff52aa38…`（该档自己的 MD5）+ `ratio=normal` → `206`，`Content-Range` 总长 68,568,404（该档）；
   - 同一 `file_id` + `sign=351f10c0…`（**原片** MD5）+ `ratio=default` → 仍然 `206`，返回的还是 68,568,404 那一档；
   - 无 `sign` → `404` JSON。
   即：只要知道目标文件的 `file_id`，`sign` 用任意合法 32 位十六进制都能过关；**原片取不到的原因是不知道它的 `file_id`，不是哈希门禁**。
3. **`force_fids=hdr`**：返回 1 个 `definition=360p`、`size=0`、`file_id=""` 的兜底行，其 `main_url` 解码后是 `v26.douyinvod.com/…/video/s/220v03033g1…/`，实测 `Content-Range` 总长 45,992,041（就是 540p 档），不是原片。该 fid 只是"给我一个能播的"兜底，并无 HDR 槽。

**这条把问题锁死了**：抖音官方接口对这类作品既不下发原片 `file_id`，也不注册原片档位；`ratio=default` 只在平台把原片登记为默认档时才有响应（`770726` 的 6.9 GB 4K 原片即属此列，已验证能自取）。

## 9 复现（补）

```powershell
# 离线测试
.\.venv\Scripts\python.exe -m pytest -q

# P3 真机验证（详情 → 默认档 → moov 校验）
$env:PYTHONPATH='D:\ProjectPy\douyin-original-parser'
.\.venv\Scripts\python.exe tools\verify_play_default.py 7707264789998849307 7708052871413075238

# 批量裁决 ratio=default（读 original_metadata.json 全量）
.\.venv\Scripts\python.exe tools\probe_play_default_batch.py
```

注：本机 PowerShell 工具的输出捕获在本会话不可用，命令一律 `*> output\xxx.txt` 后再读文件。

登录态抓取（会弹一个可见的 Chromium，扫码后把 Cookie 写进 `credentials.json`）：

```powershell
.\.venv\Scripts\python.exe tools\capture_login_cookies.py credentials.json 900
.\.venv\Scripts\python.exe tools\verify_play_default.py --cookie-file credentials.json 7708052871413075238
```

`credentials.json` 已在 `.gitignore` 中，不要提交，也不要贴到任何外部系统。
