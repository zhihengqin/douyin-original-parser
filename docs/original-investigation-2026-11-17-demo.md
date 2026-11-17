# Evil0ctal 测试站实测与本机复现

2026-11-17（Asia/Shanghai）。本轮确实使用了项目的公开测试站，并将有价值的差异加入可复用审计工具。**五个待解决作品仍未取得经证实的原画文件，不能把本次新增普通播放候选报为修复成功。**

## 实际测试范围

在 `demo.douyin.wtf/playground` 正常界面中，页面显示版本 5.1.11，使用公开共享演示会话。开启 `include_raw`，保持 `refresh` 关闭，依次提交成功对照与五个目标的 POST `/api/v1/parse`，再对当前目标测试 GET `/api/v1/douyin/video`。七项界面任务均完成；捕获到 20 次相关解析/任务轮询 HTTP 响应。该数字不是站点全部网络流量，也不是服务端真正访问抖音的次数，后者不可见。

没有向演示站发送本机抖音 Cookie，没有调用服务器下载、登录私有账号或付费接口。候选首先由第三方演示站发现；随后本机直连官方接口的复现是另一组独立证据，不能混淆两者来源。完整响应与签名链接仅保存在忽略目录 `output/`。

| 作品 | demo 视频档位 | 独立音轨 | 相对此前桌面捕获的新视频 / 音频身份 |
| --- | ---: | ---: | --- |
| 7698054262056552561（成功对照） | 10 | 0 | 0 / 0 |
| 7708319942491344154 | 10 | 1 | 6 / 1 |
| 7708052871413075238 | 11 | 1 | 0 / 0 |
| 7707993970332290314 | 12 | 1 | 0 / 0 |
| 7707964786692083007 | 8 | 1 | 0 / 0 |
| 7706218040236444937 | 5 | 0 | 0 / 0 |

归一化媒体都能映射回 raw，未发现额外隐藏媒体或新的 VID。当前作品 POST 与 GET 入口下发的媒体身份相同。原始响应中的音轨字典也纳入递归审计，没有只检查归一化最高档。

证据：[demo 审计](../output/research-astar-user-hints/demo/audit.json)、[实际界面截图](../output/research-astar-user-hints/demo/completed-get-detail.jpg)、[响应清单](../output/research-astar-user-hints/demo/manifest.json)。

## 本机直连复现

参考当前 main `3c045e11aecd58ab076562f1246931b9dd5d909b` 的纯参数构造函数，以本机现有会话和本机签名实现请求官方 Web 详情。共四次 HTTP 尝试：阳性最小参数一次网络错误；阳性完整参数、当前最小参数、当前完整参数均取得匹配作品的成功回包。

| 当前作品 7708319942491344154 的响应 | bit_rate 行数 | 内嵌模型视频数 | 去重视频身份 | 独立音频 |
| --- | ---: | ---: | ---: | ---: |
| 最小生产参数，aid=392139 | 2 | 7 | 7 | 0 |
| 完整 PC 参数，aid=6383 | 10 | 0 | 10 | 1 |

完整参数的 10 个视频及 1 个音频，逐文件的 hash、FID、大小和稳定对象路径均匹配 demo。**准确增量是 7 个视频身份变成 10 个视频身份加 1 个音频，不是 2 个文件变成 10 个。** 三个新增 MP4 在此次最小参数的内嵌模型中也能取得。多项参数同时变化，因此不能将返回差异单独归因于 aid 或某个版本号。

两种响应有互补性：6383 给出更完整的 Web 档位和音轨，但本次 `video_model` 为空；392139 保留内嵌模型和 fplay 入口。因此补充 PC 请求不能直接覆盖原详情。上游默认参数没有 `support_dash` / `support_h265`；本次没有把这两个开关冒充为上游算法。

随后用最新最小参数回包重新执行原画流程，另三次 HTTP 尝试：original/source 均返回同一组七个视频身份，与内嵌模型完全一致；default 入口返回 404。生产结果仍为 `source_unavailable`。404 不能证明原件不存在，普通档位名称或缺少 original/source 标签也不能单独排除原画身份。

证据：[参数实验](../output/research-astar-user-hints/demo/local-params-summary.json)、[逐文件复现核对](../output/research-astar-user-hints/demo/local-reproduction-audit.json)、[复现说明](../output/research-astar-user-hints/demo/LOCAL-REPRODUCTION.md)、[原画路径复查](../output/research-astar-user-hints/demo/current-source-recheck.json)。

## 新对象的媒体检查

对最初相对桌面捕获新增的六视频和一音频，使用下发的官方 CDN 地址做有限 Range / moov 检查：21 次 HTTP 请求，读取 868,066 字节，无 429/444。没有下载 mdat 或重算整个文件哈希。

| 大小（字节） | 实际类型 | 尺寸 |
| ---: | --- | --- |
| 64,373,113 | AVC1 + AAC MP4 | 720×1280 |
| 53,302,633 | AVC1 + AAC MP4 | 576×1024 |
| 35,937,790 | AVC1 + AAC MP4 | 576×1024 |
| 61,910,133 | AVC1 DASH 视频轨 | 720×1280 |
| 50,839,869 | AVC1 DASH 视频轨 | 576×1024 |
| 33,474,834 | AVC1 DASH 视频轨 | 576×1024 |
| 2,320,949 | AAC DASH 音轨 | 不适用 |

视频容器时长 348.667 秒、音频 348.649 秒，均内嵌当前作品的已知 VID。三份 MP4 位于 `tos-cn-ve-51`，分轨位于 `tos-cn-v-0051`。三个 DASH 视频的 `audio_file_id` 指向同一音轨，其中一档与音轨共享 parent 对象。

三档 MP4 和 DASH 逐档 avcC 配置完全相同，支持对应编码配置的合轨/分轨关系；没有读取编码 sample，不能由此断言视频载荷逐字节相同。桶、尺寸、同 VID、无损合轨或可播放都不足以证明作者上传原文件。新增候选全部保留“原画身份未确认”。

证据：[媒体检查](../output/research-astar-user-hints/demo/media-probes.json)、[轨道及配对说明](../output/research-astar-user-hints/demo/MEDIA-PROBES.md)。此前用户给出的第二个桶是 `tos-cn-v-15c800-ce`，不是 `0051-ce`；域名、桶和 aid 的独立实验见[前轮报告](original-investigation-2026-11-16-bucket-algorithms.md)。

## 已落实的代码改进和验证

本轮修改 [tools/audit_official_sources.py](../tools/audit_official_sources.py) 与 [tests/test_source_audit.py](../tests/test_source_audit.py)：

- 增加默认关闭的 `--web-pc`，只补充官方 Web 详情，不覆盖原详情的 fplay 模型。固定 Windows profile 在结果中明示，Chrome/Blink 版本跟随 UA；不支持的 UA 返回明确诊断。
- 视频与音频独立递归收集，包含 `audio`、`bit_rate_audio`、`audio_list`、JSON 模型及字典形状的 `url_list`。保留 `audio_file_id`、file hash 和字段路径；音轨不混入视频身份，不计为原画成功。
- 记录音轨数量和不完整范围；`--probe-all` 仍只验证视频，并明确音轨未探测。增加作品 ID、模型 VID 与 fplay VID 一致性检查。
- 保留有限请求预算及 429/444 停止行为，不使用历史 catalog 或外部原片哈希作为发现输入。
- 独立复核发现并修复附加请求触发 429/444 后丢弃主路已有视频候选的问题：现在停止后续网络探测，同时保留已发现元数据并标注不完整。纯本地测试覆盖两种停止状态及两种 probe 设置。

实际运行新工具：成功对照和五个目标各五次 HTTP 请求，minimal、web_pc、issued/original/source 五路均收到匹配作品的响应。六个审计结果合计 30 次请求；每份报告均为 `incomplete=false`。候选数是地址身份分组，可能额外包含暂时不能与文件合并的播放入口，不等于去重媒体文件数。

| 作品 | 候选地址身份组 | 独立音轨候选 | 显式 original 候选 | 五路状态 |
| --- | ---: | ---: | ---: | --- |
| `7698054262056552561`（成功对照） | 17 | 0 | 1 | 全部收到响应 |
| `7708319942491344154` | 12 | 1 | 0 | 全部收到响应 |
| `7708052871413075238` | 13 | 1 | 0 | 全部收到响应 |
| `7707993970332290314` | 15 | 1 | 0 | 全部收到响应 |
| `7707964786692083007` | 10 | 1 | 0 | 全部收到响应 |
| `7706218040236444937` | 7 | 0 | 0 | 全部收到响应 |

阳性有一个 original 标记候选；本轮 CLI 没有开 `--probe-all`，因此这六份工具报告的 `original_verified=false` 是“本次未做媒体探测”，不是阳性候选的反证。五个目标的 source/original 路线都返回成功状态，但返回身份没有形成不同于现有转码候选的新源文件证明。

对六份 demo 完整 raw 与三份本地官方回包另外做了离线字段谱系审查：没有发现可用的 parent/source VID；`origin_duet_resource_uri` 为空、`origin_comment_ids` 为 null，`download_misc` 不存在。play、h264/h265 和 download 地址中的视频 ID 均重复当前作品 VID。该审查没有发网络请求，也没有产生新的可查询身份输入，见[谱系审计](../output/research-astar-continuation-20261117/lineage-review.json)。

追加对主目标 `7708319942491344154` 进行一次不下载完整文件的媒体元数据探测。受 100 次 HTTP 请求上限影响，报告标记为不完整：11 个候选组中只有 4 个读取到容器元数据；App 详情的一次响应为 HTTP 200 但响应体为空。四个文件均为 348.667 秒的 AVC1/H.265 + AAC MP4，分别为 720×1280（44,695,234 字节）、576×1024（33,785,763 字节）、540×960（57,163,128 字节）和 576×1024（35,937,790 字节）。完整 MP4、时长、声明大小和尺寸相符只证明这些是有效的转码媒体对象；四者都没有 original/source 来源标记，不能确认上传文件身份。没有把该次不完整探测外推到另外四个目标，完整记录见[限额探测 JSON](../output/research-astar-continuation-20261117/probe-7708319942491344154.json)。

专项验证：`tests/test_source_audit.py`、`tests/test_source_pipeline.py`、`tests/test_media_handlers.py`、`tests/test_vid_lineage_probe.py` 共 **38 passed、34 subtests passed**。报告文件的 `git diff --check` 通过。本轮没有运行整个项目测试，也没有改变生产解析器默认请求和原画判定规则。

证据：[六个作品的工具审计目录](../output/research-astar-user-hints/demo/)。研究浏览器已关闭：[清理记录](../output/research-astar-user-hints/demo/cleanup.json)。

本轮新增的是可复现的完整媒体发现路径、音轨身份和诊断覆盖。五个失败目标的原画首次发现仍未解决；当前证据没有支持将任何新增对象提升为已确认原画。
