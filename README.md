# 抖音原画独立解析程序

输入抖音链接，优先返回经过媒体校验的官方 `source/original` 档位。兼容播放档单独标明来源，无可用候选时返回 `source_unavailable`（获取原画失败）。支持 MP4 校验、下载、与本地样本做 SHA-256 对照，以及本地 HTTP API。

**2026-11-18 原片复现与地址刷新修复：**作品 `7702453019425672467` 在禁用历史记录读取后，现有官方 `original` 路线仍可取得 96,704,180 字节原片；完整下载与用户自建参考文件逐字节一致。另修复部分分发路径将 `dy_q` 误作到期时间、提前消耗下载刷新机会的问题，115 项相关测试通过。新样本成功不代表此前困难作品均已恢复，详情见[本轮验证与修复](docs/new-sample-signature-repair-2026-11-18.md)。

**2026-11-17 研究状态：**已补齐多接口模型审计、复现 Java 小帅协议，并核对实际文件及 HDR 色彩信息；部分目标的原画首次发现仍未解决。最新范围与限制见[接口覆盖复核](docs/original-investigation-2026-11-17-coverage-audit.md)和[小帅接口实测](docs/original-investigation-2026-11-17-snapany-java.md)。历史实验工具及资料的使用边界见 [tools/README.md](tools/README.md)。

**2026-11-16 新一轮算法与媒体修复：**现已利用详情内嵌 `video_meta` 原画、逐路媒体校验与当前官方身份重新分发，补齐 `zjcdn.com`，并修复 QuickTime 的轨道处理器覆盖问题。作品 `7698054262056552561` 已完整下载 **40,087,514 字节 / 1080×1920 / HEVC+AAC**，MD5 与本轮官方原画回包匹配。两条重点 HDR 作品共检查204条主备地址、17个不同媒体对象，仍未恢复原片；同轮检查的 `7706218040236444937` 也仍失败。代码变化、完整下载证据、公开来源和可复现全档审计见[本轮修复与验收](docs/original-investigation-2026-11-16-astar.md)。随后新增的 `7708319942491344154` 也未取得原片，Web、精选 H5、App 专用详情与容器 VID 检查见[第三轮当前链接验收](docs/original-investigation-2026-11-16-astar-round3.md)。

单文件 MP4 下载时，解析器核对官方元数据或 CDN `Content-MD5` 提供的整文件摘要。没有摘要时，解析器核对大小、音视频轨道、时长和分辨率，并计算本地 MD5 和 SHA-256。DASH 分轨使用下文的校验方式。

**当前选档策略：**优先使用官方 `quality=original/source` 档位，以及由官方原片分发接口重新签发并通过媒体校验的原片。保留已有的 `ratio=default` 兼容通道（`source_evidence=official_play_default`），并排除详情与 fplay 的全部已知转码大小；这一兼容通道不等同于取得官方 `original/source` 档位声明，仅凭大小不同不能保证所有未知文件均是上传原件。普通 `normal/adapt` 档不会因使用 DASH 或某个 CDN 桶而被选中。原画候选不按 CDN 桶名或备用目录 `aid` 过滤：桶名只用于诊断，备用目录的 `aid`、主机、路径和查询按平台下发原样保留。

**PC Web 独有档位（2026-11-20 实测）**　两条样本的桌面播放器详情都给出了手机详情中未出现的视频轨和独立音频轨。解析器用大小和哈希排除手机详情的已知档位，分别校验两条轨道。结果标为 `source_evidence=official_web_pc_bitrate`，没有平台原画声明时 `official_quality` 为空。两条样本均已验证可合并播放。作品 `7701401474567343403` 的合并文件为 14,213,396 字节，同作品已登记并经官方分发验证的外部参考文件为 91,804,327 字节，两者的视频流 SHA-256 也不同。尚无作者上传文件可供核对。

DASH 下载需要 PATH 中的 `ffmpeg`。CLI `--download` 复制两条轨道到一个 MP4，然后核对成品的轨道、时长和分辨率。`data.size_bytes` 是输入轨道的大小之和，`data.download.bytes` 是输出 MP4 的实际大小，封装开销会使两者不同。轨道的 `file_hash` 可能标识源对象，下载结果分别记录 `video_md5`、`audio_md5` 及与上游值的比较结果。合并文件有独立的 SHA-256 和 MD5，`download.official_hash_match` 为 `null`。

**源候选（`source_candidate`，默认关闭）：**官方原画全部失败时，可显式开启 `--allow-source-candidate`（或环境变量 `DOUYIN_ALLOW_SOURCE_CANDIDATE=1`；HTTP 请求字段 `allow_source_candidate: true`）返回最高普通档作为源候选。仅当该档是完整 MP4、时长/分辨率通过媒体校验，且容器 `udta/meta/ilst` 的 `comment` 中携带的 `vid:` 与详情播放 VID 不同才返回；结果标记 `source_evidence=platform_source_candidate`、`source_candidate=true`，不是平台 `original`，也不会写入 `original_metadata.json`。容器内嵌 VID 只是源文件谱系证据，不能由它直接取原画：直接用它请求 `/aweme/v1/play/`、fplay 或 app 主机均为 404 或 `error check params`。HTTP 回包对源候选额外返回 `source_candidate`、`source_evidence`、`official_quality`、`source_vid`；单文件原画成功回包只含 `url`，调用方必须依据 `source_candidate` 区分。

**2026-11-16 当前链接验收：**仅输入作品 `7707993970332290314` 的链接，并禁用全部历史原片记录与参考资产后，两个官方取址分支均只返回 9 个转码档，首次原片发现仍未修复。该作品依靠已有参考资产 MD5 的官方重签成功，不属于仅链接解析成功；`DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1` 也不具备从链接发现未知哈希的能力。实际对照与补查边界见[仅输入链接的验收记录](docs/original-investigation-2026-11-16-link-only.md)。

**同日官方续查：**从目标自己的转码 MP4 找到了另一个内嵌 VID，并完成 SDK 播放目录、精确 FID 选择与官方网页 token 签发对照，仍未发现该作品原片。新增只读研究工具 `tools/probe_official_vid_lineage.py` 可由链接复现 VID 检查，不使用 catalog；诊断完成不表示生产解析已修复。此前“只差 native Authorization 算法”的推断也已按真实调用链纠正。详见[官方发现续查与复现命令](docs/original-investigation-2026-11-16-official-link-discovery.md)。

**2026-11-10 原画恢复：**作品 `7706466342664277290` 已恢复官方原片解析。此前官方 fplay 回包只下发普通转码，但该作品的 `video_id`、`file_id`、MD5、大小和 MP4 媒体信息已经通过官方回包与 Range 校验确认；程序在两个 fplay 入口均没有原画时，使用这些可信元数据调用官方 `/aweme/v1/play/` 分发接口重新签发临时原片地址，并再次核对 `206`、完整大小和 MP4 头。当前返回 185,591,975 字节、1080×1920、H264/AAC，`source_selected=true`、`source_evidence=official_play_hash`。没有匹配记录或分发失败时，保持 `source_unavailable`，不返回普通转码档。

**2026-11-07 原画恢复进展（尚未通用修复）：**参考公开的 `file_id/sign` 线索，作品 `7695411862271315236` 已由官方播放分发入口重新取得 **207,466,034 字节**历史原片。完整下载的 MD5 与历史记录一致，720×1280 HEVC 视频及 AAC 音频均完整。该请求依赖历史已知的原片 MD5；当前详情未下发它，新作品 `7704869082255904042` 的原片仍未恢复，因此尚未接入生产自动解析。全部实测均直接访问官方接口，没有调用第三方解析服务。机制、对照与限制见[11 月 7 日调查记录](docs/original-investigation-2026-11-07.md)。11 月 6 日的失败状态保留在[历史研究报告](docs/original-investigation-2026-11-06.md)与[专项复查记录](#自建原画专项复查2026-11-06尚未恢复缺失原画)。

**解析失败时先看：[解析故障与修复记录](#解析故障与修复记录)。** 该章节集中记录历史报错、已确认原因、修复方式、验证证据和 Linux 复查命令；后续排障先按错误码查阅，并在修复后追加记录。

**2026-11-06 对照复测：**部分历史原画目前不再由现有官方请求下发；并非所有作品失效。作品 `7695305664234589459` 仍取得 528,422,694 字节的官方 `original`，另外两个历史样本只返回普通档。对新作品 `7703504174440254762` 和历史作品 `7695411862271315236` 实际调用 NiKa 的 muzzz、Snapany 后，两家标为“原画”的文件均对应自建接口已经取得的官方 `normal` 档。新作品三个来源完整下载的 SHA-256 一致。具体证据及限制见[两家第三方对照与历史原画复测](#两家第三方对照与历史原画复测2026-11-06)。

**2026-09-20 已实测成功：**作品 `7685326449011608873` 下载得到 **61,314,387 字节**，与用户提供的 `af61965f8683a01d24fc96d2ea98e935.mp4` 的 SHA-256 完全一致。程序没有硬编码该作品的 CDN 地址或目标哈希；对照文件只在下载完成后参与验证。

**2026-10-15 可用性复核（历史故障，已于次日修复）：**原画下发情况因作品而异。作品 `7695305664234589459` 当时仍能由现有代码取得 528,422,694 字节的 `original` 档位，并通过远程音视频校验。另有多个样本只收到 `normal` 转码档：作品 `7696148481915833663` 的用户提供的第三方地址仍可读取，文件为 98,181,767 字节；本程序 HTTP 和浏览器详情模式均只取到 37,064,709 / 54,931,085 字节的普通档。当时尚未恢复原画取址，后续原因与修复见 2026-10-16 记录。

**2026-10-16 原画取址修复：**旧实现把官方备用接口的完整查询替换为 `aid=392139&stream_type=source`，多个作品因此只返回普通转码档。现改为保留平台下发的签名路径及完整查询，删除 `logo_type`，覆盖 `force_fids=Base64("original")` 和 `codec_type=5`，并保留原有 `stream_type`。已实际取得作品 `7695411862271315236` 的 `original` 文件：207,466,034 字节、720×1280、HEVC、约 489.686 秒，媒体对象与用户提供的同作品参考一致，远程音视频校验通过。新选档未取得可用原画时仅兼容一次旧 source 入口；作品身份不一致、网络和限制类错误不追加请求。此修复仍直接请求平台官方接口，无需额外登录或第三方解析服务。Linux 进程需要更新源码并重启后生效。

运行时需要 Python 3.10+、requests、cryptography、Playwright 及其 Chromium。2026-09-21 已确认抖音详情接口开始拒绝缺少 UIFID 的匿名 HTTP 请求，返回 `403 Uifid Not Found`；因此不能继续使用“无需浏览器、直接匿名请求”的旧启动方式。

程序默认用 Playwright 创建全新的匿名 Chromium 上下文，访问抖音首页取得 `ttwid`、`UIFID_TEMP` 后关闭浏览器，再使用对应的 User-Agent 和网页签名请求详情。HTTP 模式的访客凭据在进程内复用 20 分钟；直接 CLI 遇到访客相关失败最多刷新一次，受保护的 HTTP 服务不在单个任务内刷新重试。可用 `--detail-mode browser --browser-profile windows` 沿用 04 已验证的页面请求方式。整个过程不读取个人浏览器资料或登录 Cookie。

## 快速使用

将项目文件放入 Linux 服务器的 `/opt/software/python`，确保 `run.py` 直接位于该目录内，然后执行：

```bash
cd /opt/software/python
sudo bash deploy/linux/install.sh
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873"
```

安装脚本创建或复用项目的 `.venv`，安装 Python 依赖，并将 Chromium 下载到项目 `.browsers`。仅安装 `requirements.txt` 不会自动下载浏览器。首次初始化访客通常比后续请求慢；Ubuntu 的虚拟环境组件、完整安装步骤和 systemd 自启配置见 [Linux 部署说明](deploy/README.md)。

默认检查实际大小、时长、分辨率以及音视频轨道。需要下载时：

```bash
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873" --download output/my_source.mp4 --json output/my_result.json
```

文件已存在时拒绝覆盖。要重新下载，请换一个输出文件名。将对照附件放到服务器的 `/tmp` 后可执行：

```bash
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873" --download output/reference_check.mp4 --reference "/tmp/af61965f8683a01d24fc96d2ea98e935.mp4" --json output/reference_check.json
```

对照一致时退出码为 `0`；解析或下载失败为 `2`；下载成功但与指定对照文件不一致为 `3`。

也可以编辑 **parse_links.py** 顶部的 `LINKS`，再执行 `.venv/bin/python parse_links.py`。结果保存在本项目的 `output` 目录。把 `DOWNLOAD` 改为 `True` 即同时下载。任意链接解析失败时脚本退出码为 `2`，不会再显示“退出代码为 0”。

也可以直接传一个或多个作品 ID 或链接，例如 `python parse_links.py 7707954213745085746`。已有路径没有取得可用原画时，如果网页还给出了未请求过的备用目录，解析器会按原地址读取一次，记为 `issued`，仍核验视频身份、原画标签和媒体。若有效 Web 目录均只有普通档，脚本会记下作品号、时间和档位摘要。稍后运行 `python parse_links.py --retry-pending`，会逐条复查待查作品一次；成功后从列表移出。复查由你手动启动，不在后台轮询，也不保证平台届时提供原画。历史保存在 `output/web_attempts.sqlite3`，与最后一次成功结果 JSON 分开。临时媒体地址和凭据不写入此历史。

`parse_links.py` 同样支持 `--allow-external`（放行本地已核对过的外部来源原片身份，仍走官方分发重签与媒体校验）；PyCharm 里不想带参数时，把该文件顶部的 `ALLOW_EXTERNAL` 设成 `True` 即可，`None` 表示跟随环境变量 `DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY`。待查复核强制关闭外部来源恢复；`--retry-pending` 不能与链接或 `--allow-external` 混用。

### 用一个作品链接取回已归档的授权母版

如果要求每个自有或授权作品都能凭链接取回上传原文件，发布时应保存原 MP4，并在拿到作品 ID 后将它与该文件关联。以下命令仅访问本地归档，不需要 Cookie、平台签名、媒体直链或用户提供的 MD5。

```bash
# 发布者在取得作品页链接后登记一次。
python -m original_parser.masters --archive /srv/authorized-masters add "https://www.douyin.com/video/<作品ID>" upload.mp4

# 之后只需提供作品页链接；输出目录可以由调用方预设。
python -m original_parser.masters --archive /srv/authorized-masters fetch "https://www.douyin.com/video/<作品ID>" --output output/master.mp4
```

登记时检查 MP4 时长和音视频轨道并计算整文件 SHA-256。取回时再次验证字节数和 SHA-256，再写出原始字节。该入口不覆盖已有文件，不把归档文件当成平台原画目录发现。未归档的作品返回 `source_unavailable`。目前接受能直接识别作品 ID 的链接；不含作品 ID 的分享短链须先在浏览器打开。归档目录应由内容方管理，关联由提供母版的运营方确认。

对未归档的第三方作品，单链接首次取回取决于平台是否通过允许下载的入口提供原画文件。开放平台的[视频数据查询](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/video-data/)公开响应没有上传原文件地址；`original/source` 是平台的档位声明，与发布者上传文件逐字节一致还需要原文件或可信摘要核对。两条样本的浏览器检查见[单链接验收记录](docs/one-link-original-2026-11-20.md)。

### 登记一条已有的原片直链（`--register-original`）

如果手上已经有一条原片直链（例如第三方解析给出的地址），可以让项目自己把它的身份核验进本地记录，而不是手工改 JSON：

```bash
.venv/bin/python run.py "https://www.douyin.com/video/<作品ID>" --register-original "<原片直链>"
```

核验四件事，任一不过就拒绝，不会写入：

1. 该地址必须是可 Range 读取的完整 MP4（首 16 字节为 `ftyp`），且同时含视频与音频轨道；
2. moov 实读时长必须与作品详情一致（容差 1 秒）；
3. 总字节数**不得等于**详情里任何已知转码档的大小（防止把转码档当原片登记）；
4. 用该文件整文件 MD5 打官方 `/aweme/v1/play/` 重签，必须返回同字节数的可读 MP4。

缺 `Content-MD5` 响应的边缘会流式读完整文件算 MD5（一次性的，不落盘）。登记记录标记为 `official_play_hash_from_verified_asset`，与外部来源同一策略：**默认不参与取址，需要 `--allow-external` 才生效**。它证明的是“该对象确实存在且官方认可”，不是“只凭作品 ID 能自己发现”。

其他选项：`--url-only` 只打印地址；`--no-probe` 跳过远程媒体校验。默认自动初始化访客，无需手动配置 Cookie。

官方未提供可用原画时直接返回 `source_unavailable`，消息包含“获取原画失败”；普通档达到 1080p、位于 `tos-cn-v-*` 桶或被第三方标记为“原画”，都不能改变这个结果。自动更新 Cookie、重试或跳过媒体校验并不保证恢复原画。错误会汇总格式、媒体加密标记、地址缺失、解码或地址校验等原因，不包含 Cookie、密钥或完整播放地址。

已有有效访客凭据时，可用 `--cookie-file credentials.json` 指定文件，或在 `parse_links.py` 设置 `COOKIE_FILE`。支持 `name=value; ...` 文本、名称到值的 JSON 对象、浏览器导出的 Cookie JSON 数组，以及包含 `cookies` 和 `user_agent` 的 dtk-parse `credentials.json`；后者会保留凭据配套的 User-Agent。显式指定文件时不自动获取或覆盖其 Cookie；HTTP 服务每次解析重新读取该文件，外部更新后下一次请求即可生效。

旧素材原片仍缺失时，可用独立的[登录前后对照工具](docs/original-session-comparison.md)验证会话差异：Windows 可双击项目根目录的 `compare_original_sessions.cmd`，先自动测匿名，再由用户在新浏览器手动登录，最后复测登录会话及匿名会话。Cookie 不导出，报告不保存临时地址，历史原片 catalog 禁用。2026-11-16 用户已完成一次登录测试：`7707196543073275177` 三阶段返回相同 8 个普通档，`7704677676878925119` 登录后仍被详情过滤，目标原片均未恢复；阳性首次匿名详情 HTTP 403 使完整对照总标签保守记为 `inconclusive`，后两阶段阳性均通过原片媒体校验。证据及限制见[登录结果记录](docs/original-investigation-2026-11-16-login-result.md)。该工具不改变生产解析行为。

## Linux 生产部署：三个 Java 实例共用服务

当前主解析节点为已验证可用的 `172.31.0.4`，目录仍为 `/opt/software/python`，三个 Java 实例主调用地址为 `http://172.31.0.4:8765`。HTTP服务共用队列，默认由3个实际工作线程并行解析，保留每线程任务间隔、同作品请求合并、有效期缓存和连续失败暂停。已有服务升级及适用范围见 [请求保护说明](deploy/REQUEST_PROTECTION.md)，首次部署见 [Linux 部署说明](deploy/README.md)。备用解析节点若被启用，各进程的保护状态独立。

## HTTP 接口

Linux 无 Docker、三个 NiKa 实例共用服务的部署步骤见 [部署说明](deploy/README.md)。执行 `.venv/bin/python package.py` 可在项目父目录生成源码部署包，包含虚拟环境安装脚本和 systemd 配置。

```bash
cd /opt/software/python
.venv/bin/python run.py --serve --port 8765
```

默认监听 `127.0.0.1`，提供 `GET /health`、`POST /parse` 和 `POST /api/v1/resolve`。

默认最多同时受理6个HTTP请求，包含等待者；由3个工作线程实际并行解析，可用`--parse-workers`或`PARSE_WORKERS`调整（1～32）。每个线程完成完整任务后默认随机等待0.5～1秒，可由`REQUEST_INTERVAL`调整。浏览器模式也允许相同数量的独立浏览器任务。同作品完整链接/ID自动合并，只有经过媒体校验的官方原画结果最多缓存5分钟，并提前60秒避开地址到期；`source_unavailable`不缓存。累计3次限制类错误后全进程冷却15分钟，冷却结束只允许一个试探任务，旧批次迟到成功不会提前结束冷却。冷却返回HTTP 503和`Retry-After`，满队列或等待超时返回HTTP 429。健康检查的`protection.workers`和`protection.active`分别表示实际线程数和正在解析的任务数。参数及短链、进程内状态等边界见 [请求保护说明](deploy/REQUEST_PROTECTION.md)。

下载或转存发现旧直链失效时，调用方可在解析请求中传入 `"force_refresh": true`。服务会清除当前作品及凭据范围内的旧成功缓存，重新执行取址和媒体校验；相同作品的在途请求仍合并，排队、任务间隔和冷却规则继续生效。刷新失败不会回落到原来的缓存地址。该参数必须是 JSON 布尔值，默认 `false`。播放地址是有时效的临时链接，业务方应在消费失败后重新解析原作品链接，不能长期复用保存的 CDN 地址。

```bash
curl --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://127.0.0.1:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7685326449011608873","with_probe":true}'
```

单文件 MP4 的 HTTP 成功回包如下。

```json
{
  "code": 0,
  "msg": "原画解析成功",
  "data": {
    "url": "https://平台CDN/临时播放地址"
  }
}
```

单文件原画的 HTTP 成功回包只保留播放链接，不再返回 `video_list`、备用地址、官方文件 MD5 和媒体探测结果；这些内容仍保留在 CLI 输出和 `--json` 结果文件中。依赖 `source_selected`、`official_quality`、`probe` 等字段的调用方需要同步调整。NiKa 旧 Java 客户端会将这种成功响应误报为“请求异常 / ServiceException”，需同步发布兼容精简响应的 `nika-basic`，具体排查见[部署说明](deploy/README.md)。

例如作品 `7704212621922159898` 缺少原画时，返回 HTTP 502，响应如下：

```json
{
  "code": "source_unavailable",
  "msg": "获取原画失败：原画接口仅返回普通转码档",
  "data": null
}
```

CLI 完整结果中的 `source_evidence` 区分本次平台明确标注的 `original/source` 与按已知身份重新分发的文件。精简 HTTP 回包保留默认播放档的 `official_play_default` 和 PC Web 播放档的 `official_web_pc_bitrate`；收到这两个值时，调用方应将结果显示为播放档。

请求可传 `"allow_source_candidate": true`（必须是 JSON 布尔值）显式开启源候选。源候选成功时回包会额外带标记：

```json
{
  "code": 0,
  "msg": "返回源候选（非平台原画）",
  "data": {
    "url": "https://平台CDN/临时播放地址",
    "source_candidate": true,
    "source_evidence": "platform_source_candidate",
    "official_quality": "normal",
    "source_vid": "容器内嵌源 VID"
  }
}
```

单文件原画成功回包只含 `url`。调用方必须检查 `source_candidate`，不能把源候选当作原画；服务端默认关闭源候选，只有请求显式开启或进程设置 `DOUYIN_ALLOW_SOURCE_CANDIDATE=1` 才可能返回。

PC Web 独有档位返回 `dash_mux_required: true` 时，`url` 指向视频轨，`audio_url` 指向音频轨，`size_bytes` 为两轨合计大小。NiKa 等 HTTP 调用方须同时保存两条轨道并合并，单独保存 `url` 只会得到无声视频。CLI `--download` 可直接生成完整 MP4。

NiKa 的独立 `selfhosted` 渠道，页面名称为“自建原画（抖音）”，与 Snapany、muzzz 并列。Java 后端访问配置的 Python `/parse`，支持排队限流、在线检查和媒体校验。本次策略升级需更新 Python 服务并发布 NiKa 后端；旧 NiKa 后端会拒绝转码结果。已启用自建渠道的页面无需改动。部署配置和启用步骤见 [部署说明](deploy/README.md)。HTTP 示例服务不自带公网鉴权，跨机器部署时使用后端可达的内网地址。

## 核心算法与已有项目的区别

1. 提取作品 ID，支持视频链接、`modal_id`、分享文案和短链。
2. 初始化或复用匿名访客凭据，计算 `x-secsdk-web-signature`，请求官方 Web 详情，使用 `aid=392139` 取得非空 `video_model`。PC 视频页的 `aid=6383` 详情（`request_source=600`、`origin_type=video_page`）会额外下发手机详情没有的 `video.bit_rate` 隐藏档位，作为原画补充入口。
3. 先检查 `video_model.video_list` 中平铺或 `video_meta` 包装的原画候选，再按需访问 `video_model.fallback_api` 下发的目录地址。主机、路径、`aid`、签名和完整查询（包括原有 `stream_type`、`encode_user_tag` 等上下文）均按平台原样保留，不要求固定桶名或固定 `aid`；删除 `logo_type`，覆盖 `force_fids=Base64("original")` 与 `codec_type=5`；随后兼容仅切换 `stream_type=source` 的入口。每一路候选均完成媒体校验，地址全部失效才继续后续路线，同一完整地址不重复探测，遇到限流停止。
4. 校验响应的视频资源 ID、档位声明与媒体格式。上述候选均不可用时，先尝试用本次官方原画回包中的 `file_id/file_hash` 重新分发，再尝试本地可信身份记录，最后进入已有的 `ratio=default` 兼容通道；仍无候选时请求 PC Web 详情，取手机详情没有的 `video.bit_rate` 行，分别校验视频轨和 `bit_rate_audio` 音频轨（DASH 分轨由 `--download` 合并），识别为 `official_web_pc_bitrate`。默认档要求 `206`、MP4 头、实际大小不属于详情与已观察 fplay 的转码集合，并校验时长、音视频轨道及分辨率；大小不同本身不是上传原文件的充分证明。全部取址入口均无候选时报 `source_unavailable`，曾取得原画候选但所有地址均校验失败时报 `probe_failed`。所有候选均排除媒体加密、无效地址格式和无效元数据。原画地址及其下载跳转不再限制固定 CDN 域名，仍检查 HTTP/HTTPS 地址格式；输入作品链接继续限定抖音平台域名。算法全貌见 `docs/original-source-algorithm-2026-11-16.md`。
5. 还原播放地址。本轮格式为 Base64 后的 `a8 00 01 00` 头部加 AES-CBC 密文；响应提供 32 字节 `key_seed`。派生方式为 `SHA512(SHA512(seed) + 固定64字节常量)`，前 16 字节作为 AES key，接下来 16 字节作为 IV；按 PKCS#7 去填充得到 URL。代码在 `original_parser/codec.py`。普通 URL、普通 Base64 URL 也支持。
6. 用 Range 请求核对真实大小并读取 MP4 moov，确认视频、音频、时长和分辨率。支持 moov 位于文件尾部；不用下载整个视频即可完成常规解析校验。
7. 单文件 MP4 下载时核对文件大小，存在官方 MD5 时必须匹配；未提供官方哈希时，校验完整文件的音视频轨道、时长和分辨率，记录本地 MD5/SHA-256，并明确返回 `official_hash_match=null`。可再与本地参考文件做 SHA-256 比较。地址过期或全部镜像下载失败会重新解析一次。

链接提取思路参考 `douyinVd`，网页签名公式参考 `dtk/signing/native/websign.py`，匿名访客初始化参考 `dtk-parse`，档位与音轨校验吸收现有项目的经验。2026-10-16 的原片选档参考 [ucmao/media-parser 的第一候选请求](https://github.com/ucmao/media-parser/blob/36e57ff489d23e1037050c9de7f0a39598f8caee/src/parsers/doubao_parser.py#L351)，并已在抖音作品和本程序默认请求头下验证；没有照搬豆包专属的查询 `key_seed` 前置条件或请求头。关键是 **保留平台取址上下文、选择原片及还原播放地址**。已有 NiKa 第三方客户端只包含调用第三方服务的鉴权与选档逻辑，没有其内部取址算法。

本次结果推翻了此前针对这些样本的“只能经 App 链路取得原画”的判断：实际可以由 Python 直接访问官方接口获得相同源文件。它不是改大 `br` 参数，也不是把 720p/1080p 网页文件重新编码变大。

## 验证与范围

2026-10-16 已使用修复后的默认 `OriginalParser.parse()` 串行验证以下 6 条作品，均返回官方 `original`，真实 MP4 大小、分辨率、时长及音视频轨校验通过。前两条媒体对象与同作品参考地址精确一致。前五条各一次新选档请求成功；正常对照由一次旧 source 兼容请求成功，因而保留该兼容入口。此轮未重新完整下载全部文件或做 SHA-256 对照，也未操作目标 Linux 主机。

| 作品 ID | 大小（字节） | 分辨率 | 视频编码 | 时长（秒） |
| --- | ---: | --- | --- | ---: |
| `7695411862271315236` | 207,466,034 | 720 × 1280 | HEVC | 489.686 |
| `7696148481915833663` | 98,181,767 | 1280 × 720 | H264 | 295.080 |
| `7695338288235810075` | 109,826,171 | 1280 × 720 | H264 | 331.675 |
| `7695328931049655588` | 277,478,492 | 1280 × 720 | H264 | 713.867 |
| `7695160215544532278` | 115,861,098 | 1280 × 720 | H264 | 220.100 |
| `7695305664234589459` | 528,422,694 | 1920 × 1248 | HEVC | 486.342 |

完整源码的 74 项离线测试通过，新增覆盖签发查询的空值及重复字段保留、原画选择、一次旧入口兼容，以及身份/网络/平台限制错误不追加请求。

同日另启动真实 HTTP 服务验证：`/parse` 和 `/api/v1/resolve` 均成功返回作品 `7695411862271315236` 的原画及媒体校验结果；`parse_links.py` 当前填写的作品 `7695330301186297124` 也通过 `/parse` 取得 81,156,780 字节、1280 × 720、约 118.748 秒的 H264 原画，音视频轨校验通过。累计验证 7 条不同作品，临时测试服务已停止。

2026-09-20 的完整下载与哈希对照详见 `实测报告.md`：目标视频已使用独立 ffmpeg 检查音视频解码，另外三条视频完成取址及远程媒体校验。该历史记录中的匿名 HTTP 访问条件现已变化。

2026-09-21 使用新建匿名访客及网页签名重新请求官方接口，已取得以下原画并完成远程媒体校验；此处记录取址结果，不表示本轮重新完成了所有完整下载或目标 Linux 部署检查。

| 作品 ID | 大小（字节） | 分辨率 | 时长（秒） |
| --- | ---: | --- | ---: |
| `7685326449011608873` | 61,314,387 | 1920 × 1080 | 175.149 |
| `7659627743507778842` | 232,472,151 | 720 × 1280 | 456.622 |

离线测试需使用包含 `tests` 目录的完整源码；生产部署包不包含测试文件。在完整源码位于 `/opt/software/python` 时执行：

```bash
cd /opt/software/python
.venv/bin/python -m unittest discover -s tests -v
```

已有离线测试覆盖官方地址编码样本、未知格式、身份不一致、严格原画选档、普通档拒绝、无声音视频拒绝、备用地址、尾部 moov、截断下载、覆盖保护、过期地址重取和缓存刷新。安装后的实际环境仍需调用 `/parse` 验证；`/health` 只检查服务进程在线。

平台接口未公开承诺兼容性，未来可能变更签名、返回格式或访问条件。原画缺失时程序明确标注返回的实际档位；所有候选不可用时仍报错。2026-09-20 的完整下载样本已做 SHA-256 一致性验证；2026-10-16 的结果依据是官方原画档位、媒体对象、真实大小及音视频轨道校验，不代表所有样本均重新完成逐字节对照。没有作者上传前的源文件，不能再推断这是未经平台任何处理的上传原文件。

## 解析故障与修复记录

以下记录区分已确认的故障原因、缓解措施和部署排查项。日期表示修复或记录日期；未留存发生日期的项目单独注明。详情接口凭据失败、原画选档失败和下载地址过期属于不同阶段，不能统一按“更新 Cookie”处理。

### 报错索引

| 现象或错误码 | 优先查阅 |
| --- | --- |
| `403 Uifid Not Found`、`credentials_required`、`credentials_rejected` | [访客身份与自动 Cookie](#访客身份与自动-cookie2026-09-21) |
| `guest_initialization_failed`，首页导航约 20 秒超时 | [访客初始化的页面等待超时](#访客初始化的页面等待超时2026-11-16已修复) |
| 本地可用、Linux 返回 502；`guest_setup_required`、`guest_initialization_failed`、crashpad 错误 | [Linux 浏览器运行环境](#linux-浏览器运行环境部署排查项) |
| `upstream_empty_response`、`upstream_non_json`、“平台返回空内容或非 JSON” | [空内容与非 JSON](#空内容与非-json2026-10-16-补充诊断) |
| `upstream_rate_limited`、`upstream_forbidden`、`upstream_cooldown`、HTTP 429/503 | [集中请求与平台限制](#集中请求与平台限制2026-09-28) |
| `source_unavailable`、“没有可还原的完整原画地址”、“仅返回普通转码档”、`is_source_HDR=1` | [HDR 源作品不列举原片](#hdr-源作品不列举原片2026-11-16第三方可取本项目取不到)；[已验证资产哈希重签](#已验证资产哈希重签2026-11-16历史补救非首次发现)；[自建原画专项复查](#自建原画专项复查2026-11-06尚未恢复缺失原画)；[两家第三方对照与历史原画复测](#两家第三方对照与历史原画复测2026-11-06)；[历史选档修复](#原画选档失败2026-10-16已修复) |
| 解析成功后旧 CDN 地址返回 403、`probe_failed`、`download_failed` | [直链过期与旧缓存](#直链过期与旧缓存2026-10-16-记录)；这些错误也可能有其他原因，需检查媒体校验和下载结果 |

### 访客身份与自动 Cookie（2026-09-21）

- **现象与原因：**直接匿名访问详情接口返回 `403 Uifid Not Found`。已确认平台要求 UIFID 访客身份与网页签名，旧的纯 HTTP 匿名访问条件失效。
- **修复：**用 Playwright 新建匿名 Chromium 上下文取得 `ttwid`、`UIFID_TEMP`，使用配套 User-Agent 及网页签名请求详情。HTTP 模式的访客凭据在进程内复用 20 分钟，并发初始化加锁。相关代码为 [guest.py](original_parser/guest.py) 和 [client.py](original_parser/client.py)。
- **验证：**作品 `7685326449011608873`、`7659627743507778842` 已完成原画取址及远程媒体校验；原始记录见 [Linux 部署说明](deploy/README.md#验证记录2026-09-21)。
- **再次出现时：**先看浏览器初始化日志及凭据配置。显式设置 `COOKIE_FILE` / `--cookie-file` 表示凭据由外部维护，程序不会自动获取或覆盖它；文件更新后 HTTP 下一次解析会重新读取。默认自动访客不需要登录账号。直接 CLI 遇到指定凭据类错误最多刷新一次；HTTP 服务通过队列与冷却处理失败，不在单个任务中重复刷新访客。

### 访客初始化的页面等待超时（2026-11-16，已修复）

- **实际复现：**Windows 本地运行 `parse_links.py` 返回 `guest_initialization_failed`；独立初始化也复现底层 Playwright `TimeoutError`，约 20.6 秒后失败，紧接着的新匿名会话在 1.7 秒内成功取得访客标识。因此本次不是缺少 Chromium；不能将通用错误提示直接当作依赖未安装的证据。
- **修复：**[guest.py](original_parser/guest.py) 收到首页响应后即开始独立等待 `ttwid` 和 UIFID，不再要求首页先完成 `DOMContentLoaded`。导航等待超时时也在同一匿名上下文中检查完整访客标识；只有两种标识都存在才成功。浏览器启动和 Cookie 等待仍有时限，真实网络错误仍返回失败，错误信息补充固定阶段及受限的网络错误码。
- **验证：**新增 6 项导航与 Cookie 回归检查，全项目 91 项测试通过。修复后实际运行当前 `parse_links.py`，`7707196543073275177` 已完成访客初始化、详情和目录查询，返回真实的 `source_unavailable`（8 个普通档）。另从全新进程解析阳性 `7695305664234589459`，取得 528,422,694 字节、1920×1248 的官方 `original`，实际大小及音视频轨道校验通过。本次修复恢复访客初始化，不代表两个缺失原片目标已恢复。

### Linux 浏览器运行环境（部署排查项）

- **现象与原因：**Windows 能获取访客但 Linux 浏览器启动失败，可能出现 `guest_setup_required`、`guest_initialization_failed` 或 HTTP 502。已知环境问题包括未安装 Chromium、缺共享库、服务账户无法读取浏览器目录，以及家目录缺失或属主错误导致 crashpad 初始化失败。这些是不同排查项，不能仅凭 HTTP 502 确定原因。
- **已有处理：**[install.sh](deploy/linux/install.sh) 在目标服务器安装浏览器及依赖；[deploy.sh](deploy/linux/deploy.sh) 和 [upgrade.sh](deploy/linux/upgrade.sh) 提供服务账户及可写家目录的创建处理。该处理已随 `6ba0017` 保存，实际故障发生日期未单独记录；升级时仅指定 `--no-units` 不会创建账户或家目录，首次准备账户需按部署说明执行。
- **再次出现时：**检查服务日志、`.browsers`、共享库及 `douyin-parser` 的家目录和读取权限。用服务实际运行账户验证，不能只凭 root 下 CLI 成功判断服务正常。仅安装 `requirements.txt` 不会下载 Chromium，Windows 的 `.venv` 也不能直接搬到 Linux。操作步骤见 [Linux 部署说明](deploy/README.md)。

### 集中请求与平台限制（2026-09-28）

- **问题与处理：**三个 Java 实例共用解析服务时会提交集中或重复请求。增加统一串行队列、任务间隔、同作品合并、有效期缓存及限制错误冷却，相关提交为 `6ba0017`。这是降低请求与限制风险的措施，不能据此认定每次空响应都由请求频率引起。
- **当前行为：**默认任务间隔为 0.5～1 秒，以进程启动参数为准；累计 3 次限制类失败后冷却 900 秒，真实解析成功清零。冷却返回 HTTP 503、`code=upstream_cooldown` 和 `Retry-After`；队列满或等待超时返回 HTTP 429。需结合响应 `code` 区分本服务排队和上游 HTTP 429。
- **再次出现时：**检查 `/health` 的 `protection.state`、`retry_after` 及日志，按重试时间等待。不要反复重启来绕过冷却，也不要同时启动多份 CLI 批量解析。多个 Python 进程的保护状态独立，详细边界见 [请求保护说明](deploy/REQUEST_PROTECTION.md)。

### 空内容与非 JSON（2026-10-16 补充诊断）

- **现象：**曾统一提示“平台返回空内容或非 JSON，可能需要稍后重试或更新 Cookie”，无法分辨失败发生在详情还是原画接口，也不足以证明 Cookie 过期。
- **已有改进：**`client.py` 分开返回 `upstream_empty_response` 与 `upstream_non_json`，补充请求阶段、HTTP 状态、Content-Type 和响应字节数；识别出的访客验证页面使用凭据类错误。日志不记录 Cookie、密钥或完整签名地址。
- **再次出现时：**保存错误码和上述诊断字段，结合 Linux 浏览器日志、网络、凭据模式及冷却状态排查。该改进帮助定位原因，不代表所有平台空响应均已被修复。若已取得有效 JSON 但只有 `normal` 档，应转查下条原画选档记录。

### 原画选档失败（2026-10-16，已修复）

- **现象：**多个作品报 `source_unavailable`，提示“没有可还原的完整原画地址；不会降级为网页转码档”或“仅返回普通转码档”。同作品的第三方结果可用，项目却只取得更小的 `normal` 档；少数作品仍可正常解析。
- **已确认原因：**旧实现将官方 `video_model.fallback_api` 的完整查询替换为 `aid=392139&stream_type=source`，丢失取址上下文。对本批失败样本，保留完整查询并明确选择原片的组合已验证可以恢复；不能仅据 CDN 域名或查询参数多少判断是否原画。
- **修复：**保留官方签名路径、原有 `stream_type` 和全部查询字段（包括空值、重复字段及 `encode_user_tag`），删除 `logo_type`，覆盖 `force_fids=b3JpZ2luYWw=`（Base64 的 `original`）和 `codec_type=5`。新选档没有可用原画时，仅兼容一次旧 source 入口；身份不一致、网络、403/429 等错误直接返回。继续校验同一视频资源 ID、官方 `original/source`、完整 MP4、非媒体加密及音视频轨道，普通转码档不会当作原画返回。
- **代码与参考：**修复提交 `e23fa61`，入口为 [client.py 的 source_streams / _source_candidates](original_parser/client.py)，回归用例见 [test_parser.py](tests/test_parser.py)。有效线索来自 [ucmao/media-parser 的原片选档实现（固定提交）](https://github.com/ucmao/media-parser/blob/36e57ff489d23e1037050c9de7f0a39598f8caee/src/parsers/doubao_parser.py#L351)，已在本程序默认请求头和匿名访客流程下验证；不依赖豆包页面、登录账号或第三方解析接口，也没有硬编码样本下载地址。
- **验证：**7 条不同作品真实解析成功，74 项离线测试通过，`/parse` 和 `/api/v1/resolve` 实际验证成功。主要失败作品 `7695411862271315236` 取得 207,466,034 字节，`7696148481915833663` 取得 98,181,767 字节，媒体对象与同作品参考一致。原先正常的 `7695305664234589459` 通过一次旧入口兼容取得 528,422,694 字节，证明该分支需保留。完整样本表见 [验证与范围](#验证与范围)。本轮未完整下载全部文件做哈希对照，Linux 是否恢复须在部署后实测。
- **再次出现时：**确认服务正在运行包含上述修复的源码，更新后已重启；记录具体作品和错误信息，区分“未返回原画”与“原画地址解码或校验失败”。不能只换 Cookie、修改 `br`、换 CDN 域名，或用旧签名路径替换其他作品的 VID 来保证恢复。

### 两家第三方对照与历史原画复测（2026-11-06）

本轮在 Windows 本地使用当前源码及新建匿名访客，实际核对 NiKa 中的两个第三方接入：muzzz 的 `POST /detail/users`（`type=details`）和 Snapany 的 `POST /api/v1/resolve`。两家各解析新作品与历史失败作品一次；Snapany 对历史作品指定 `force_refresh=true`，避免只比较旧结果。此前对新作品的 Snapany 历史查询返回 HTTP 404 / `code=40013`，本轮已补充实际解析。凭据仅用于对应服务鉴权，以下记录不含密钥或完整签名播放地址。

**新作品 `7703504174440254762`：**

- 自建原画优选请求返回 8 个档位，旧 source 兼容请求返回 3 个 `normal` 档；两次均无 `original/source`，作品资源 ID 一致。报错中的“3 个”来自最后一次兼容请求。
- muzzz 返回 `level=原画 (3.94MB)`，Snapany 返回 `quality=source, level=原画`；两者指向自建官方回包中同一个 `quality=normal` 的媒体对象。两家的标签均来自其原始响应，本次没有触发 NiKa 缺少 `video_list` 时补“原画”的分支。
- 从官方、muzzz、Snapany 三个地址分别完整下载：均为 **4,135,798 字节**、1080×1920、11.9 秒，H264 视频与 AAC 音频轨道完整；SHA-256 均为 `6231a88c22ea61874f53ce1d5c5c5becfe4a9b4d23c4c49dc7a75f0f4cbb35e1`，MD5 均与官方 `file_hash=ece7f956ac4a5945197adfc0bb7fb894` 一致。Snapany 响应中的大小为 4,131,389，表述文件大小时以实际下载值为准。

**追加作品 `7704212621922159898`（用户提供 muzzz 下载直链）：**

- 自建优选请求返回 11 个档位，旧 source 入口返回 3 个 `normal` 档，均无 `original/source`。两次官方回包都已包含用户链接中的对象 `tos-cn-ve-51-ce/owSq7yAEm0NNREAIDBFqATbDwaoOFEHLfd6Deh`，官方标记为 `quality=normal`，大小为 **72,980,971 字节**，1080×1920、159.638 秒、H264 视频和 AAC 音频。
- 使用 NiKa 配置向 Snapany 发起一次实际解析（`force_refresh=true`），返回 `quality=source, level=原画`，仍指向上述同一对象。muzzz 直接使用用户给出的直链核对，本次没有重复调用其解析 API。
- 从官方地址、用户提供的 muzzz 地址、Snapany 新地址分别完整下载，三份文件 SHA-256 均为 `36660056fa35fb54fa7434e873ab5869b94f35100602ad2f131ce0e43c7d7a04`，MD5 均为 `f5d0bb2f8353bff5e39aa6d60afa5a41`，与官方 `file_hash` 一致。自建已获得同一份文件，失败发生在仅接受 `original/source` 的选档条件；此对照不证明普通档等于作者上传前的源文件。
- 脱敏证据：`output/source-diagnostic-20261106/7704212621922159898-comparison.json` 和 `7704212621922159898-full-comparison.json`。

**README 历史样本复测：**

| 作品 ID | 历史官方原画（字节） | 当前自建结果 | 当前两家第三方结果 |
| --- | ---: | --- | --- |
| `7695411862271315236` | 207,466,034，HEVC | 无 `original/source`；最高普通档 82,354,519 字节、H264 | 均把此 82,354,519 字节的普通档标为“原画”，没有返回历史 207MB 对象 |
| `7685326449011608873` | 61,314,387，H264 | 无 `original/source`；普通档 31,560,443 字节 | 本轮未请求第三方 |
| `7695305664234589459` | 528,422,694，HEVC | 旧 source 兼容请求仍返回 `original`；大小与历史一致，完整音视频轨道及远程媒体校验通过 | 本轮未请求第三方 |

历史 207MB 作品中，两家标为“原画”的当前结果均通过 Range/MP4 媒体校验，大小 82,354,519 字节、720×1280、489.687 秒，对应官方 `normal` 对象 `tos-cn-ve-51/oYBKm1OQYjciBy1EgAEiF4SfK2LQriIBR2hAo8`。历史原画对象为 `o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE`，文件大小及编码均不同。本轮没有完整下载该历史作品的三个当前文件做哈希比较；其比对依据是同一媒体对象及实际媒体校验。两家另给出的 720p 地址均未通过本次预检，不影响上述“原画”地址的比对。

**请求上下文与结论：**

- 本轮策略修改前的 `client.py` 与修复提交 `e23fa61` 无差异，保留完整签发查询、删除 `logo_type`、设置 `force_fids=Base64(original)` 和 `codec_type=5` 的修复仍在。修改前 74 项离线测试通过。
- 历史 207MB 作品的新旧详情具有相同的视频 ID、签名路径和查询字段；`encode_user_tag` 等上下文一致。应用原画选择后，仅匿名 `device_id` 值不同。恢复已保存的历史查询上下文仍只返回普通档，未恢复原画。
- 对新作品和历史 207MB 作品补查“保留完整查询，同时使用 `stream_type=source` 与原画选择”仍无原画；历史作品还核对了公开实现中的 `codec_type=1` 兼容请求，也未返回原画。因此本次没有复现 10 月因查询字段丢失导致的故障。
- 当前可确认的是：部分历史原画已不再由这些官方请求下发；两家第三方在本次样本中，也都将官方普通档作为“原画”返回。旧版自建程序按官方 `original/source` 严格选档，所以报错。528MB 对照仍成功，说明原画取址及解码并非全面失效。不能据此断言平台已删除原文件，也不能确定是保存期限、访问条件还是下发策略变化。
- 诊断后用户曾选择“优先原画，缺失时返回最高可用画质，并标明实际档位”，当时据此修改默认策略。用户于 2026-11-10 要求撤回降级，当前仅输出原画，普通档返回“获取原画失败”；临时策略和当时验证结果见下方历史记录。该次降级没有恢复未下发的历史原画，本轮未部署 Linux。

脱敏证据位于 `output/source-diagnostic-20261106/`：新作品的 `comparison.json`、`full-download-comparison.json`、`snapany-file-comparison.json`，历史样本的 `historical-controls.json`、`historical-providers.json`，以及请求对照 `issued-context-check.json`、`historical-context-replay.json`、`target-combined-selector.json`。原始回包及临时播放地址只保存在本机被 Git 忽略的诊断目录，不能随部署包发布。

### 原画优先与最高可用画质（历史策略，已撤回）

以下记录的是 2026-11-06 的临时降级策略，不代表当前行为。当前实现已经恢复严格原画模式：普通转码档不会作为成功结果返回，也不会缓存。

- **历史行为：**保留完整上下文的原画请求优先；没有可用原画时选择最高可用完整 MP4，并标记实际档位。
- **历史标记：**普通转码曾返回 `fallback_used=true`、`fallback_reason=source_unavailable` 及实际 `quality`、`official_quality`、`level`。单文件原画的 HTTP 成功回包只返回 `data.url`。
- **当时边界**　该次撤回后只接受官方 `original/source` 档位和用已验证 `file_hash` 分发的结果。PC Web 独有档位及其 DASH 下载行为见文首的 2026-11-20 记录。
- **当前缓存：**只有通过媒体校验的官方原画结果缓存；普通档、失败结果和没有媒体校验的结果不缓存。
- **验证：**83 项 Python 离线测试通过；NiKa `mvn -o -pl nika-modules/nika-basic -am -DskipTests compile` 成功。使用编译后的真实 Java 客户端调用本地 Python HTTP 服务，下面三条均通过解析及媒体校验；`/api/v1/resolve` 复用 `/parse` 的缓存并保留实际档位。Java 校验也验证了无音轨、大小不符、来源或标记缺失等结果被拒绝，旧版原画响应仍兼容。临时服务已停止。

| 作品 ID | 实际官方档位 | 分辨率 | 大小（字节） | 选档结果 |
| --- | --- | --- | ---: | --- |
| `7703504174440254762` | `normal` | 1080 × 1920 | 4,135,798 | 最高可用画质，与两家第三方文件一致 |
| `7704212621922159898` | `normal` | 1080 × 1920 | 72,980,971 | 最高可用画质，与两家第三方文件一致 |
| `7695305664234589459` | `original` | 1920 × 1248 | 528,422,694 | 仍优先取得原画 |

本次解析选中的两个普通档的官方 MD5 与前面完整下载验证的文件相同；完整文件 SHA-256 对照见上一节。脱敏联调记录为 `output/source-diagnostic-20261106/quality-policy-live.json`。部署时必须同时更新 Python 服务与 NiKa 后端；本地验证不代表 Linux 已升级。

### 原片桶识别补强（历史实验，已撤回）

该实验曾尝试把 `tos-cn-v-*` 作为辅助证据。由于桶名不能独立证明档位，当前生产逻辑不再使用桶名推断原画；只有官方 `quality=original/source` 或可信官方原片分发记录才会成功。

- 用户指出抖音原画对象使用 `tos-cn-v-0051` 桶。该前缀也出现在已验证的历史原画对象；成功的 2026-09-20 官方原片样本使用 `tos-cn-v-0000c2287`。已知普通转码对象使用 `tos-cn-ve-*`，两者的路径前缀不同。
- 历史选档器曾解码官方 fplay 回包中的地址，并将 `tos-cn-v-<桶名>` 作为辅助原片证据；复核后已删除这条生产判定，因为同类桶名不能替代官方档位和媒体身份证明。
- 当前即使地址位于 `tos-cn-v-*`，只要没有官方 `original/source` 标记或可信 `file_hash` 分发记录，也会返回原画失败。
- 这项补强没有恢复 `7704212621922159898`：当前官方回包未包含用户提供的 `tos-cn-v-0051` 对象，保留签名的直链在 `v11`、`v26`、`v95` 三个 CDN 镜像均返回 HTTP 403，无法核对媒体时长、大小和 VID。具体复测见[调查报告](docs/original-investigation-2026-11-06.md)。
- **排序与验证：**官方 `original/source` 标签始终高于桶路径推断；桶路径候选高于普通转码。`python -m unittest tests.test_parser -v`，43 项通过；覆盖 `tos-cn-v-0051`、已成功的 `tos-cn-v-0000c2287`、普通 `tos-cn-ve-51`、高分辨率和 `a=392139` 情况。目标原画仍需等官方接口返回可验证的原片对象后才能确认恢复。

### 自建原画专项复查（2026-11-06，尚未恢复缺失原画）

按用户最新要求，本阶段只研究自建官方取址，不再调用 Snapany、muzzz 等第三方解析服务。此前的降级策略仅作为历史记录保留；当前普通档成功不作为解析成功，也不作为原画恢复的验收结果。

**失败阶段与对照：**

- 历史作品 `7695411862271315236` 的目标仍是 207,466,034 字节的 HEVC 原片，官方对象为 `tos-cn-v-0051/o0DAUSDIFAtixhHMANdfABbDW5HEECAfgq4MzE`。本轮有效的 fplay 回包均返回正确 VID、`status=10`，但档位列表只有常规或自适应转码，没有该对象和 `original/source` 条目。失败位置在原画档位下发阶段。
- 用户作品 `7704212621922159898` 同样没有取得 `original/source`；已有 72,980,971 字节、1080×1920 的 `normal` 不能据此改称原画。
- 阳性对照 `7695305664234589459` 的旧 source 请求仍返回唯一 `original`：528,422,694 字节、1920×1248、HEVC，远程大小及完整音视频轨道校验通过。本次回包中该原片 `file_id` 与 VID 相同，但不能把这个关系推广到其他作品。

**新增的有限请求对照：**使用官方签发的路径，串行请求并保持间隔；除表中注明的字段外保留原有上下文。

| 核对方向 | 样本与实际结果 | 能确认的范围 |
| --- | --- | --- |
| 平台签发的原始 `play_auth_token`，按 SDK 默认主机请求 GetPlayInfo | 207MB 样本返回 HTTP 200、业务错误 `AccessDenied`，没有资源列表 | 该原样 token 路线当前不可用；不把授权错误记为“查询成功但无原画”，不修改已签名字段 |
| 原片选择中删除 `vquality`，分别用 `codec_type=5` 和 `3` | 207MB 样本和 528MB 对照均只返回转码档；528MB 对照仍能通过旧 source 取得原片 | 不能用去掉画质限制或单独切换 HEVC 选择恢复原画；仍需保留旧 source 分支 |
| `force_fids` 的文件选择语义 | 207MB 样本用已下发文件 ID 的末四位，只返回对应的 32,811,196 字节 `adapt` 档；使用推测的原片 ID（VID）及末四位均返回 7 个转码档 | 该上下文中文件选择器确实生效；VID 并未选中该作品的原片，尚不知道历史原片的真实 `file_id`。早期证据的用例名含 `known_normal`，实际档位为 `adapt` |
| 分别删除 `vps`、`encode_user_tag` | 207MB 样本各返回 7 个转码档，新作品各返回 11 个转码档；均无原画 | 未恢复原片，不能据此认定某个上下文字段是根因 |
| 最小 `aid + stream_type=source + force_fids=Base64(original) + codec_type=5` | 207MB 样本返回 2 个、新作品返回 3 个转码档 | 同时保留 source 与原片选择也未恢复 |
| 保留原片选择，显式增加 `format_type=mp4` | 207MB、新作品、528MB 对照分别返回 7、11、16 个转码档，均无原画 | SDK 中确有 MP4 容器回退逻辑，但这一个容器字段对照未恢复原片，不加入生产重试 |

`play_auth_token` 的签名字段包含 `aid`、`codec_type`、`format_type`、`stream_type` 和 `video_id`；原样回放失败后没有改签名字段试探。默认主机 `vod.bytedanceapi.com` 已通过公开 SDK 的 `EngineParams.getDefaultVodTopHost()` 确认。签名内容和完整地址只保存在本机忽略目录。

**HDR 线索的实际核验：**两个失败作品的详情均带 `is_source_HDR=1`，528MB 对照为 `0`。但已保存的历史 207MB 原片 moov 显示 HEVC Main、8 位，`colr/nclx` 的色彩三元组为 `1/1/1`（Rec.709），实际为 SDR。该详情标记不能直接解释原片缺失。本轮还对公开 APK 中相关字符串做了只读候选定位；这是启发式静态检查，没有执行 APK，也没有据此猜测 HDR 请求参数。

**取证边界：**新作品有一次新建访客失败（`guest_initialization_failed`），该次未进入 fplay 对照，不能计为原画缺失。其后上下文与 MP4 对照复用当天已保存的官方详情，不重新初始化访客。公开实现及 SDK 复查没有建立新的、通过目标原片验收的官方取址路线；公开实现中以更大文件、分辨率或标签认定“原画”的做法未采用。

**当前结论与代码状态：**尚未恢复失败作品的真实原画。现有有效官方回包缺少原画条目，具体是资源可见性、下发策略还是其他访问条件变化仍待确定，不能断言平台删除了原文件。本阶段仅增加诊断脚本、脱敏证据和本文记录，未改变生产取址逻辑，未部署 Linux。

本机证据目录为 `output/original-research-20261106/`。汇总见 `original-research-summary.json`；有限请求脚本为 `check_official_selection.py`，各作品的 `*-official-selection.json`、`*-file-selectors.json`、`*-context-isolation.json` 和 `*-mp4-container.json` 均不包含完整播放地址。原始回包、签名查询和临时地址保存在 `*.private.json`，整个目录由 Git 忽略，不随部署包发布。历史原片的媒体头证据为 `output/source-diagnostic-20261015/7695411862271315236-reference-moov.bin`。

### GitHub 与公开网页复查、成功样本链路对照（2026-11-06）

用户追问 `7695305664234589459` 为何仍可取得原画。已确认全部作品走相同的生产流程；该作品在保留上下文的 original 优选中也只有转码，随后旧 source 分支才返回 528,422,694 字节的 `original`。失败作品在同一分支仍没有原画，不能归因于客户端为成功作品使用另一套专属算法。

在前一专项基础上，进一步核对公开实现并直接验证官方入口，未调用第三方解析服务：

| 方向 | 历史 207MB 失败样本 | 528MB 成功样本 | 用户 `7704212621922159898` |
| --- | --- | --- | --- |
| 官方精选页面签发查询、公开 codec8 选择 | HTTP 200，业务 `code=1`、`status=2002`，未授权 | 唯一 `original`，528,422,694 字节 | HTTP 200，业务 `code=1`、`status=2002`，未授权 |
| 精选签发查询、original 选择与 codec5 | 7 个转码，无原画 | 16 个转码，无原画 | 11 个转码，无原画 |
| 官方 `/aweme/v1/play/`，`ratio=default`、`source=PackSourceEnum_PUBLISH`，匿名 GET | 两个官方域名均 404 | 两个域名均 302 → CDN 206，精确匹配历史原片对象和大小，音视频轨道校验通过 | 两个官方域名均 404 |

PUBLISH 对照域名为 `www.douyin.com` 与 `aweme.snssdk.com`；失败样本的 404 另查正文均为空，不能据此断言平台删除原文件。该验证是公开匿名请求组合，不代表验证了所有签名或授权条件。codec8 的授权拒绝与 codec5 成功回包缺少原画分别记录，不混为同一种错误。

继续核对历史记录：2026-10-15 曾由正常作品页对 207MB 样本发起同参数 PUBLISH 请求，已观察到页面签名，仍为 404、无跳转。该历史结果不计入本日请求数，也不等同于完整复现某个公开项目的 `a_bogus` 签名组合；详细证据与条件参数的适用边界见研究报告。

离线核对还确认：网页详情与精选模型的 fplay 主机和签发路径相同，内嵌档位也相同且均无原画；207MB 失败样本与 528MB 对照的下载限制字段相同；207MB 样本历史成功时 `is_source_HDR` 就已经为 `1`；历史模型消失的两档仅是 540p H264 转码。两条历史作品发布于同一天，成功样本稍早，也不支持仅按发布时间统一失效的简单解释。

公开来源、固定版本、各项证据与限制见[完整研究报告](docs/original-investigation-2026-11-06.md)。本机脱敏汇总为 `output/original-web-research-20261106/original-web-research-summary.json`。该报告记录的是历史调查和已撤回的降级策略；当前生产取址只接受官方原画，普通档会失败。此次验证为真实官方 HTTP 对照及媒体校验，未重新运行前一阶段的 83 项离线测试。

### 真实精选客户端核验（2026-11-07，尚未恢复失败原画）

从精选官网取得 41.0.0 Android 官方安装包，核实真实应用 ID 为 `568863`，完成官方匿名设备注册并使用同一身份取得正确作品详情。对官方签发模型及带签名的播放、下载地址做对照：`7695305664234589459` 仍能取得并校验 528,422,694 字节完整原片；`7695411862271315236` 仍没有历史 207,466,034 字节原片，`7704869082255904042` 也未恢复。两条失败作品的官方普通播放地址均可正常跳转、读取文件，原片/下载选择仍返回空 404；这不能证明原文件已删除。真实精选身份没有解决本次原画缺失，未把该研究路线接入生产。

APK 复核还确认 `isNeedSetCookie()` 实际对应 JSON 的 `need_set_token`，三条真实精选详情均为 `false`；`is_source_HDR` 随详情上下文不同，不能据此认定原片消失的原因。请求条件、媒体验收和脱敏证据见 [11 月 7 日调查记录](docs/original-investigation-2026-11-07.md)。本阶段未调用第三方解析服务，未部署 Linux。

### 历史原片 MD5 分发恢复（2026-11-07，未知新作品仍待修复）

参考 [yt-dlp #7109](https://github.com/yt-dlp/yt-dlp/issues/7109)，将已验证的历史原片 MD5 用作官方 `/aweme/v1/play/` 的 `sign`，以 VID 同时作为 `video_id` 与 `file_id`。作品 `7695411862271315236` 已重新完整下载 207,466,034 字节原片，整文件 MD5 与历史一致，音视频完整；作品 `7685326449011608873` 也经相同机制取得 61,314,387 字节的同一历史原片对象，远程媒体校验通过，第二份文件本轮没有重新完整下载。两条不带 sign 的同类请求均为 404。

这证明原片仍可从官方入口获取，也验证了“已知原片哈希”的取址机制。当前公开详情未提供新作品所需的原片哈希，`7704869082255904042` 仍未恢复，不能将此结果称为通用解析修复。生产没有硬编码作品、哈希或临时地址；取址代码与部署尚未更新。完整结果及新增公开资料对照见[当日调查记录](docs/original-investigation-2026-11-07.md)。

### 新旧素材与精选新版复查（2026-11-12，部分旧素材仍未恢复）

新作品 `7707234108203650342` 已直接取得 119,146,775 字节官方原片；同一签发 URL 在发布约 38 分钟后不再列举原片，而已有可信身份仍可官方重签。旧目标 `7706282108947385626` 当前最大 normal 已完整比较，确认重新编码，不能按大小或标签放行。精选 41.1.0 的真实匿名注册与签名请求、源文件元数据消费者及公开代码增量核对，尚未建立无历史记录的旧作品首次原片取址链路。本轮没有修改生产解析器或部署，详见 [11 月 12 日调查记录](docs/original-investigation-2026-11-12.md)。

同日启用 VPN 后补查了国内外公开实现、Sourcegraph 全局源码和官方客户端保存视频链，并通过 VPN 实测旧目标的两种 fplay 选择及新签发播放 token，仍未取得该旧目标原片。没有将普通档标签或上传完成后的 SourceInfo 当作恢复依据；生产代码未改，详见 [VPN 复查记录](docs/original-investigation-2026-11-12-vpn.md)。

### 已验证资产哈希重签（2026-11-16，历史补救，非首次发现）

- **现象：**`7707196543073275177` 的两个 fplay 选择器只列 8 个普通档，生产返回 `source_unavailable`；但用户持有的同作品参考文件为 132,665,774 字节，明显大于最大普通档 57,651,328 字节。
- **确认原因：**不是原片被删除，而是该作品的 fplay 目录不再列举原片。用参考文件的整文件 MD5 `96e395ae426871e3fc3294755d54308f` 作为 `sign` 请求官方 `/aweme/v1/play/`（VID 同时作为 `video_id` 和 `file_id`），两个官方域名均返回 HTTP 206、`Content-Range` 精确 132,665,774 字节、MP4 头正常。阳性校准 `7706466342664277290` 同步验证同一请求方式有效；去掉 `file_id` 则为 404，说明入口仍按作品身份匹配。
- **修复与边界：**该对象整文件 MD5 与 `sign` 完全一致；720×1282、309.639 秒、avc1+mp4a 均由 moov 实际解析；CDN 对象 `tos-cn-v-0051/oMq8DeoSEA0EB2TDE2AzrAAwANFLbCfo5gtDiE` 与 11 月 13 日记录一致，即参考文件就是官方原片对象本身。**但这条路径依赖外部取得的资产哈希，无法由作品 ID 推出，不属于首次发现**：记录以 `official_play_hash_from_verified_asset` 标记写入 `original_metadata.json`，默认不参与生产，仅 `DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1` 时生效；主线 catalog 仍只接受 `official_fplay_and_mp4_probe`（平台自己下发身份）。
- **验证：**显式开启后 `run.py` 端到端取回 `原画（官方原片分发）`，媒体校验通过；新增回归用例覆盖"默认丢弃且不发请求""开启后仍需通过分发与媒体校验""自定义来源拒绝"，全套 85 项离线测试通过。证据见 [当日调查记录](docs/original-investigation-2026-11-16-asset-hash-recovery.md)。
- **关键限制：**官方原片分发需要 `(video_id, file_id, file_hash)` 三元组，而 `file_hash` 是整文件 MD5——没有原片文件算不出，有文件才需要它来取文件，构成闭环。所以本条只能解释"已知身份为何取不回"，不能解释"身份从哪来"。`7704677676878925119`、`7706282108947385626` 没有可用资产，仍未修复。
- **再次出现时：**先确认是否已有同作品的可靠原片副本或直链，再走本机制重签并完整核对 MD5；没有资产时不要用普通档哈希去撞，也不要按第三方"原画"标签放行。

### 原画列举按作品状态变化（2026-11-16 实测）

- **现象：**同样是历史成功取过原画的作品，一部分长期仍能从官方 fplay 拿到 `quality=original` 一行，另一部分两个选择器都只剩转码档，生产返回 `source_unavailable`。
- **实测：**对 10 个有记录的作品做只读探针（`tools/probe_original_listing.py`，只用作品详情与官方备用播放接口），仍在列举的 4 个公开播放量为 28.4 万–656.7 万，已不列举的 6 个为 64–3.7 万；分辨率、时长、编码、画幅、发布时间都无法区分两组。分辨率与画幅尤其不能作为判据：仍列举的 `7706477018388536499` 只有 31 秒、1080×1920、hevc，而不列举的 `7706732556430953770` 是 1920×1080、416 秒。
- **现场验证：**`7706477018388536499` 用当前代码端到端取回 `原画，1080×1920，27,668,186 字节，31.069 秒`，来源 `official_quality`，媒体校验通过，未使用任何离线哈希。说明"仍列举"的作品随时可取，不需要外部身份。
- **处理：**仍列举时直接解析即可，`parse()` 通过媒体校验后会自动把 `file_id`/`file_hash` 写入 `original_metadata.json`，失效后仍可官方重签。已不列举且没有记录的作品，客户端没有参数能把这一行要回来。
- **再次出现时：**先确认该作品当前是否仍列举（跑一次探针或直接解析），再判断能不能取；不要靠调参数、换 codec、改画幅去"逼出"原画档。详见[当日实测记录](docs/original-investigation-2026-11-16-listing-rule.md)。

### HDR 源作品不列举原片（2026-11-16，第三方可取、本项目取不到）

- **现象：**`7707993970332290314` 用户的第三方解析服务能给出原片地址，本项目两个选择器只拿到 9 个转码档，返回 `source_unavailable`。
- **分界字段：**把 11 个有记录作品逐个取官方详情对齐后，仍在列举原片的 4 个全部 `video.is_source_HDR=0`，不列举的 6 个全部 `is_source_HDR=1`（含本条目标，`is_long_video=1`）。播放量只是伴随现象，`is_long_video` 无法区分两组。原始对照表在[当日记录](docs/original-investigation-7707993970332290314.md)。
- **第三方那条地址是什么：**指向 `v26-dy.ixigua.com` 的 `tos-cn-v-0051-ce` 原片桶，Range 读为 38,562,411 字节 / 326.937 秒 / 720×1280 / avc1+mp4a，`Content-MD5` = `b4665e915a3177897c2cffc8bff735ed`；`expire` 只比签发时刻晚约 27 分钟，是实时签发的短时地址。用该 MD5 作 `sign` 打官方 `/aweme/v1/play/`（VID 同时作 `video_id`/`file_id`）返回 302 → 官方 CDN → 206、`bytes 0-15/38562411`，即**第三方链接就是官方分发的结果**；全零 32 位与转码档 MD5 均返回 404，`sign` 必须是该对象的整文件 MD5。
- **已排除（全部只有 `tos-cn-ve-51-ce` 转码桶）：**fplay `vquality=5/8/9`、`codec_type=1/5/6`、`force_fids=Base64("source")`、**保留模型原值 `force_fids`**、**完全去掉 `force_fids`**、`aid=2329/1128`、`support_hdr=1`/`hdr_type=1`/`enable_hdr=1`；详情的 `play_addr`/`play_addr_265`/`play_addr_h264`/`download_addr`；`video_model.video_list`；分享页 HTML；`iesdouyin iteminfo`（200 空）、web 详情 `aid=6383`（403）、app 详情 `aid=1128`（200 空）、无 `sign` 的分发（404）。
- **第二轮排除（同日，仍未拿到原片行）：**详情 `device_platform` 取 `webapp`/`android`/`iphone`/`unknown`（四种上下文的 `video_model` 完全相同）；fplay `stream_type` 取 `hdr`/`origin`/`original`/`high`/`dash`；fplay `vquality` 全值域 `0`–`13` 加 `hd/sd/source/original/origin/hdr` 共 20 个取值；详情每个 `addr` 的 `url_list` 全部条目；无头浏览器打开作品页并触发播放（页面被挡）；`/play/hd|hdr|source|original|hevc|h264/` 路径矩阵（均为网页壳）。以上全部只有 `tos-cn-ve-51-ce` 转码桶。脚本见 `tools/probe_detail_context.py`、`probe_stream_and_play_paths.py`、`probe_vquality_sweep.py`、`probe_video_page.py`、`probe_download_endpoints.py`。
- **短链下载接口（已实测失败）：**`api.amemv.com/aweme/v1/aweme/download/` 真实存在，但对作品页、分享页、iesdouyin 页以及真实分享短链 `https://v.douyin.com/9odWMuc0J9Q/`（含整段分享口令、加 `aid=1128`）一律返回 `status_code=0 / Url does not match`；短链落地是 `www.douyin.com/video/7707993970332290314?previous_page=web_code_link` 的 72KB 空壳页，无 `play_addr`、无任何桶地址。该接口显然需要 App 侧签名头或认的不是这种短链，本项目无法复现。
- **两种地址形状：**官方档位分发跳转到 `douyinvod` 边缘时带长串参数（`a=1128&br=921&bt=921&btag=…&cquery=…&dy_q=…&mime_type=video_mp4&qs=13&rc=…`），而第三方那条只有 `mime_type` 与 `expire`。最可能说明第三方拿到的是**对象级直读签名**而不是档位分发；但也不能排除只是 `ixigua` 边缘与 `douyinvod` 边缘的跳转形状差异（本项目未观察到 `ixigua` 边缘形状）。两种解释都读不出对象哈希。
- **对象级直读接口已定位、但签名未通：**详情自带 `video.token_auth.play_auth_token`（`GetPlayInfo/2019-03-15` 的 AWS4 签发 query，1 小时有效）；`douyin-32.2.6.apk` 的 `classes30.dex` 里有服务端模板 `%s/video/openapi/v1/?action=GetPlayInfo&video_id=%s&ptoken=%s&aid=%s%s`。按模板请求 `vod.bytedanceapi.com` / `vod-luna.douyin.com` 均返回 `CodeN=100024 InvalidAuthorization`（缺 `Authorization` 头），`api-play.amemv.com` 返回 `10408/10409 Miss the Authorization header / The sign's format is not valid`；用 token 里的 `X-Amz-Credential`/`X-Amz-Signature` 重排成 `AWS4-HMAC-SHA256 Credential=…, Signature=…` 仍被拒；把路径换成 `/video/openapi/v1/` 而 query 原样带 token 时是 `100010 SignatureDoesNotMatch`（路径参与签名），路径保持 `/` 则是 `100013 AccessDenied`（资源解析为空）。该头的构造在客户端原生层，密钥不在明文常量里，因此本项目无法在只输入链接时复现这一步。
- **已有原片直链的登记能力：**`--register-original` 可把一条已知原片直链核验后写成原片身份记录（完整 MP4 + 时长与详情一致 + 不等于任何转码档大小 + 整文件 MD5 经官方重签返回同大小 MP4），记录按外部来源对待，默认不参与取址。实测 `7708052871413075238`：直链 140,778,272 字节 / 1280×720 / 330.867 秒 / `avc1`+`mp4a`，MD5 `351f10c0e8f038973f2a63c9c749cb41`，官方重签得到的地址与小帅那条**同桶同对象 key**（`tos-cn-v-0051/ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8`）。详见[仅输入链接的验收记录](docs/original-investigation-2026-11-16-link-only.md)。
- **代码改动与限制：**对本条目标，已验证参考资产的 MD5 能通过官方 `/aweme/v1/play/` 重新签发，整文件完整性已核实；记录加入 `original_metadata.json`，标记为 `official_play_hash_from_verified_asset`。按外部资产哈希的既定安全策略，默认仍不读取这条记录；设置 `DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1` 或直接给 `run.py` 加 `--allow-external`（`--serve` 同样支持）后，解析器会重新向官方分发取临时地址，并验证 MP4 大小、时长、分辨率和轨道。默认策略下失败时，错误信息会明确提示"本地已有该作品原片身份记录、被策略屏蔽、如何放行"。详见[当日记录](docs/original-investigation-7707993970332290314.md)。
- **问题边界：**HDR 源的 fplay 目录没有列出原片行，故只输入作品 ID 仍无法首次发现该哈希。这条已验证参考资产可供本目标恢复，但不能推广到没有可信资产/哈希的其他作品。
- **再次出现时：**已有同作品可靠原片副本或直链时，可验证整文件哈希并由官方分发重签；没有资产时不要用普通档哈希尝试，也不要按第三方的"原画"标签放行。

### 直链过期与旧缓存（2026-10-16 记录）

- **现象与原因：**历史返回的 CDN 地址已过期或不可访问，重新调用解析又可能命中之前的成功缓存。直链包含媒体对象及签名、时效信息，不是永久下载入口，也不能用替换 VID 的方式复用其他作品的地址。
- **处理：**HTTP 请求传入 JSON 布尔值 `"force_refresh": true`，清除同作品、同凭据及同预检模式的旧缓存后重新解析；刷新失败不会恢复旧缓存，队列与冷却仍生效。下载方法在地址到期或所有镜像下载失败时最多重新解析一次，代码见 [guard.py](original_parser/guard.py) 和 [client.py](original_parser/client.py)。
- **再次出现时：**用原始作品链接重新取址并校验，不重复测试早已失效的 CDN 链接。`force_refresh` 不能绕过平台限制，也不能让上游返回本来没有的原画。

### Linux 复查与后续记录

先查看服务和近期日志，再执行一条真实解析；`/health` 成功只说明进程在线。以下命令在解析节点运行，服务名和目录沿用本项目默认配置：

```bash
cd /opt/software/python
sudo systemctl status douyin-original-parser --no-pager
sudo journalctl -u douyin-original-parser -n 100 --no-pager
curl -sS --noproxy '*' --connect-timeout 5 --max-time 10 http://127.0.0.1:8765/health
curl -sS --noproxy '*' --connect-timeout 5 --max-time 180 \
  -X POST http://127.0.0.1:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7695411862271315236","with_probe":true,"force_refresh":true}'
```

该样本在 2026-10-16 本地实测的验收值为 `code=0`，并取得 207,466,034 字节原画；HTTP 回包只返回 `data.url`，文件大小需通过 CLI 输出或实际下载核对。目标 Linux 主机的结果需另行记录，不能用本地通过代替上线验收。

后续修复请在本章节追加：日期和环境、作品 ID、错误码及失败阶段、确认根因与证据、代码或提交位置、修复方法、验证结果，以及 Linux 更新和重启是否完成。尚未确认的原因写为待排查；日志和记录中去除 Cookie、密钥及带签名的完整地址，保留可复查的作品 ID、媒体大小和错误诊断即可。
