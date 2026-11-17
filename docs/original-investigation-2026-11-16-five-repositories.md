# 五个开源仓库的取址复核与组合算法实测

目标作品：<https://www.douyin.com/video/7707993970332290314>。

验收标准是作者上传原片。2026-11-16 本轮源码审查与实测后，**仍未从这个作品链接首次发现原片地址**。五个仓库没有补出一条在该目标上实测成功的新原片发现路线；这不等于证明所有官方取址方式都不可能。

本轮只读审查固定版本的源码，再运行本项目独立实现的组合探针，没有完整运行五个上游应用。网络实验使用匿名访客和官方接口；没有读取登录凭据、原片 catalog、参考视频、参考 MD5，也没有调用第三方解析或付费 ASR。`fplay` 是本项目此前已经实现的路线，并非这五个仓库的新发现。

## 固定源码与实际能力

| 仓库 | 固定提交 | 实际视频取址逻辑 | 对上传原片发现的贡献 |
| --- | --- | --- | --- |
| jiji262/douyin-downloader | `4255c983db82a6df6d811f04f5572e08794dfb59` | Web detail → 选择分辨率/码率档；显式 original 模式另探测 `play?ratio=default` | 有可复现的默认档请求，但只检查响应头/体积，失败会回退普通档 |
| Evil0ctal/Douyin_TikTok_Download_API | `3c045e11aecd58ab076562f1246931b9dd5d909b` | Web detail → 主 play_addr、bit_rate、带水印 download_addr → 第一个下载成功的 mirror | 当前源码没有另查上传原片的请求，也没有保证选择最高档 |
| cv-cat/DouYin_Spider | `d151f9c2980abc304c1ae4918c2272675cd9e4c2` | Web detail → `video.play_addr.url_list[0]` | 获取现有播放地址，没有原片选档逻辑 |
| yzfly/douyin-mcp-server | `b0bb8b1fbe4f514bf28099b1471928ebb3716ad2` | 移动分享页 `_ROUTER_DATA` → 首个 play_addr → `playwm` 改为 `play` | 提供分享页入口；去水印地址不证明是上传原片 |
| yuxie2025/douyin | `3bb79c0a578a6b70768735b9822da14a48ab61aa` | Android WebView 拦截页面已有 MP4 请求，复用原请求头下载 | 是真实的浏览器下载实现，但捕获播放器请求不等于查到上传原片 |

### jiji262 的请求与选档边界

关键源码：[探测与提升候选](https://github.com/jiji262/douyin-downloader/blob/4255c983db82a6df6d811f04f5572e08794dfb59/core/downloader_base.py#L1333-L1435)、[URI 选择](https://github.com/jiji262/douyin-downloader/blob/4255c983db82a6df6d811f04f5572e08794dfb59/core/downloader_base.py#L1446-L1465)、[签名构造](https://github.com/jiji262/douyin-downloader/blob/4255c983db82a6df6d811f04f5572e08794dfb59/core/api_client.py#L479-L513)。

```text
GET https://www.douyin.com/aweme/v1/play/
    ?video_id=<实际选中 play_addr.uri>
    &ratio=default
    &line=0
    &is_play_url=1
    &watermark=0
    &source=PackSourceEnum_PUBLISH
    [&ss_is_p_v_ss=1，仅官方 is_need_set_cookie 为真时]
    &a_bogus=<与 UA 配套的动态签名>

Range: bytes=0-0
Referer: https://www.douyin.com/
Origin: https://www.douyin.com
Accept: */*
```

这条 play 请求不合并 detail 的 aid/msToken 等默认参数。上游优先 A-Bogus，生成异常才回退 X-Bogus；本轮复现的是成功生成 A-Bogus 的正常分支。A-Bogus 与 X-Bogus 是请求签名，不是未知原片的文件 MD5。

上游接受终点 HTTP 200/206、video/* 和可解析的正数文件大小，不读取 MP4 内容。它还要求默认档比所选转码档更大才置顶；[测试明确保留“小原片不提升”的行为](https://github.com/jiji262/douyin-downloader/blob/4255c983db82a6df6d811f04f5572e08794dfb59/tests/test_original_quality_promotion.py#L132-L142)。所以不能直接复用它的“original 下载成功”作为本项目的原片验收结果。

此次 HEAD 的直播 origin/RSC 修复没有改变短视频的上述实现。`core/downloader_base.py` 与此前审查的 `7c4b8b2252acbfe24728664cc77364bb75a24ecb` 副本内容一致。

### 另外四个仓库的调用证据

- Evil0ctal 的详情接口：[endpoints.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/endpoints.py#L275-L282)。当前代码在 `src/dtk`；[parser.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/parser.py#L306-L334) 只映射已有地址，[plan.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/media/plan.py#L220-L240) 将码率档扁平化成 mirrors，[Go 下载器](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/docker/downloader/download.go#L143-L164) 首个成功即返回。事后 SHA-256 用于下载归档，不提供原片首次发现能力。
- cv-cat 的 [get_work_info](https://github.com/cv-cat/DouYin_Spider/blob/d151f9c2980abc304c1ae4918c2272675cd9e4c2/dy_apis/douyin_api.py#L235-L278) 使用 `aid=6383`、`request_source=600`、`origin_type=video_page`、该接口的版本参数及 Web 签名；[data_util.py](https://github.com/cv-cat/DouYin_Spider/blob/d151f9c2980abc304c1ae4918c2272675cd9e4c2/utils/data_util.py#L49-L64) 直接选首个 play_addr。其 creator `get/url` 调用消费发布流程已有的封面 URI，没有从任意公开作品链接发现未知原片 URI 的代码。
- yzfly 的 [MCP 入口](https://github.com/yzfly/douyin-mcp-server/blob/b0bb8b1fbe4f514bf28099b1471928ebb3716ad2/douyin_mcp_server/server.py#L82-L132) 与 [独立脚本](https://github.com/yzfly/douyin-mcp-server/blob/b0bb8b1fbe4f514bf28099b1471928ebb3716ad2/douyin-video/scripts/douyin_downloader.py#L84-L134) 使用相同分享页流程。ASR API key 用于语音转写，不是抖音取址所需条件。
- yuxie 的 [WebView hook](https://github.com/yuxie2025/douyin/blob/3bb79c0a578a6b70768735b9822da14a48ab61aa/base_lib/src/main/java/com/yuxie/baselib/webView/WebViewActivity.java#L431-L435) 进入 [DownloadUtils](https://github.com/yuxie2025/douyin/blob/3bb79c0a578a6b70768735b9822da14a48ab61aa/base_lib/src/main/java/com/yuxie/baselib/utils/DownloadUtils.java#L37-L81)，再以相同 URL/headers 下载。它的 MD5/ETag 比较只能检查所下载的那个对象，不能证明对象是原上传文件。

本轮按接口事实独立编写探针，没有复制 cv-cat 或 yuxie 的应用代码。既有 A-Bogus 模块保留其 JohnserfSeed/F2 Apache-2.0 版权头。

## 组合算法

实现：[tools/probe_repo_algorithm.py](../tools/probe_repo_algorithm.py)。

1. 从输入链接解析 aweme_id，以新建的匿名访客会话取官方详情，要求响应作品 ID 匹配。本项目 HTTP 详情入口沿用 `aid=392139`；五仓库普遍使用的 PC `aid=6383` 已有自然页面对照证据，不能将两种详情上下文混为一次实验。
2. 详情确有 `video_model` 时，核对 model VID 与 play_addr URI，检查 fallback 域名及路径，分别请求原样目录、`force_fids=base64(original)&codec_type=5` 和 `stream_type=source`。不调用可能读 catalog 的 production `source_streams()`。
3. 仅当官方回包的作品 VID、状态和 `quality=original/source` 均符合时，解码其地址并读取 ftyp/moov。校验 Range 总长、声明大小、完整音视频轨道、时长和分辨率；媒体若带有不同的内嵌 VID，则暂列身份待确认。目录标签和媒体元数据验证通过，才报告 `official_source_verified`。
4. 独立执行 jiji 的默认档探测；不要求必须先有 video_model，不要求原片比转码大。签名、UA、Origin、Referer、选中 URI 和条件 ss_is_p_v_ss 按上游正常分支复现。默认档即使可下载、体积不同，也保持 `default_candidate_identity_unconfirmed`，不能凭这些条件升级为原片。
5. 使用 yzfly 的移动 UA 读取官方分享页，只消费匹配作品的 Router JSON；分享页若提供另一有效 VID，可在固定上限内再探测其默认档。yuxie 的页面播放拦截作为另一种媒体观察方法，沿用此前自然 PC 页面证据；本轮未重新运行 Android 应用，也未声称对其 WebView 环境完成完全等价复现。

`official_source_verified` 的含义是“官方响应标原片，且相应 MP4 元数据校验通过”。本轮没有完整下载两个对照的大文件，没有与作者持有的原始文件逐字节比较，所以不将这一标记扩展解释为已完成作者原件的哈希比对。

CLI 整轮限制 64 次 HTTP 请求（包含重定向）、8 MiB 请求 Range 字节预算、120 秒内发起请求；单个 MP4 元数据检查另限制 16 次/2 MiB，HTML 限制 4 MiB，JSON 沿用客户端 8 MiB/响应上限。浏览器访客初始化属于现有模块，不在 HTTP 计数内；120 秒也不是强制中止所有响应体读取的硬超时。超限、网络失败、白名单拦截和未验收的剩余候选保留为不完整结果。

## 实测结果

最终复测时间：2026-11-16 10:32:30–10:33:19 UTC。

| 作品 | fplay 结果 | 默认档/分享页 | 本轮判定 |
| --- | --- | --- | --- |
| 目标 `7707993970332290314` | 三种请求均 9 档，最大 52,471,983 字节，没有 original/source；VID `v28033gi0000dbs4nevog65jrl6u1s10` | default HTTP 404；分享页 HTTP 200、Router 存在但 item_list 不存在 | 未发现原片；CLI exit 2；预算未耗尽 |
| 对照 `7695305664234589459` | source 请求返回 original：528,422,694 字节，1920×1248，486.342 秒，HEVC + AAC | 最终 default 跳转未通过域名检查；分享页未返回 item_list | 官方 original 和媒体校验通过；该 default 路线仍未完成 |
| 对照 `7706430541934972201` | source 请求返回 original：87,979,914 字节，1920×1440，46.208 秒，AVC + AAC | 初测 default HTTP 206，同样大小和媒体元数据；最终复测 default 跳转未通过域名检查；分享页未返回 item_list | 官方 original 和媒体校验通过；default 单独仍不作身份证明 |

两个对照原片的元数据分别只读取 587,651 与 37,111 字节，没有完整下载其媒体载荷。目标最终共 6 次 HTTP 请求，三个响应明确包含普通档位，并非请求预算不足或详情整体失败。

机器证据：

- [目标最终结果](original-investigation-2026-11-16-five-repo-target.json)
- [528 MB 对照最终结果](original-investigation-2026-11-16-five-repo-control.json)
- [87 MB 对照最终结果](original-investigation-2026-11-16-five-repo-default-control.json)
- [87 MB 对照初次 default 206 结果](original-investigation-2026-11-16-five-repo-default-control-initial.json)

PC 播放拦截的已有证据见 [此前官方链接调查](original-investigation-2026-11-16-official-link-discovery.md) 和 [PC 上下文证据](original-investigation-2026-11-16-pc-context-evidence.json)。匿名自然页面下发给目标的是 12 个普通档（8 MP4、4 DASH），实际播放观察到 576×1024 转码；这能解释浏览器拦截方法当前看到什么，不能外推所有客户端都只可能取得这些资源。

## 复现与测试

在项目根目录执行：

```powershell
.venv\Scripts\python.exe tools\probe_repo_algorithm.py https://www.douyin.com/video/7707993970332290314 --direct --out output\repo-target.json
```

退出 0 表示本轮取得了官方原片标签且媒体校验通过；退出 2 表示未证实。`original_not_discovered` 只描述这个有限探针本轮没有发现原片，不表示“该作品不存在原片”；`investigation_incomplete` 表示有路线或候选未能完成验收。

新增测试：[tests/test_repo_algorithm_probe.py](../tests/test_repo_algorithm_probe.py)，覆盖 catalog 读写隔离、普通档/错误 VID/不完整媒体拒绝、不同内嵌 VID 待确认、大小不同不能证明默认档原片、缺 model 仍探测 default、分享页身份检查、跳转计入全局预算、候选省略报告不完整和错误输出脱敏。

`python -m pytest -q`：**116 passed，121 subtests passed**。

本轮新增隔离探针、测试和证据，没有把待确认的 default 或最高转码提升为生产原画结果。目标首次发现原片的问题尚未修复。

## 对旧调查记录的更正

- Evil0ctal 当前 `src/dtk` 源码已完整审查，不能再以“取不到源码”作为结论依据。
- yuxie 确有 WebView 媒体拦截与下载代码，不是只有模板。
- default 404 只能说明该请求没有返回可用地址；不能据此证明“平台没有登记原片”。
- 原片可能小于超分转码；HDR 标志、文件更大、原片风格的桶路径都不能单独证明原片身份，也不能单独证明官方链路必然失败。
- 登录下载流程和 native Authorization 等推测，不因本次仓库源码检查而得到验证。没有可复现的请求证据时，不能把它们写成目标失败的确定原因。
