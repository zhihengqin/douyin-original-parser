# 7704677676878925119 原画取址排查，2026-11-13

## 实际状态

用户指定修复此作品的原画解析。本轮仍未恢复其原画首次取址；没有将普通档、已知其他作品原片或原片身份缓存写成修复，也没有修改生产解析逻辑。目标在当前 `parse_links.py` 中已由用户设置，无需再次更换链接。

本轮取得的新证据是：**目标当前 VID 和其播放文件中保存的另一个 VID，确实共享两份转码对象。** 这为“素材资源复用”提供了直接证据，但没有证明复用发生的具体阶段，也没有恢复原片。

## 继续修复验证：新发现的具体候选均未恢复原画

用户要求继续修复后，本次没有将前一轮的“目录中没有原画”当作调查终点，继续完成以下协议源码和目标实测。最终仍没有可验证有效的生产修复。

### 官方播放授权消费链

从保留的官方32.2.6 APK追到 `VideoInfoFetcher.fetchInfo(url, null, 2)` 和最终 `TTHTTPNetwork.startTask`，确认GetPlayInfoToken以原始查询直接附在 `https://open.bytedanceapi.com?` 后，使用GET，不加Authorization、不补参数。

此前默认 `parse_qs` 会略掉空值，误以为 `X-Amz-NotSignBody` 和 `X-Amz-SignedHeaders` 缺失；`keep_blank_values=True`确认这两个字段实际都存在，所有签名声明字段齐全。因此不能通过补猜测字段修复。

本目标原始token在有效期内按上述形态实际请求，确认发送query与签发query逐字一致。HTTP200但业务错误为 `AccessDenied/100013`，不是媒体成功，也不是缺少GET/POST转换。

### 精选SSR与公开算法精确复现

公开 `parsehub-kmp` 的真实算法是精选移动页面的SSR下发fallback，原样保留查询，仅设 `codec_type=8`，再筛选original。使用源码相同的Mobile UA及 `?app=yumme`：目标返回HTTP200但SSR中的gid、VID、video_model均为空；同会话阳性769530返回正确的作品及模型。目标因此没有可执行的SSR签发fallback，不能将此记成其codec8授权失败。

另对本目标Web详情实际签发的fallback，只改 `codec_type=8` 作一次明确对照。返回code1、status2002、“未授权, 禁止访问”，VID匹配目标，没有媒体列表。此结果与SSR缺模型是不同失败环节。

进一步对同一阳性769530比较Web与SSR：两者fplay主机和完整签名路径完全一致；查询差异是Web有device_id、SSR有version_code=26.1.0，force_fids仅同一集合的顺序不同。两边只改codec_type=8，都返回528,422,694字节的官方original。然后保留目标自己的签名路径、VID和FID集合，按已观察差异去device_id并补version_code=26.1.0，再请求codec8，目标仍返回status2002。因此codec8不是全局失效，也不是单靠模拟这两项SSR参数就能恢复本目标；不据此推断所有资源均需同一授权。

公开ucmao实现的第二候选也被精确复现：完整issued查询去logo/force_fids、codec_type=1、保留原stream_type=normal。目标仅返回已有3个adapt档，没有原画。源码本身没有严格原片验证，因此其返回URL不能等同恢复原画。

### 新签发的原片选择授权

对目标当前VID以及MP4注释VID，分别由官方懂车帝token接口签发授权。实际签发结果确实包含并签名：`stream_type=source`、`codec_type=5`、`definition=original`、`format_type=mp4`、`watermark=unwatermarked`。然后用原始签发查询直接请求官方 `vod.bytedanceapi.com`，没有改签名字段，没有附加历史脚本中的aid/ssl。

两个请求都成功到达VOD并返回各自正确的VideoID，回包是 `Result.Data.PlayInfoList`，不是生产fplay的video_list。完整检查该结构后：当前VID仅2个已有adapt档；注释VID仅2个已有normal档。每个FileHash、FileID、Size均匹配前面已经识别的转码；回包也没有单独SourceInfo或原画元数据。

这项实验排除了“只因Web token未授权，所以没有看到注释VID原画”的简单解释。它没有证明原片物理删除，也不能保证该官方token身份具备原画权限。

### 源码边界及保存位置

32.2.6 APK的fallback分支只追加解码method及可选force_codec；没有发现另一原画选档器。这个静态结论限定于实际检查的APK版本。当前官方网页的player脚本和入口脚本也已下载检查，未找到可恢复目标的原画消费字段。`video_transcode_resource_replace` 在APK中实际用于搜索页JS资源切换，与媒体原片替换无关。

本轮资料保存在同一临时目录中，脱敏摘要包括：

- `open-original-token-summary.json`、`play-auth-protocol-findings.md`；
- `public-audit/FINDINGS.md`、`public-audit/jingxuan-target-summary.json`；
- `ucmao-second-selector-summary.json`、`web-codec8-summary.json`；
- `public-audit/positive-web-vs-ssr-context-summary.json`、`public-audit/positive-codec8-comparison.json`、`target-ssr-context-codec8-summary.json`；
- `dcar-resource-source-summary.json`（签发字段及初步结构）、`dcar-vod-media-summary.json`（正确展开Result.Data后的媒体结论）；
- `new-response-source-field-audit.json`。

本次修复请求仍未完成。没有把失败候选加入生产路径，也没有修改质量判断来返回转码。要形成有效代码修复，仍需发现可从目标链接或合法签发元数据取得原片身份的实际路径；当前公开候选和可见回包尚未提供它。

## 目标基线

- 作品：`7704677676878925119`。
- 发布时间：2026-11-05 21:24:30（Asia/Shanghai）。
- 当前官方 VID：`v02033g10000dbm873fog65puos79er0`。
- 视频时长：266.514 秒。
- 官方 `video_model.version=3`，下发同一现有 fplay 路由。
- 本项目旧会话中对此作品 ID 的精确搜索没有命中，因此没有沿用其他作品的原片身份或参考文件作为它的验收依据。

16:20 的实际生产调用返回 `source_unavailable`。两种生产请求各返回8个普通档：

| 档位 | 大小（字节） | 编码 |
| --- | ---: | --- |
| normal | 81,999,228 | H264 |
| normal | 54,305,669 | H264 |
| low | 48,007,371 | H264 |
| low | 42,831,969 | H264 |
| adapt_lowest | 32,811,564 | ByteVC1 |
| adapt_low | 30,297,915 | H264 |
| adapt | 27,184,562 | ByteVC1 |
| adapt_lower | 23,609,365 | ByteVC1 |

同一匿名会话下，阳性 `7695305664234589459` 通过 source 分支取得528,422,694字节的官方 original，并通过完整音视频的远程媒体检查。故本次目标失败没有表现为全局签名、网络或地址解码失败。

## 本地是否漏解析

目标两个 fplay 回包共32个主/备URL均能由当前算法解码。原始数据里没有 original/source 行；详情内嵌 `video_list[].video_meta` 的8条记录，与上述8个文件身份对应。

递归展开详情的JSON字符串后，未发现另一个播放模型、独立SourceInfo或原片文件身份。`download_addr.data_size` 为81,999,228，与normal720p相同。`token_auth` 是已签发的GetPlayInfo查询，未显示原片选择字段；没有修改其签名范围中的参数并宣称获得新授权。

没有证据表明放宽媒体格式、加密标记、质量标签或模型版本检查能修复这个目标。

## 对真实选档行为的有限对照

在目标自身的同一签发路径上，除了两个生产分支，检查以下四种有代码/响应依据的请求：

| 对照 | 结果 |
| --- | --- |
| 平台下发查询原样请求 | 8个普通档 |
| 10月16日版本的精确旧查询：仅aid=392139、stream_type=source | 2个normal |
| 完整签发上下文，source与force_fids=Base64(original)、codec_type=5组合 | 8个普通档 |
| 完整签发上下文，source并移除force_fids | 8个普通档 |

因此，对这个目标，恢复旧代码的source请求或叠加两种现有选档方式都没有取得原片。

## 从目标文件确认的资源关系

仅对81,999,228字节的normal720p读取顶层box和moov，总计440,141字节，没有下载整个媒体。MP4包含完整avc1/mp4a轨道，时长266.514秒，720×1280。`comment` 明确保存：

```text
vid:v02033g10000dbl8qbnog65viomj0nc0
```

这个注释VID不同于当前详情VID。注释本身不能证明它是原始上传资源，因此接着分别请求两个VID的官方SDK播放信息，并核对实际返回身份。SDK签名算法恢复自此前保存的官方播放器代码；请求签名与原片文件MD5是不同概念。没有猜测新的VID，没有查找其他作品或剧集。

两个请求都返回HTTP200/code0/status10，响应VID各自匹配请求。对应媒体关系如下：

| 字段 | 当前VID资源 | MP4注释VID资源 |
| --- | --- | --- |
| 720p file_id | `57084ed11fd447568e30be1286adb985` | `7679355d7ed84322aaf77abaf28ae7bd` |
| 720p file_hash | `4989d51ed3c41bf39050b9d41a533486` | 相同 |
| 720p size | 81,999,228 | 相同 |
| 720p对象 | `tos-cn-ve-51/o4BNAgX6KF3OlDoRIqEDfufYEMZmg00iACsuwN/` | 相同 |
| 540p file_id | `029b38be9a0a43b89a035abd77d15412` | `533148311fd646fa82a47f45b3ad3c94` |
| 540p file_hash | `d0582380a95138a5540b97abc44f2955` | 相同 |
| 540p size | 54,305,669 | 相同 |
| 540p对象 | `tos-cn-ve-51/oME40zNDIAAfgEjsQqygiYlwCBF0Xg6Doioudf/` | 相同 |

不同资源记录确实指向同一转码对象。这比“两个文件大小相同”或“文件哈希相同”更明确地证明了对象复用。它尚不能单独证明上传去重、用户重发、平台迁移中的哪一项导致此关系。

对这两个实际VID，继续分别带现有original选择器和source选择器作有限SDK对照。均没有取得原画：当前VID的original选择请求返回已有adapt转码，source返回两个normal；注释VID的两个选择器都返回相同的两个normal。没有把SDK对附加参数的接受程度假定为全部支持；仅记录实际返回。

## 证据和限制

原始详情、回包、签名及访客凭据不写入文档。相关脱敏JSON和原始私有数据在本机临时研究目录：

```text
C:/Users/EDY/AppData/Local/Temp/douyin-target-7704677676878925119/
  media-metadata-summary.json
  sdk-embedded-vid-summary.json
  sdk-original-selection-summary.json
  resource-mapping-summary.json
```

早期output目录中的基线与选档文件在本轮检查期间再次变得不可见；本轮未执行删除或移动操作。因而后续短期数据使用上述临时目录，稳定结论保存在本文件。不能将已经不可见的output文件当作仍可用的交付物。

SDK第一次经生产HTTP包装器调用被域名白名单本地拦截，没有发出请求。之后通过独立研究会话对固定官方SDK主机完成上述对照；没有放宽生产域名白名单。读取MP4时一次0字节box体请求返回416，随后跳过空box体，完成440,141字节读取；这不是素材取址失败原因。

本轮没有生产行为修复，不以生产测试通过代替原画恢复。后续若找到原片身份，仍须证明它属于本目标且是原画，再做完整媒体核验并接入通用逻辑。当前两份normal不作为原画结果返回。

## 20:xx后续公开候选复核

新增公开 `douyin-8k-parser` 的 `ratio=default&improve_bitrate=1` 仍使用现有播放分发器，并按 CDN 桶名标记“原画”，没有建立来源文件身份。按上游请求对本目标、`7707196543073275177` 和已验证阳性 `7707561244894580004` 重放均为 HTTP 404；因为阳性也失败，这个请求结果不能单独说明本目标的资源状态。

同一作者授权的开放平台“查询视频来源”API 只返回来源类别，不返回源文件地址或标识。Douyin 32.2.6 APK 的静态审计没有发现公开作品 ID 到原片的独立映射调用。证据和范围见 [公开研究汇总](public-original-research-roundup-2026-11-13.md) 与 [APK 审计](douyin-apk-origin-api-audit-2026-11-13.md)。本目标当前没有可信原片参考文件，fplay 的两组 8 档仍都只有普通转码；本轮没有代码修复，也没有放宽校验返回转码。
