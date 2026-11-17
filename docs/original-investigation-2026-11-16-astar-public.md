# 2026-11-16 新一轮公开方案检索与实测

本轮发现并修复了一项真实媒体校验缺陷：合法 QuickTime/MP4 的 `minf/hdlr` 数据处理器覆盖了 `mdia/hdlr` 媒体处理器，导致已有官方 original 地址被错报“缺少音视频轨道”。作品 **7698054262056552561** 的 40,087,514 字节 HEVC/AAC 原画已通过修复后的生产 `probe()`。

## 检索范围与限制

实际检索了 GitHub commits/issues，读取了下列提交、PR 与 issue 的正文和补丁。也分别访问了 Google、Bing 和 DuckDuckGo：Google 返回跳转提示，DuckDuckGo 返回人机验证，Bing 返回与精确词不匹配的宽泛结果。这些搜索没有贡献可实施的新取址代码，不能据此宣称穷尽全网。完整查询结果保存在 `github-search-round2.json`、`github-search-round3.json`、`web-searches.json`。

没有执行外部仓库应用，没有调用第三方解析服务。官方小规模实验使用现有项目凭据会话，未在报告打印 Cookie。没有读取原片 catalog、既有参考文件或参考 MD5 作为发现输入。

## 新读取的公开来源

| 来源 | 代码事实 / 可测试线索 |
| --- | --- |
| [Terry-Wing/twtube, ad45562](https://github.com/Terry-Wing/twtube/commit/ad45562ebd5213eab41e2be791753d64b5e68426) | 宣称 1080p/4K 原画的代码按 bit_rate 的像素面积和码率排序，再回退主 play_addr；没有首次原片身份发现请求。 |
| [KAIRI-WBF/video-explain, 1952246](https://github.com/KAIRI-WBF/video-explain/commit/19522461fd4ca1723854631e9a8008e8b70e34f4) | 取已有 play_addr/download_addr，标签写“无水印原视频”；没有独立原画目录。 |
| [z905888415-beep/ikun-video-downloader, ad10d53](https://github.com/z905888415-beep/ikun-video-downloader/commit/ad10d53730be639138f91e98cc2e536513183470) | 对码率排序并替换 playwm，为结果填“1080P/原画”；此标签不是平台原画证据。 |
| [wangdudu9999-byte/mediapiper, 0569de2](https://github.com/wangdudu9999-byte/mediapiper/commit/0569de226a2a1aa63b2f0798699c8a0a82676b94) | 区分付费试看资产与 download_addr 全长加密资产；default 仍沿用既有实现，不提供 HDR 原片映射。 |
| [Lxontw/hongguoTV, b0b837f](https://github.com/Lxontw/hongguoTV/commit/b0b837fc808e867b2e96ced8f33e620de4d8f3f5) | 共用 fplay 目录的 `force_fids` 和 `encode_user_tag=only_roi_vcube_improve_1` 可能锁定 ByteVC2；去除两者后 codec_type 才可能生效。仅作为抖音 fplay 参数对照线索，没有将目标转至其他平台。 |
| [miaoxiaohu/hongguoTV, 8a38040](https://github.com/miaoxiaohu/hongguoTV/commit/8a3804019b2ea2b68ebf42edb7d00f1ff932f19d) | 相同锁定参数问题及客户端身份复用；没有任意抖音作品原片映射。 |
| [maomaoxiaokuoai/duck, 71a242d](https://github.com/maomaoxiaokuoai/duck/commit/71a242df5a0cde4c479e1f1454ac59a7bdd687b4) | release 声称 ratio=1080p 可返回高分辨率；提交仅更新文档和版本，体积不能证明上传原件身份。 |
| [sokoko-org/nonebot-plugin-parser-lite, cf3359f](https://github.com/sokoko-org/nonebot-plugin-parser-lite/commit/cf3359f3d1b298307f9679ce8ab342695ec5e0f3) | 从 `play_addr.url_list[-1]` 的查询串读取 file_id；提示字段审计也必须解析 URL 查询参数。仍取已下发档位。 |
| [SiAnWn/douyinbox, 00cd77b](https://github.com/SiAnWn/douyinbox/commit/00cd77b7ce4cc1710b1c08e22a206d1a80285230) | 官方分享页播放链与耗配额的外部“原画管线”分开；未发现公开的服务端原画算法。 |
| [NeeYoonc/bili-sync-up PR #238](https://github.com/NeeYoonc/bili-sync-up/pull/238) | default + improve_bitrate=1，并提供官方可复现正例 7698054262056552561。正文称另两个 4K 作品 default 只给 720p，但未公开这两个 ID；不能直接当已证实假原画反例。 |
| [INGHRTY/ING-videoDonload PR #1 / fb6b845](https://github.com/INGHRTY/ING-videoDonload/pull/1) | 补全 default 的 media_type、vr_type、improve_bitrate、source=PackSourceEnum_AWEME_DETAIL；原画分类仍依赖 `tos-cn-v-*` 路径。提供 7524924078063439145、7596496938191654184 可对照样本。 |
| [ucmao/media-parser issue #29](https://github.com/ucmao/media-parser/issues/29) | 维护者讨论更高画质所需成本，但没有公开可运行原片算法；不能将其推测当成已知 App 签名障碍。 |
| [JoeanAmier/TikTokDownloader PR #812](https://github.com/JoeanAmier/TikTokDownloader/pull/812) | 仅客户端可看作品优先已下发 CDN 地址、跳过失败 default；能提高普通视频下载成功率，但不补出原片。 |

## 官方对照结果：不能单凭更高分辨率认定原画

对三个公开样本，分别读取 fplay 原样、original 选择器、source 选择器；再检查 snssdk 最简 default、www+jiji 签名发布源 default、www+ING 完整详情源 default。均只做有限 Range 与 moov 读取，没有完整下载。机器报告为 `default-counterexamples.json`。

| 作品 | 最高可见转码 | 三种 default | fplay 官方 source |
| --- | --- | --- | --- |
| 7524924078063439145 | 3840×2160 HEVC，6,078,776 B | 全部 1280×720 AVC，3,094,888 B | `original`，同 3,094,888 B，MD5 `f47df39189edf5302f3e0685d14e97c5` |
| 7596496938191654184 | 1440×1440 HEVC，169,151,307 B | 全部 720×720 AVC，100,211,975 B | `original`，同 100,211,975 B，MD5 `5e3104420354ec1d66dffc0c79a2f6ef` |
| 7698054262056552561 | 1080×1920 AVC，3,977,493 B | 全部 1080×1920 HEVC，40,087,514 B | `original`，同 40,087,514 B，MD5 `8dfd03e580d0afdd54ff0607276adc93` |

前两个作品还将同一文件同时列为 `normal` 与 `original`，第一条的 Content-MD5 实际匹配两类行。因此这些数据**不能证明 default 返回了假原画**。它们证明了：最高分辨率未必是官方 original；同一文件能在不同目录语义中具有 normal 和 original 两种标签；仅按普通档大小黑名单排除会误伤已有官方 original 证据的文件。是否与作者上传前文件逐字节相同，本轮没有作者参考文件可验证。

## 实际恢复：QuickTime hdlr 覆盖缺陷

第三个作品在修复前已拿到官方 original，但 `inspect_mp4()` 将两个轨道都识别为 `type="url "`，从而 `has_video=false` 且 `has_audio=false`。读取真实 18,445 字节 moov 后确认：

```text
moov/trak/mdia/hdlr       component=mhlr subtype=vide
moov/trak/mdia/minf/hdlr  component=dhlr subtype=url
moov/trak/mdia/hdlr       component=mhlr subtype=soun
moov/trak/mdia/minf/hdlr  component=dhlr subtype=url
```

`original_parser/media.py` 现在只用直接位于 mdia 的 hdlr 决定轨道类型。测试 `tests/test_media_handlers.py` 覆盖 QuickTime 双 handler、不同 box 顺序、真正没有音轨、媒体 handler 缺失但数据 handler 冒充音视频的情况。修改前 3 项失败；修改后与 `tests/test_parser.py` 合跑为 **49 passed，37 subtests passed**。

随后重新从官方详情和 fplay_source 取址，调用生产 `parser.probe()`，返回：`ok=true`、40,087,514 B、1080×1920、46.249 秒、hvc1 视频与 mp4a 音频。实验把 catalog 的读写函数都替换为一旦调用就抛异常，验证没有使用历史身份。证据：`quicktime-fix-verification.json`；仅元数据原始片段：`quicktime-original-moov.bin`；复现脚本：`verify_quicktime_fix.py`。

此恢复对 QuickTime 结构的官方原片生效，不代表两个 HDR 目标 7708052871413075238 / 7707993970332290314 已经恢复。它们的新链路实测由主任务统一记录。

## 旧结论需要保持的边界

- default 404 只证明该请求没有成功，不证明平台从未登记原片。
- 有限 fplay/codec 组合没有列出原片，不等于已经穷尽所有官方接口。
- 尝试若干种 MD5 派生都不匹配，不能推出数学意义的“file_id 不可推导”。现有格式符合随机标识的表现，但不是完整机制证明。
- 单纯更大、分辨率更高、HDR 标志、桶路径或开源工具自称 original，都不应替代官方身份与实际媒体校验。
