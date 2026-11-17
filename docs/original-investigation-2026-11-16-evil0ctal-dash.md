# Evil0ctal 当前源码：0051 分轨地址、原始回包与原画身份

本轮重新从 GitHub 获取公开源码并核对远端分支，而非仅沿用旧记录。**该项目能够保留接口返回的分轨地址，这个现象与“存在从分轨对象反推出未知原画对象的算法”不同。** 当前 main 和 v4 的抖音路径均没有找到后一种算法；用户所述 0051 地址可以通过原始回包透传出现。具体用户样本的接口回包与桶对象关联由主任务另行实测，本报告不把源码推断当作该样本的网络结果。

**原画不带 `original` / `source` 标签是需要保留的可能性。** 缺少标签只能说明尚缺这类来源证据，不能据此排除原画；同样，0051 桶、分轨格式、最高码率或不带水印也不能单独确认原画。应保留这些候选，继续核对来源关系与媒体内容。

## 固定版本和范围

| 分支 | 本次远端提交 | 提交时间 | 本次审查 |
| --- | --- | --- | --- |
| main，版本 5.1.11 | `3c045e11aecd58ab076562f1246931b9dd5d909b` | 2026-11-09 | detail 参数/签名上下文、parser、raw 透传、下载计划和 Go 下载器 |
| v4 | `42784ffc83a72a516bfe952153ad7e2a3998d16c` | 2025-10-12 | 原始 API、hybrid minimal/非 minimal、抖音与 Bilibili 下载分支 |

两个全新浅克隆位于 `output/research-astar-user-hints/evil0ctal/`，上游跟踪文件未修改。本分支没有请求抖音目标接口或媒体，没有调用第三方解析服务，没有使用外部原片 catalog、已知原片哈希作为发现输入，也没有猜测哈希。两项无网络合成回放执行了未修改的上游 parser/planner；不等于部署或完整运行上游应用。

机器证据：[脱敏审查 JSON](original-investigation-2026-11-16-evil0ctal-dash.json)。带有界源码片段及文件哈希的证据保存在 `output/research-astar-user-hints/evil0ctal/source-audit.json`，合成回放见 `synthetic-parser-replay.json`。

## main：实际详情请求到媒体下载

1. [端点绑定](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/endpoints.py#L275) 使用官方 `/aweme/v1/web/aweme/detail/`。业务参数为 `aweme_id`，公共 query 包括 `device_platform=webapp`、`aid=6383`、`channel=channel_pc_web`、`pc_client_type=1`、`version_code=290100` 和浏览器指标，见 [params.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/params.py#L104)。没有另一个“0051 原画接口”参数。
2. 浏览器指标来自所选身份的 UA 和 fingerprint；签名层取同一身份的 session 参数，附加 A-Bogus/X-Bogus 及可用的访客 web signature，见 [signer.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/signing/native/signer.py#L185)。这些机制服务于请求被接受，不是媒体文件哈希或对象 key 的推导。
3. [Douyin parser](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/parser.py#L306) 的视频取址是 `video.play_addr` → `video.bit_rate[].play_addr` → `video.download_addr`。最后一项在该项目中标为带水印回退。它不依靠 `original` / `source` 标签取这些地址。
4. [_stream](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/parser.py#L224) 只归一化 URL 列表、尺寸、格式、大小、水印和码率等字段；其 [VideoStream 模型](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/models/content.py#L40) 没有文件身份、DASH 配对或 source provenance 字段。
5. [follow_up](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/adapter.py#L64) 直接返回 None；此调用链没有拿到详情后再请求 fplay/源文件目录的步骤。
6. [下载计划](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/media/plan.py#L178) 保留 parser 顺序，并把多个码率档扁平化为同一个视频条目的回退 mirrors；[Go 下载器](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/docker/downloader/download.go#L143) 返回第一个下载成功者。它不比较各档是否为同一份字节，也不在此处识别原片或配对音视频轨道。下载完成后的 SHA-256 是所下载文件的摘要，不是事先推导未知源文件身份。

最关键的保留路径在 [parser.py 的 raw=detail.raw()](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/platforms/douyin/parser.py#L408)。[include_raw 序列化开关](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/3c045e11aecd58ab076562f1246931b9dd5d909b/src/dtk/services/fetch.py#L950) 可以把未建模字段一起返回。因此官方回包中的 `video_model`、分轨地址或其它未知字段，可能在 raw 里完整存在，而没有进入标准下载计划。这是值得借鉴的保留策略。

## v4：抖音原始透传与音视频合并的区别

[fetch_one_video](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/douyin/web/web_crawler.py#L88) 请求同一 Web detail 端点，以配置中的请求身份配套 A-Bogus；该处清空 msToken 字段后发请求，直接返回 JSON。[API handler](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/app/api/endpoints/douyin_web.py#L37) 再把 JSON 放入自己的响应包装，不重新生成媒体对象。

[hybrid 非 minimal 模式](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/hybrid/hybrid_crawler.py#L69) 直接返回 aweme detail；因此也可能原样暴露分轨信息。其 [Douyin minimal 模式](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/hybrid/hybrid_crawler.py#L166) 仅进行两类操作：

- 从 `video.play_addr.url_list[0]` 选择 HQ 地址，并把 `playwm` 字符串换成 `play`。
- 将接口已有的 `video.play_addr.uri` 放入 `video_id` query，构造官方 play 路由，`ratio=1080p`、`line=0`。这不是原片 file_id/MD5 的推导，未补出未知桶对象。

仓库确有明确的 `dash.video`、`dash.audio` 选择和音视频合并代码，但 [hybrid 入口的条件](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/hybrid/hybrid_crawler.py#L254) 是 `platform == 'bilibili'`，[下载合并分支](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/app/api/endpoints/download.py#L192) 也是这个条件。不能把这部分实现解释成抖音的 0051 原画反推路径。

## 标识与对象的映射究竟发生在哪里

| 标识/字段 | 当前源码行为 | 能否据此获得未知原画对象 |
| --- | --- | --- |
| `aweme_id` | 请求详情的作品 ID | 只能由接口返回后续映射，ID 本身没有公开的对象推导步骤 |
| `play_addr.uri` | v4 直接放入官方 play 的 `video_id` 参数；main 未单独建模 | 可以追返回地址，不能把 VID 当成原片 MD5 |
| `file_id` / `file_hash` | main 视频归一化不读取；若 upstream 有值，可保留于 raw | 应按具体响应来源验证，源码没有从 VID 计算未知值 |
| 媒体 `meta` / `token` | 没有用于 Douyin 原画对象推导的消费者；不能与请求 msToken 混同 | 只能分析实际返回的数据结构，不能假定含源文件地址或哈希 |
| `tos-cn-v-0051` | 所查 Douyin/parser/planner/downloader 源码没有桶常量、桶替换或对象 key 生成 | 能在回包 URL 中出现，不提供同桶所有文件或源对象映射 |
| 下载 SHA-256 | 读取视频字节后计算 | 可校验已取得文件，不能反向发现尚未知文件 |

搜索证据覆盖 main 的 Douyin、media 和 Go downloader 目录，以及 v4 的 Douyin crawler；结合上述实际消费者，六个目标词 `0051`、`video_model`、`dash_sep`、`audio_list`、`file_id`、`file_hash` 在所列具体源码范围内均无命中。跨平台 hybrid 的 DASH 消费者已另行查明条件。这个范围不代表审计了所有历史分支或抖音全部服务。

## 无网络合成回放

使用上游合成 fixture，执行未修改的 main `parse_content` 和 `plan.build`：

| 输入变化 | 实际归一化/下载计划 | raw |
| --- | --- | --- |
| 正常 play_addr 旁增加包含视频/音频 URL 的 video_model | 只计划原 play_addr；嵌入分轨 URL 未进入计划 | video_model 和 uri/file_hash/meta/token 原样保留 |
| 将无 original/source 标签的分轨形状 URL 放进 play_addr，另放音频列表 | 计划一个 video 条目，包含该 URL；没有音频条目或配对合并 | 附加字段仍保留 |

两项断言均通过。测试地址未发请求；它证明代码如何处理字段，不证明平台真实回包采用合成的 schema，也没有验证该地址的媒体字节。运行环境为 Python 3.14.6、隔离依赖 Pydantic 2.14.3；上游声明 Python <3.14，因此这里仅记录已经成功执行的纯函数，不声称完整上游应用兼容此版本。

## 对算法改进和下一步实验的含义

可移植的重点是**保留来源和未建模字段**。取得真实详情后，保存每个候选的 JSON 路径、所属作品 ID、VID、representation/file_id、已返回的 hash、桶和对象 key；受长度/深度约束地解开 JSON 字符串及 Base64 model，再与已建模 play_addr 对照。字段缺失记为未知，不能用其它文件的哈希填补，也不能因标准 parser 未读而忽略。

DASH 视频轨、音频轨和完整 MP4 应保持各自身份。不同编码/码率档不是同字节镜像；先依据同一次响应内的 representation 关系及实际轨道、时长、时间基配对，再决定是否可无损重封装。`-c copy` 能避免再编码，却不能自动证明产物就是作者上传原文件；原上传本身也可能没有音频，不能仅凭“缺音轨”一项判死，必须结合实际封装和来源证据。

对于未标 `original` / `source` 的候选，应继续验证容器、编码、分辨率、帧数/时长、轨道组成、实际长度、对象身份和可得的官方来源映射。**标签缺失不应成为丢弃候选的唯一条件；桶命中也不应成为提升为原画的唯一条件。** 如果官方返回元数据可以将某分轨明确关联到源 representation，才继续验证那条具体映射；若只有分轨对象 key，没有源映射，不能通过改桶名、删除 `media-video-*` 后缀或猜测 MD5 来声称恢复原画。

主任务接下来的桶关联实测，应记录用户样本的真实字段路径及 `work → VID → representation → bucket/object` 链，并保留所有未标签候选。这会直接检验“源数据仍存在，但原画标签或包装改变”的假设，而不依赖仓库的 HQ 命名。
