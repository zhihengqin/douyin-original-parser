# 2026-11-16：DASH、全档容器 VID 与继承资源精确选档

目标仍是只输入作品 ID，首次发现 `7707196543073275177` 和 `7704677676878925119` 的原片。本轮新增 11 次播放目录请求、20 个实际媒体对象的限定元数据读取，**仍没有取得两个目标的原片，没有生产修复**。参考文件对象及哈希没有作为发现请求输入。

## 官方 SDK 的另一种模型格式已实际跑通

41.1.0 的 `X.0AGe.getAPIString()` 在 TTPlayer 支持且 DASH 模式开启时加入 `format_type=dash`，ByteVC1 分支加入 `codec_type=3`；`X.1flM.apiForFetcher` 将这些参数追加到既有时间戳＋MD5＋VID 的 SDK 地址。本轮采用这两个真实参数及已有 SSL/device_type 基础参数，不称为完整 App 重放，也没有把 DataSource 参数搬到 fplay。

先请求阳性，确认 HTTP 200、code 0、status 10、VID 匹配，实际返回 `dynamic_video_list` 和 `dynamic_audio_list`。随后对两个目标各自的当前 VID 和普通 MP4 内嵌 VID 请求一次：

| 输入 | 实际返回 | 原片结果 |
| --- | --- | --- |
| 阳性当前 VID | 4 个 ByteVC1 DASH 视频档和 1 个音频档 | 此 SDK 参数分支没有列出已知 528 MB 原片；仅作为模型格式与身份校准 |
| 770719 当前 VID | 2 个 H264 low DASH 视频档和 1 个音频档 | 无 original/source；不是 132,665,774 字节参考文件 |
| 770719 内嵌 VID | 2 个已有 normal MP4 | 最大仍为 57,651,328 字节 |
| 770467 当前 VID | 2 个 H264 low DASH 视频档和 1 个音频档 | 无 original/source |
| 770467 内嵌 VID | 2 个已有 normal MP4 | 最大仍为 81,999,228 字节 |

五次请求的响应 VID 均与输入相符。`codec_type=3` 并不保证服务端必须返回 ByteVC1，两个目标实际回退为 H264，按实际响应记录。DASH 目录查询没有补出原片；不由此推出其它格式／授权的所有资源都已枚举。

## 旧模型仍能刷新目录，详情过滤与媒体访问需要分别判断

从每个作品自己保存的官方 `video_model.fallback_api` 取得原样 URL，未更改选择器。先校准阳性，再请求两个目标，三者均 HTTP 200、status 10、VID 精确匹配。

两个目标各返回 8 个已知普通 MP4。770467 此前同日普通详情基线为 `series_control_filter`，本轮没有重测普通详情；历史上由该目标自己下发的播放模型在本次仍可返回有效目录。这不恢复缺失原片，也不证明过滤原因；它说明不能把“详情没有作品对象”直接写成媒体资源已经不可访问。

## 补查所有普通档的容器身份

此前两个目标只从最大 normal 的 moov 发现过不同 VID。本轮先以本地已知 normal 文件校准提取器，再按 box 偏移读取实际媒体的 ftyp/moov，跳过 mdat。对已有相同官方 file_hash 的对象复用检查结果；最大 normal 两个文件沿用此前已验证的元数据证据，其余各 7 个 MP4 的元数据本轮补齐。

| 作品 | 两个 normal MP4 的 moov comment | 其余 6 个 low/adapt MP4 的 moov comment | 新取得 DASH 视频／音频的 moov comment |
| --- | --- | --- | --- |
| 770719 | `v02033g10000dbpkhdnog65u9q5nd820` | 当前 `v02033g10000dbqncrvog65l6dmpd7rg` | 当前 VID |
| 770467 | `v02033g10000dbl8qbnog65viomj0nc0` | 当前 `v02033g10000dbm873fog65puos79er0` | 当前 VID |

因此，每个作品的当前目录确实同时包含带两种不同 VID 的文件，而不是所有档位都指向同一容器身份。这个结果与素材复用／重新处理相容，仍不能仅凭 comment 判定具体上传去重或迁移机制。已检查的全部普通档与新分轨没有提供第三 VID。

本轮实际新读 20 个媒体对象，合计 3,655,333 字节元数据、60 次成功 Range 请求；另有两个最大 normal 的历史证据。770467 三个 DASH 主地址最初连接失败，改用同一官方回包给出的 `backup_url_1` 后读取成功，没有将连接失败记成资源缺失。DASH 视频文件经 moov 确认仅有视频轨，音频文件仅有音频轨，不把模型的 `vtype` 字符串单独当作实际容器验证。

## 已把真实继承 VID 用作原片 FID 精确选档

成功原片记录与本轮阳性实际回包都显示，original 的 `file_id` 可等于 VID。因此对“当前作品原画 FID 可能等于其 normal 容器的另一 VID”做一次具体对照：保留各自原 fplay 路径和上下文，使用 `stream_type=source`、原模型的 codec5，将 `force_fids` 精确设为 Base64(实际观察到的 VID)。

阳性以自身 VID 为 FID，返回精确匹配的 528,422,694 字节、1920×1248 HEVC `original`。完成这一校准后，两个目标分别以各自 normal 中的另一 VID 为 FID 请求，均正常返回匹配当前 VID 的 8 个普通档，无 original/source。这项测试不同于先前的 SDK 路线或“以当前 VID 强制选档”，仍未恢复原片。没有修改路径中的已签发 VID，也没有跨作品借用授权。

## 其余授权线索和当前限制

并行核对了官方网页播放器留存脚本、懂车帝 token 签发和目标 metadata 上下文。现有实际 caller 没有提供新的原片 Action；已检查的懂车帝 token 都签 `GetPlayInfo/2019-03-15`，现代云请求中的 `NeedOriginal/GetAll` 不构成匿名旧版签发器已支持它们的证据。目标与阳性的 `strategy_tokens` 差异只进入播放事件和诊断 map，没有发现新的签发或取源消费者。

项目当前 `parse_links.py` 的 `COOKIE_FILE=None`，未找到项目凭据配置文件或相关环境变量；本轮没有获得可做登录态对照的已配置会话。未读取个人浏览器配置，也没有虚构登录状态。

本轮没有新原片候选可接入生产代码。现有实测支持继续把问题限定为原片身份／授权的首次下发缺口，不能宣布算法升级、新旧两接口或特定去重机制已确定。脱敏结构化结果在同目录 `original-investigation-2026-11-16-lineage-evidence.json`。

完整私有响应、容器元数据及可复现研究脚本保存在：

`C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/round8-20261116/`

主要入口为 `probe_sdk_dash.py`、`probe_media_vids.py`、`probe_fplay_media_vids.py`、`probe_fplay_embedded_fid.py`。`sdk-dash/summary.json`、`media-vids/summary.json`、`media-vids/backup-summary.json`、`fplay-media-vids/*.summary.json`、`fplay-embedded-fid/summary.json` 保存实际结果；`web-player/FINDINGS.md`、`dcar-scope/FINDINGS.md` 和 `auth-context/FINDINGS.md` 保存源码核对及其留存限制。
