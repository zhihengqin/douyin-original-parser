# 新一轮官方分发与完整容器身份实测

本轮实时检查了目标 `7708052871413075238`、当前 `parse_links.py` 配置的 `7706218040236444937`、第三个失败目标 `7707964786692083007`，并用 `7707264789998849307` 校准。**三个失败目标仍未首次取得原片。** 新证据纠正了旧对话记录对 file_id/sign 的过强解释，也补齐了这三个作品所有已列完整 MP4 的容器身份检查。

所有发现输入均来自作品 ID、新鲜官方详情／播放目录以及这些目录下发媒体的限定 Range。原片 catalog 和外部参考资产未参与；没有调用第三方解析服务。脱敏机器证据：[astar-routes.json](original-investigation-2026-11-16-astar-routes.json)。其中 `target_repair_verified=false` 明确记录验收结果。

## sign 并非已知转码 FID 的必要门禁

旧 `tools/probe_play_sign_mech.py` 的“无 sign”对照同时删除了 `file_id`，无法区分这两个参数的作用。固定转码 FID 后替换两个有效 hash，也不能证明 VID 形式的原片 FID 具有相同语义。

本轮以严格单变量、只消费实时官方目录身份的请求校准：

| 作品 / 请求 | 实测 |
| --- | --- |
| 770805：已下发转码 FID，不传 sign | HTTP 206，68,568,404 字节，首 16 字节确认 MP4 ftyp |
| 770805：同一转码 FID，全零 sign | HTTP 206，同样 68,568,404 字节 |
| 770726：已下发转码 FID，不传 sign | HTTP 206，120,715,342 字节，MP4 ftyp |
| 770726：同一转码 FID，全零 sign | HTTP 206，同样 120,715,342 字节 |
| 两个作品：file_id=VID，分别不传 sign、全零 sign、已下发转码 hash | 都为 HTTP 404；显式 ratio=default 与省略 ratio 两种均检查 |
| 770726：file_id=VID，sign 使用本轮 source 目录直接下发的原片 hash | HTTP 206，6,932,400,516 字节，MP4 ftyp |

首轮部分成功分发跳转到 `v3-dy-o.zjcdn.com`、`v5-dy-ov-experiment.zjcdn.com`，当前白名单尚未覆盖，因此仅记为白名单拦截。补齐 CDN 支持后重新执行同一请求，得到表中的真实 Range 结果。更新前后的证据分别保留，没有把白名单错误写成平台没有原片。

这组结果否定“sign 是所有播放请求必需门禁”的结论，也说明不能把“必须发现一个另行分配的 32 位原片 FID”当作唯一已知缺口。阳性原片的 file_id 就是 VID。目标的请求为什么没有下发原片身份仍未确定；HTTP 404 不证明文件不存在或已删除。

本组对照只读取 16 字节媒体头和 Range 总长，没有重新下载 6.9 GB 阳性或计算整文件哈希。该阳性的 source 目录标签、大小和 FID 来自本轮新鲜官方响应，未读取历史原片记录。

## 三个失败作品的全部已列 MP4 元数据

对每个作品的原样 fplay 完整 MP4 清单逐项解析 ftyp/moov，按容器偏移跳过 mdat。检查都在既有研究工具的对象／元数据预算内完整结束，无对象省略或元数据失败。

| 作品 | 对象数 | Range 次数 | 实际读取元数据 | 当前 VID | normal 容器内另一 VID |
| --- | ---: | ---: | ---: | --- | --- |
| 7708052871413075238 | 8 | 32 | 2,360,865 字节 | v03033g10000dbs82lnog65ls2l3ol5g | v03033g10000dbqmt9fog65se99jopeg |
| 7706218040236444937 | 5 | 20 | 1,580,821 字节 | v0d033g10000dbovp17og65v1kcfouhg | v0d033g10000dbo46gvog65mgfoqmhbg |
| 7707964786692083007 | 5 | 20 | 680,172 字节 | v28033gi0000dbs329vog65m4ip4vss0 | v28033gi0000dbrcbr7og65lknc94cu0 |

18 个 MP4 均有实际视频和音频轨道。另一个 VID 是从官方下发媒体自身发现的可复现输入；它不单独证明父子关系、去重或迁移机制。

分别请求这些新发现 VID 的 SDK 目录、source 选择和默认档后：

- 770805 的另一 VID 返回相同 45,992,041 / 68,568,404 字节 normal，file_hash 与当前目录相同、FID 不同；default 为 404。当前和另一 VID 的 codec8 都是业务 status 2002；原签发 fplay 用另一 VID 精确 force_fids 后仍为原来的 8 个转码。
- 770621 的另一 VID 返回 72,404,804 字节 H264 normal，以及 19,041,910 / 23,088,989 字节 ByteVC1 normal；default 为 404。后两档是本次补查中多见的低分辨率转码，未被升级为原片；本轮当时没有追加读取这两个对象的容器。**后续状态：**[第二轮](original-investigation-2026-11-16-astar-round2.md)已对两份相同 FID/hash/大小的对象各做 4 次 Range/moov 检查，均只有已知内嵌 VID，没有第三 VID；证据为 `output/research-astar-round2/graph-7706218040236444937.json` 的 `new_media[0:2]`。本条旧边界不再构成未执行的检查任务，也不表示所有未观察资源关系均已枚举。
- 770796 的另一 VID 返回相同 16,418,362 / 24,305,152 字节 normal，default 为 404。

## 当前输入和第三目标的实时端到端检查

本轮明确禁止 catalog 读写，针对两个作品用新鲜详情执行生产 `source_streams()`；均返回 `source_unavailable`。随后独立读取原样 fplay、source fplay、SDK source 和 play 默认档作对照：

| 作品 | 官方详情 | 原样 / source fplay | 当前 VID 的 SDK source | 默认档 |
| --- | --- | --- | --- | --- |
| 当前输入 7706218040236444937 | ID/VID 匹配、有完整 video_model，内嵌 JSON 未发现另一 VID | 都为 5 个转码；最大 72,404,804 字节 | 2 个 ByteVC1 转码 | HTTP 404 |
| 第三目标 7707964786692083007 | ID/VID 匹配、有完整 video_model，内嵌 JSON 未发现另一 VID | 都为 5 个转码；最大 24,305,152 字节 | 2 个 H264 normal | HTTP 404 |

这里的另一 VID 来自后续媒体元数据读取，详情字段自身没有提供它。两个作品均 `is_source_HDR=1`，该标记仅记录上下文，未作为失败原因或原片不可取的判据。

## 可复现范围

研究脚本在忽略目录 `output/research-astar/`：`route_sign_controls.py`、`route_dispatch_semantics.py`、`route_lineage_new_target.py`、`route_lineage_followup.py`、`route_current_targets.py`、`route_current_lineage.py`。`route_publish_evidence.py` 将各份只含状态、主机、作品／媒体身份和大小的报告汇总，并拒绝含完整 URL、Cookie／签名字段的输出。

实验使用仓库已有 `credentials.json` 的会话，不读取个人浏览器资料、不输出 Cookie。研究脚本退出成功表示实验执行完成，不能用作目标修复验收。结果只覆盖实际列出的接口和请求，没有声称已经穷尽全部抖音接口。
