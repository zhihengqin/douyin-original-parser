# 用户提供的域名、0051 桶与开源算法实测

本轮落实了三项进展：真实官方桌面客户端正负对照、0051 分轨对象关联核查，以及审计器遗漏音频地址的修复。**五个目标作品的原画首次发现仍未修复。** 无 `original` / `source` 标签不作为排除候选的条件；default 阳性已证明可以通过不依赖这些标签的分发入口取得媒体。0051 桶、域名、`a=392139` 和更大体积也不能单独证明原片。

用户线索为三个主机 `v13-default.365yg.com`、`v26-dy.ixigua.com`、`v3-qingtao.douyinvod.com`，两个桶 `tos-cn-v-0051`、`tos-cn-v-15c800-ce`，以及 CDN query `a=392139`。下文的 `tos-cn-v-0051-ce` 是本轮另外观察到的分轨桶，并非用户给出的第二桶；阳性 source 所在桶是用户给出的 `tos-cn-v-15c800-ce`。以下仅描述有限的源码与网络实测，不宣称遍历全网或全部抖音接口。独立发现与请求阶段没有使用外部原片 catalog 或参考 URL；历史资产只在冻结候选后作离线比较。

## 实测域名、参数与对象关系

| 检查 | 实际结果 | 能支持的结论及边界 |
| --- | --- | --- |
| 两个已下发 0051/0051-ce 视频分轨对象 | 原址均 206；总长分别 41,979,651 / 39,056,996 字节 | 可读取官方下发对象；并不证明上传原文件 |
| 只把上述对象的 `a` 改为 392139 | 均继续 206，总长及所读前 32 字节相同 | 未出现新对象或更高档；相同头部不证明完整文件相同 |
| 去掉 `media-video-avc1`，请求 parent 路径；原 aid 与 392139 各一次 | 四次均 403 | 保留的是为原路径签发的签名，因此不能用 403 证明 parent 原文件不存在 |
| 独立取得的阳性 source 对象改用用户三个主机 | v13-default 与 v26-dy 均 403；v3-qingtao 为 206、40,087,514 字节，ETag 与声明 file_hash 一致 | qingtao 可分发该已知对象；更换域名没有发现五目标的新原片身份 |
| 同一真实客户端、同一会话的 default 分发对照 | 阳性 206、总长 40,087,514；五目标均 404 | 路线不依赖 original/source 标签，当前五请求未恢复媒体；404 不等于不存在 |

桶关系探针共 **11 次 HTTP 尝试**，每例最多读取 32 字节；没有穷举对象 key 或哈希。阳性另经 source 路线实际检查为 1080×1920、46.249 秒、HEVC+AAC。default 仅读前 16 字节，总长与 source 一致，没有做两个完整下载的哈希比对。

证据：[桶关系探针](../output/research-astar-user-hints/bucket-relation-probes.json)、[真实客户端 default](../output/research-astar-resumed/desktop-client/runtime/default-native-summary.json)、[阳性 source 媒体检查](../output/research-astar-resumed/desktop-client/runtime/positive-current-source-probe.json)。

## 分轨候选和实际修复

真实详情与目录捕获中新增的 **10 个对象**已完成元数据检查：全在 0051/0051-ce，URL 末段为 `media-video-avc1`，回包格式为 DASH，实际为 AVC1 视频单轨并含 `mvex/trex`，可找到音频 file_id 绑定。尺寸、时长和总长与声明相符；没有发现新的 VID。这些结构支持“分轨 representation”的判断，**未提供把 parent 对象映射成上传原文件的证据**。检查共 40 次 HTTP 尝试、读取响应体 19,332 字节，没有下载 mdat 或重算完整媒体哈希。

本轮在 [tools/audit_official_sources.py](../tools/audit_official_sources.py) 修复一个真实遗漏：过去 `url_list` 被当成列表处理并跳过子遍历，而本次回包的音轨采用：

```text
video.bit_rate_audio[].audio_meta.url_list.main_url
video.bit_rate_audio[].audio_meta.url_list.backup_url
```

现在字典形状继续递归，并保留父层 file_id/file_hash 等来源信息。重新审计真实捕获，补回 **6 条音频地址观察**，对应 **3 个音频对象**；与视频形成 **3 组同桶、同 parent、不同后缀关系**，后缀为 `media-audio-und-mp4a` 和 `media-video-avc1`。这修复的是候选发现完整性，没有把分轨音频误作原画视频，也没有改生产原画鉴定规则。

合并台账包含 **484 条地址观察、57 个桶内基础对象**；观察数含跨响应重复及镜像，不等于独立文件数。其 `a` 值同时有 6383 和 392139。音视频共享 parent 证明一组相关 representation，不能自动说明去掉后缀就能取回原上传文件。无损 remux 可以避免再次编码，但不自动恢复作者原始文件的字节身份。

新增 [test_source_audit.py](../tests/test_source_audit.py) 回归验证字典 url_list 的身份继承、字段路径、脱敏输出与“不得自动认定原画”。本轮专项结果为 **10 passed、2 subtests passed**；`git diff --check` 通过，仅有已有 CRLF 提示。此前 155 passed / 152 subtests 是前轮全套结果，本阶段没有重跑。

证据：[含音轨的桶台账](../output/research-astar-user-hints/bucket-ledger-with-audio.json)、[十个新对象的媒体检查](../output/research-astar-resumed/desktop-client/runtime/new-object-probes.json)。

## 开源代码提供了什么

| 项目与当前提交 | 已验证算法 | 可参考部分和边界 |
| --- | --- | --- |
| Evil0ctal main `3c045e11…`，5.1.11；v4 `42784ffc…` | Web detail；main 读取 play_addr/bit_rate/download_addr，同时保留 raw；v4 非 minimal 也透传 | 0051 分轨可以来自原始回包；没有从该桶/分轨反推未知原片 hash/key 的消费者。v4 明确的 DASH 合并分支属于 Bilibili |
| jiji262 `4255c983…` | 按像素和码率取档；original 模式另以实际 URI 请求 `ratio=default` | 原函数对六份真实详情回放，选中 URI 均与本轮 default 实测一致；未遗漏另一 VID。其“原片必须更大才提升”和失败回退普通档不能当作原片验收 |

Evil0ctal 本轮新克隆两个公开分支，并完成两项无网络纯函数回放；jiji 实际提取八个未改函数体回放六份真实响应。未完整运行两个上游应用，未调用第三方在线解析。详细证据见 [Evil0ctal 专项](original-investigation-2026-11-16-evil0ctal-dash.md) 和 [jiji 专项](../output/research-astar-user-hints/jiji/FINDINGS.md)。

## 五目标身份核查

| 作品 | 独立视频身份数 | 相对既有证据新增对象 | default | 冻结后的历史资产比较 |
| --- | ---: | ---: | --- | --- |
| `7708319942491344154` | 4 | 0 | 404 | 无合适参考，未知；四对象均与前轮相同 |
| `7708052871413075238` | 11 | 3 | 404 | 与历史参考资产的 hash、大小、对象键均未匹配 |
| `7707993970332290314` | 12 | 4 | 404 | 与历史参考资产的 hash、大小、对象键均未匹配 |
| `7707964786692083007` | 8 | 3 | 404 | 无合适参考，未知 |
| `7706218040236444937` | 5 | 0 | 404 | 无合适参考，未知 |

候选于 **15:48:01 UTC** 冻结并保存 SHA-256，随后才读取历史参考，整个比较安装 audit hook 禁止联网，**0 次网络请求**；参考值没有加入候选或用于请求。两个参考来自历史外部资产及官方分发验证，不具备独立作者原件逐字节证明。因此“未匹配”只区分本次候选和那些历史资产；另外三目标保持未知。该比较没有使用标签缺失作为拒绝依据，也不能推出原画不存在。

证据：[事后离线比较](../output/research-astar-user-hints/posthoc-identity-comparison.json)。继续研究应沿真实响应中的作品→VID→representation/file_id→对象关系取证，保留未标签候选；目前没有得到可把五目标升级为原画成功的身份链。

## 客户端诊断与恢复边界

真实客户端实验使用临时 ASAR 诊断前缀，不能称“完全未修改客户端”；原业务 UI 和 GET 签名实现仍执行。Node inspector 被禁用，期间关闭两个空预创建 target，并在 REPL 超时后重启研究运行时。UI 显示账号头像/通知，未手动导入凭据；不据此断言匿名或具体会话来源。详见 [客户端实测报告](original-investigation-2026-11-16-astar-resumed.md)。

**23:55:11 +08:00** 清理快照确认研究进程为 0、两个默认 Douyin profile 仍不存在、HKCU Run 无 Douyin 项，ASAR 已恢复且 SHA-256 与原备份完全匹配。备用浏览器研究 Cache index 可独占打开，此项不证明全系统没有 Chrome。证据：[final-cleanup-summary.json](../output/research-astar-resumed/desktop-client/runtime/final-cleanup-summary.json)。机器汇总：[本报告 JSON](original-investigation-2026-11-16-bucket-algorithms.json)。
