# 抖音原画独立解析程序

输入抖音链接，直接访问平台官方接口，取得 `source/original` 档位并还原播放地址。支持完整 MP4 校验、下载、与本地样本做 SHA-256 对照，以及本地 HTTP API。

**解析失败时先看：[解析故障与修复记录](#解析故障与修复记录)。** 该章节集中记录历史报错、已确认原因、修复方式、验证证据和 Linux 复查命令；后续排障先按错误码查阅，并在修复后追加记录。

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

其他选项：`--url-only` 只打印地址；`--no-probe` 跳过远程媒体校验。默认自动初始化访客，无需手动配置 Cookie。

`source_unavailable` 会区分“未返回原画档位”和“原画档位存在但地址不可用”。“仅返回普通转码档”表示本次接口回包没有 `original/source`，不等于地址解码失败或 Cookie 过期；自动更新 Cookie、重试或跳过媒体校验并不保证恢复原画。即使普通档达到 1080p，也不能仅凭分辨率认定为原画。存在原画但无法使用时，错误会汇总格式、媒体加密标记、地址缺失、解码或地址校验等原因，不包含 Cookie、密钥或完整播放地址。

已有有效访客凭据时，可用 `--cookie-file credentials.json` 指定文件，或在 `parse_links.py` 设置 `COOKIE_FILE`。支持 `name=value; ...` 文本、名称到值的 JSON 对象、浏览器导出的 Cookie JSON 数组，以及包含 `cookies` 和 `user_agent` 的 dtk-parse `credentials.json`；后者会保留凭据配套的 User-Agent。显式指定文件时不自动获取或覆盖其 Cookie；HTTP 服务每次解析重新读取该文件，外部更新后下一次请求即可生效。

## Linux 生产部署：三个 Java 实例共用服务

当前主解析节点为已验证可用的 `172.31.0.4`，目录仍为 `/opt/software/python`，三个 Java 实例主调用地址为 `http://172.31.0.4:8765`。HTTP 服务新增统一串行队列、任务间隔、同作品请求合并、有效期缓存和连续失败暂停。已有服务升级及适用范围见 [请求保护说明](deploy/REQUEST_PROTECTION.md)，首次部署见 [Linux 部署说明](deploy/README.md)。备用解析节点若被启用，各进程的保护状态独立。

## HTTP 接口

Linux 无 Docker、三个 NiKa 实例共用服务的部署步骤见 [部署说明](deploy/README.md)。执行 `.venv/bin/python package.py` 可在项目父目录生成源码部署包，包含虚拟环境安装脚本和 systemd 配置。

```bash
cd /opt/software/python
.venv/bin/python run.py --serve --port 8765
```

默认监听 `127.0.0.1`，提供 `GET /health`、`POST /parse` 和 `POST /api/v1/resolve`。

默认最多同时受理 6 个 HTTP 请求，实际访问上游始终串行，每个完整任务结束后默认随机间隔 3～6 秒，可由 `REQUEST_INTERVAL` 调整。同作品完整链接/ID 自动合并，成功且已校验的原画结果最多缓存 5 分钟，并提前 60 秒避开地址到期；累计 3 次限制类错误后冷却 15 分钟，真实解析成功清零。冷却返回 HTTP 503 和 `Retry-After`，满队列或等待超时返回 HTTP 429。参数及短链、进程内状态等边界见 [请求保护说明](deploy/REQUEST_PROTECTION.md)。这些措施降低重复访问，不保证不会被平台限制。

下载或转存发现旧直链失效时，调用方可在解析请求中传入 `"force_refresh": true`。服务会清除当前作品及凭据范围内的旧成功缓存，重新执行取址和媒体校验；相同作品的在途请求仍合并，排队、任务间隔和冷却规则继续生效。刷新失败不会回落到原来的缓存地址。该参数必须是 JSON 布尔值，默认 `false`。播放地址是有时效的临时链接，业务方应在消费失败后重新解析原作品链接，不能长期复用保存的 CDN 地址。

```bash
curl --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://127.0.0.1:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7685326449011608873","with_probe":true}'
```

核心响应结构：

```json
{
  "code": 0,
  "msg": "原画解析成功",
  "data": {
    "aweme_id": "7685326449011608873",
    "provider": "douyin-official-source",
    "url": "https://平台CDN/临时播放地址",
    "size_bytes": 61314387,
    "width": 1920,
    "height": 1080,
    "duration_seconds": 175.149,
    "source_selected": true,
    "reference_match": null,
    "video_list": [
      {"quality": "source", "level": "原画", "size": 61314387, "url": "https://平台CDN/临时播放地址"}
    ]
  }
}
```

实际响应还包含备用地址、有效期、编码、官方文件 MD5、媒体探测结果等。`size` 和 `size_bytes` 均以字节计。`source_selected` 表示选择了官方标注的源档；`reference_match=true` 仅在完整下载并与指定对照文件 SHA-256 相同时设置。

NiKa 已新增独立的 `selfhosted` 渠道，页面名称为“自建原画（抖音）”，与 Snapany、muzzz 并列。默认由 Java 后端访问 `http://127.0.0.1:8765/parse`，支持排队限流、在线检查和原画媒体校验。需要同时发布修改后的 NiKa 后端与 NiKa-Admin 前端，再在任务中心保存渠道。部署配置和启用步骤见 [部署说明](deploy/README.md)。HTTP 示例服务不自带公网鉴权，跨机器部署时使用后端可达的内网地址。

## 核心算法与已有项目的区别

1. 提取作品 ID，支持视频链接、`modal_id`、分享文案和短链。
2. 初始化或复用匿名访客凭据，计算 `x-secsdk-web-signature`，请求官方 Web 详情，使用 `aid=392139` 取得非空 `video_model`。普通 `aid=6383` 的 `bit_rate` 只用于此前的转码档对比，不作为本程序的原画结果。
3. 从 `video_model.fallback_api` 读取平台签发的 `/video/fplay/1/{签名}/{video_id}` 路径。保留完整查询（包括原有 `stream_type`、`encode_user_tag` 等上下文），删除 `logo_type`，覆盖 `force_fids=Base64("original")` 与 `codec_type=5`。新选档没有可用原画时，再使用同一签名路径的 `aid=392139&stream_type=source` 兼容一次；不反复重试。
4. 校验响应的作品资源 ID，筛选 `quality=original/source` 且为完整 MP4 的候选。
5. 还原播放地址。本轮格式为 Base64 后的 `a8 00 01 00` 头部加 AES-CBC 密文；响应提供 32 字节 `key_seed`。派生方式为 `SHA512(SHA512(seed) + 固定64字节常量)`，前 16 字节作为 AES key，接下来 16 字节作为 IV；按 PKCS#7 去填充得到 URL。代码在 `original_parser/codec.py`。普通 URL、普通 Base64 URL 也支持。
6. 用 Range 请求核对真实大小并读取 MP4 moov，确认视频、音频、时长和分辨率。支持 moov 位于文件尾部；不用下载整个视频即可完成常规解析校验。
7. 下载时核对文件大小和官方 MD5；可再与本地参考文件做 SHA-256 比较。地址过期或全部镜像下载失败会重新解析一次。

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

已有离线测试覆盖官方地址编码样本、未知格式、身份不一致、普通档拒绝、无声音视频拒绝、备用地址、尾部 moov、截断下载、覆盖保护和过期地址重取。安装后的实际环境仍需调用 `/parse` 验证；`/health` 只检查服务进程在线。

平台接口未公开承诺兼容性，未来可能变更签名、返回格式或访问条件。无法取得原画时程序明确报错，不把网页转码档改名为原画。2026-09-20 的完整下载样本已做 SHA-256 一致性验证；2026-10-16 的结果依据是官方原画档位、媒体对象、真实大小及音视频轨道校验，不代表所有样本均重新完成逐字节对照。没有作者上传前的源文件，不能再推断这是未经平台任何处理的上传原文件。

## 解析故障与修复记录

以下记录区分已确认的故障原因、缓解措施和部署排查项。日期表示修复或记录日期；未留存发生日期的项目单独注明。详情接口凭据失败、原画选档失败和下载地址过期属于不同阶段，不能统一按“更新 Cookie”处理。

### 报错索引

| 现象或错误码 | 优先查阅 |
| --- | --- |
| `403 Uifid Not Found`、`credentials_required`、`credentials_rejected` | [访客身份与自动 Cookie](#访客身份与自动-cookie2026-09-21) |
| 本地可用、Linux 返回 502；`guest_setup_required`、`guest_initialization_failed`、crashpad 错误 | [Linux 浏览器运行环境](#linux-浏览器运行环境部署排查项) |
| `upstream_empty_response`、`upstream_non_json`、“平台返回空内容或非 JSON” | [空内容与非 JSON](#空内容与非-json2026-10-16-补充诊断) |
| `upstream_rate_limited`、`upstream_forbidden`、`upstream_cooldown`、HTTP 429/503 | [集中请求与平台限制](#集中请求与平台限制2026-09-28) |
| `source_unavailable`、“没有可还原的完整原画地址”、“仅返回普通转码档” | [原画选档失败](#原画选档失败2026-10-16已修复) |
| 解析成功后旧 CDN 地址返回 403、`probe_failed`、`download_failed` | [直链过期与旧缓存](#直链过期与旧缓存2026-10-16-记录)；这些错误也可能有其他原因，需检查媒体校验和下载结果 |

### 访客身份与自动 Cookie（2026-09-21）

- **现象与原因：**直接匿名访问详情接口返回 `403 Uifid Not Found`。已确认平台要求 UIFID 访客身份与网页签名，旧的纯 HTTP 匿名访问条件失效。
- **修复：**用 Playwright 新建匿名 Chromium 上下文取得 `ttwid`、`UIFID_TEMP`，使用配套 User-Agent 及网页签名请求详情。HTTP 模式的访客凭据在进程内复用 20 分钟，并发初始化加锁。相关代码为 [guest.py](original_parser/guest.py) 和 [client.py](original_parser/client.py)。
- **验证：**作品 `7685326449011608873`、`7659627743507778842` 已完成原画取址及远程媒体校验；原始记录见 [Linux 部署说明](deploy/README.md#验证记录2026-09-21)。
- **再次出现时：**先看浏览器初始化日志及凭据配置。显式设置 `COOKIE_FILE` / `--cookie-file` 表示凭据由外部维护，程序不会自动获取或覆盖它；文件更新后 HTTP 下一次解析会重新读取。默认自动访客不需要登录账号。直接 CLI 遇到指定凭据类错误最多刷新一次；HTTP 服务通过队列与冷却处理失败，不在单个任务中重复刷新访客。

### Linux 浏览器运行环境（部署排查项）

- **现象与原因：**Windows 能获取访客但 Linux 浏览器启动失败，可能出现 `guest_setup_required`、`guest_initialization_failed` 或 HTTP 502。已知环境问题包括未安装 Chromium、缺共享库、服务账户无法读取浏览器目录，以及家目录缺失或属主错误导致 crashpad 初始化失败。这些是不同排查项，不能仅凭 HTTP 502 确定原因。
- **已有处理：**[install.sh](deploy/linux/install.sh) 在目标服务器安装浏览器及依赖；[deploy.sh](deploy/linux/deploy.sh) 和 [upgrade.sh](deploy/linux/upgrade.sh) 提供服务账户及可写家目录的创建处理。该处理已随 `6ba0017` 保存，实际故障发生日期未单独记录；升级时仅指定 `--no-units` 不会创建账户或家目录，首次准备账户需按部署说明执行。
- **再次出现时：**检查服务日志、`.browsers`、共享库及 `douyin-parser` 的家目录和读取权限。用服务实际运行账户验证，不能只凭 root 下 CLI 成功判断服务正常。仅安装 `requirements.txt` 不会下载 Chromium，Windows 的 `.venv` 也不能直接搬到 Linux。操作步骤见 [Linux 部署说明](deploy/README.md)。

### 集中请求与平台限制（2026-09-28）

- **问题与处理：**三个 Java 实例共用解析服务时会提交集中或重复请求。增加统一串行队列、任务间隔、同作品合并、有效期缓存及限制错误冷却，相关提交为 `6ba0017`。这是降低请求与限制风险的措施，不能据此认定每次空响应都由请求频率引起。
- **当前行为：**默认任务间隔为 3～6 秒，以进程启动参数为准；累计 3 次限制类失败后冷却 900 秒，真实解析成功清零。冷却返回 HTTP 503、`code=upstream_cooldown` 和 `Retry-After`；队列满或等待超时返回 HTTP 429。需结合响应 `code` 区分本服务排队和上游 HTTP 429。
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

该样本在 2026-10-16 本地实测的验收值为 `code=0`、`data.source_selected=true`、`data.size_bytes=207466034`、`data.probe.ok=true`，不能只看 HTTP 200。目标 Linux 主机的结果需另行记录，不能用本地通过代替上线验收。

后续修复请在本章节追加：日期和环境、作品 ID、错误码及失败阶段、确认根因与证据、代码或提交位置、修复方法、验证结果，以及 Linux 更新和重启是否完成。尚未确认的原因写为待排查；日志和记录中去除 Cookie、密钥及带签名的完整地址，保留可复查的作品 ID、媒体大小和错误诊断即可。
