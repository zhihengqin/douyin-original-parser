# 再复核 15 个相关项目：官方原片发现续查

目标仍是 <https://www.douyin.com/video/7707993970332290314>，标准仍是作者上传原片，完全自建、免费、只凭链接发现。

**本轮额外复核了 15 个项目，并将其中有请求差异的官方路线写入探针实测；目标原片首次发现仍未修复。** 新进展是部分分享页请求能返回匹配目标的作品数据，但 VID 仍相同，没有新的 video_model 或上传原片身份。其返回地址也没有在本轮通过目标媒体下载验证。

下面是固定源码审查与有限请求实验，不代表完整运行了 15 个上游应用。未调用 TikHub、HelloTik、TikWM、Neirongshu 或其他第三方解析服务；未读取登录凭据文件、原片 catalog、参考文件或参考 MD5。此前五个仓库不计入本表。

## 固定版本与源码依据

完整提交和入口行号另存为 [sources.json](original-investigation-2026-11-16-more-repos-sources.json)。

| 项目、固定版本及源码 | 实际发现 |
| --- | --- |
| [F2 / f6be8c0](https://github.com/Johnserf-Seed/f2/blob/f6be8c0ffba9a127075bbeafe4838716650b6325/f2/apps/douyin/utils.py#L1782-L1830) | 按像素面积、码率选择已有 bit_rate。新版修复 2K/4K 选档，没有额外原片目录请求。 |
| [yt-dlp / fcfd814](https://github.com/yt-dlp/yt-dlp/blob/fcfd814ffac6e3c1976ff7c6065386dcfea9f515/yt_dlp/extractor/tiktok.py#L1495-L1508) | DouyinIE 用普通 Web detail，再枚举已有 play/download/bit_rate；文件前半部分的 TikTok App API 不在该 Douyin 调用链。 |
| [TikTokDownloader / f766a6e](https://github.com/JoeanAmier/TikTokDownloader/blob/f766a6eff25b76fe4d737f10c27258e4da65df7d/src/extract/extractor.py#L1628-L1629) | original_quality 用无签名、只有 video_id/ratio 的 default 请求；仍按大小决定是否采用。 |
| [dingwei2028 / 8a05b4a](https://github.com/dingwei2028/douyin-downloader-local/blob/8a05b4affb4387ad4e46d7ec7adc34f687081bf0/core/downloader_base.py#L1264-L1389) | jiji 六参数 default 的变体，增加三次重试、浏览器自然详情捕获，仍放弃小于所选档的默认档。 |
| [CatchSnap / 8600ef2](https://github.com/Jolly-J/CatchSnap/blob/8600ef28f1edaeea8aaa10086bbb6970be1fb251/lib/parsers/douyin_parser.dart#L170-L250) | 分享页加尾斜杠，显式转发匿名 Cookie、收集 Set-Cookie 并重试；另有旧 iteminfo 回退。 |
| [Douyin-download / 8e89d1b](https://github.com/lazymicezhu/Douyin-download/blob/8e89d1b52f66a4c20c49e8a777caae5bc2c14c3e/DouyinLite/DownloadModel.swift#L105-L119) | 原画按钮调用 TikHub 付费接口，代码不包含服务端原片发现算法。 |
| [svbot / 8caf600](https://github.com/assimon/svbot/blob/8caf6003d5a6ac63000b4e24287136441bf5cdc1/videos/adapter/douyin_adapter.go#L167-L200) | 旧 iteminfo → 首个 play_addr → playwm 改 play。 |
| [api-golang / ee3e7aa](https://github.com/insoxin/api-golang/blob/ee3e7aa8376271e0a849398f2129133c52e36528/main.go#L148-L167) | api-hl.amemv.com 的旧 App detail，aid=1128、version_code=251，然后取首个地址。 |
| [douyin_download / 72d2296](https://github.com/owen-gxz/douyin_download/blob/72d2296d3c072d173ee551114239dfdca813941f/download.go#L88-L98) | GetOriginalVideoUrl 实际也是旧 iteminfo 和去水印路径替换。 |
| [videodl / 52aa299](https://github.com/CharlesPikachu/videodl/blob/52aa299dbbb85d775f8ee02651df63a105cc5a1d/videodl/modules/sources/douyin.py#L22-L42) | iOS 16 分享页 Router 数据 → HTTP iesdouyin play、ratio=1080p。 |
| [res-downloader / f8ac4d9](https://github.com/putyy/res-downloader/blob/f8ac4d9c85baf28322106e40ea3fdea9867e2f74/core/plugins/plugin.default.go#L31-L90) | 代理捕获已有网络媒体响应、复用请求头，没有按公开作品 ID 新查抖音原片。未运行其代理或安装证书。 |
| [MediaBridge / 2a086e9](https://github.com/wqvbjhc/MediaBridge/blob/2a086e9e122ba615b411210973caa0f176943617/src/lib/engines/custom.ts#L7-L124) | 抖音主路线是第三方网关，最后退回本地 RENDER_DATA/play_addr；文件里的 GetPlayInfo 属于头条解析分支。 |
| [douyinxiazai / 973b864](https://github.com/sasigai1/douyinxiazai/blob/973b864a02339823ad88039a3ac1050488d44191/scripts/download_douyin_hd.py#L74-L178) | PC HTML 的 RENDER_DATA/INITIAL_STATE → 收集已有地址并按分辨率排序。 |
| [video-no-watermark / 61934fa](https://github.com/sheen945/video-no-watermark/blob/61934fa34e9968dcc6f3efe27564aeceb94672b6/scripts/nwm.mjs#L7) | HelloTik 服务客户端，原片算法不在该仓库；未请求该服务。 |
| [video-unwatermark / ebc8b03](https://github.com/652036/video-unwatermark/blob/ebc8b03378195cb2356ebca2ec8d6e99b2439547/app/engines/sharepage.py#L221-L262) | 多 UA、带/不带尾斜杠的分享页；另有浏览器捕获和外部服务分支。只采用官方请求线索。 |

CatchSnap 还会将 URL 的 ratio 改为 1080p，并在客户端填写 1080×1920、4 Mbps 等属性（同一解析器 267–325 行）。这些是客户端推定值，不能直接作为实际原片分辨率或码率。

## 本轮新增的请求对照

实现为 [tools/probe_additional_repo_routes.py](../tools/probe_additional_repo_routes.py)，复用上轮探针的官方质量检查、MP4 检查和整轮预算。新增八类请求对照：

1. `https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=<aweme_id>`。
2. `https://api-hl.amemv.com/aweme/v1/aweme/detail/?aid=1128&app_name=aweme&version_code=251&aweme_id=<aweme_id>`。
3. iOS 16 Safari UA 的无尾斜杠分享页。
4. 同一 UA 的带尾斜杠分享页。
5. aweme/32.7.0 App UA 的带尾斜杠分享页。
6. CatchSnap 的匿名 Cookie 分享页：显式把新匿名会话的 ttwid 带给 iesdouyin，并合并该官方域名下发的 Cookie，最多两次。
7. TikTokDownloader 的最简 `play?video_id=<VID>&ratio=default`，不附加 A-Bogus 和 jiji 的其余查询字段。
8. videodl 的 `http://www.iesdouyin.com/aweme/v1/play/?video_id=<VID>&ratio=1080p&line=0`。

这些请求都使用作品 ID 或从匹配作品的官方响应中得到的 VID，没有将其他作品的签名或外部文件哈希放入请求。详情和分享页严格检查 aweme_id；若出现新播放模型，仍需检查匹配 VID 与官方 original/source 标签并验收 MP4。

对分享页提供的 play/download 地址，还实际进行有限 Range/MP4 检查。只改源码中有依据的 `/playwm/` 路径，保留 query，不改写未知 sign。相同媒体 URL 在进程内去重，避免重复验收；URL 不写入证据文件。

默认档、1080p 档以及分享页直接地址均保持“身份待确认”。文件更大、URL 含 original 字样、桶路径和方法名都不作为上传原片的充分证据。

## 目标结果

最终实测：**北京时间 2026-11-16 19:12:19–19:12:26**。

| 路线 | 目标实际响应 | 含义 |
| --- | --- | --- |
| 既有三种 fplay 请求 | 仍只有 9 个普通档，最大 52,471,983 字节 | 本轮未下发 original/source |
| 旧 iteminfo | HTTP 200、status_code=11110 | 没有取得可验收的作品数据；不据此推测具体拒绝原因 |
| 旧 App detail | HTTP 200、空正文 | 没有新的播放模型或原片候选 |
| iOS 16 分享页，两种路径 | 最终均返回匹配作品，同一 VID，没有 video_model；之前出现过无 item_list 的响应 | 页面结果随上下文变化，尾斜杠和 UA 不能保证恢复 |
| aweme/32.7.0 分享页 | 返回匹配作品，VID 仍为 `v28033gi0000dbs4nevog65jrl6u1s10`，没有 video_model | 详情获取有进展，没有新增原片身份 |
| CatchSnap 匿名 Cookie 分享页 | 第一次即返回匹配作品、相同 VID、没有 video_model | 该组合可取得分享页数据；未单独证明只有 Cookie 这一变量导致恢复 |
| 分享页返回的媒体地址 | 去水印路径请求 HTTP 404；CatchSnap 相同地址去重 | 不能把页面解析成功算成实际下载成功 |
| 最简 default | HTTP 404 | 没有取得媒体 |
| iesdouyin 1080p | HTTP 404 | 没有取得媒体 |

最终目标请求计数 16，预算未耗尽，`original_verified=false`，CLI 返回 2。这里只说明已测路线没有取得目标原片，不表示官方不存在其他原片入口，也不把 404 解释为“原片未登记”或“HDR 永远无法下载”。

完整脱敏记录：[more-repos-target.json](original-investigation-2026-11-16-more-repos-target.json)。

## 对照结果

对照作品 `7695305664234589459` 在北京时间 19:12:26–19:12:59 完成：

- 既有 source 请求仍返回官方 original：528,422,694 字节，1920×1248，486.342 秒，HEVC + AAC，MP4 元数据校验通过。
- 分享页实际取到另一文件：67,139,544 字节，1108×720，AVC + AAC，时长相同，路径为 tos-cn-ve-15。探针保留为未证实原片的播放候选，没有因文件可下载就设 original_verified。
- 最终最简 default 与 iesdouyin 播放入口跳转未通过当前域名检查，记为未完成，未扩展生产白名单。它们不能和目标的入口 HTTP 404 合并解释。
- 整轮 28 次 HTTP 请求，预算未耗尽；整体官方原片验证成功来自 fplay，不能归功于新分享页算法。

完整脱敏记录：[more-repos-control.json](original-investigation-2026-11-16-more-repos-control.json)。本轮只读取媒体元数据，没有完整下载这些大文件，也没有进行作者原件的逐字节比较。

## 代码与验证

- 新增独立探针，保留每条路线结果、失败类型和不完整状态。
- 扩展原分享页函数，支持显式 UA、尾斜杠和匿名请求头；默认调用方式兼容。仅报告作品匹配和地址返回，不提前把未检查文件称为普通档或原片。
- 新增 [tests/test_additional_repo_routes.py](../tests/test_additional_repo_routes.py)，验证旧接口身份和平台错误检查、媒体元数据不能独自证明原片、错误作品不能触发媒体请求、地址去重、匿名 Cookie 重试上限及脱敏。既有 catalog 隔离测试继续通过。
- 全量测试：**120 passed，124 subtests passed**。

复现命令（项目根目录）：

```powershell
.venv\Scripts\python.exe tools\probe_additional_repo_routes.py https://www.douyin.com/video/7707993970332290314 --direct --out output\more-repos-target.json
```

本轮没有将未确认的分享页地址、默认档或最高转码接入生产原画结果；目标首次原片发现仍未修复。下一步若要称为原画修复，需要发现新的官方原片身份或独立取得的候选，并完成相应媒体与身份验收，单纯增加相同请求的重试次数不满足验收条件。
