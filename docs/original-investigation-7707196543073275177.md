# 7707196543073275177：小帅参考文件与自建取址对照

日期：2026-11-13，时区 Asia/Shanghai。

## 已确认结果

用户提供小帅版对该作品返回的官方CDN直链。本轮完整下载132,665,774字节，并与自建返回的最大normal完整下载对照：**它们对应同一剪辑，但不是同一文件；小帅参考文件不在当前详情或fplay列举的8个档位中。**

因此，“自建当前没有解析出原画”只能描述自建请求结果，不能解释成平台不存在这份高码率文件，也不能将本样本的小帅结果当作普通档仅改标签。没有调用小帅、Snapany等第三方解析服务；只读取用户提供的官方CDN地址和官方接口。

当前尚未恢复仅由作品链接首次发现该参考文件的能力。参考哈希只用于比较，没有录入可信原片catalog、硬编码生产地址或当作首次取址输入。

## 完整文件与媒体对照

| 项目 | 用户提供的小帅参考 | 自建最大normal |
| --- | --- | --- |
| 字节数 | 132,665,774 | 57,651,328 |
| MD5 | `96e395ae426871e3fc3294755d54308f` | `34c1614a212475882eec27f6664552c7` |
| 存储对象 | `tos-cn-v-0051/oMq8DeoSEA0EB2TDE2AzrAAwANFLbCfo5gtDiE/` | `tos-cn-ve-51/owOagbeGbROAVEEe5PgDi3GV7eQLIBtpCAOF25/` |
| 分辨率 | 720×1282 | 720×1282 |
| 帧率与帧数 | 30fps，9288帧 | 相同 |
| 视频时长 | 309.600000秒 | 相同 |
| 容器时长 | 309.638095秒 | 309.638005秒 |
| 视频编码 | H264 Main@3.2 | H264 High@3.2 |
| 视频码率 | 3,224,628bit/s | 1,416,958bit/s |
| 音频编码 | AAC-LC，44.1kHz，双声道 | 相同格式 |
| 音频码率 | 196,891bit/s | 64,024bit/s |

normal完整文件MD5与官方fplay.file_hash相符。参考完整文件SHA256为 `1e2253bf96b99cb671bc1140bc972e1525fc408981fe11ef10d49dd42bbf0dc5`。

选取5/50/100/150/200/250/300秒的画面作相同时刻比较：人物、动作、字幕、构图对应；SSIM为0.960390至0.975803。45/150/290秒起各8秒音频的相关系数0.998365至0.999431，最佳延迟均0ms。这建立了抽样内容对应关系，不声称两个视频逐帧相同。

上述证据足以证明文件身份、内容关系和编码差异。仅凭这些媒体特征仍不能独立证明参考文件就是上传前未经任何处理的文件；没有将目录桶名、大小或第三方名称当作这种来源证明。参考文件含te_is_reencode=1与Lavf61.1.100标签，这些标签亦不能单独确定处理发生在哪一环。

## 为什么当前程序没有拿到这份文件

17:44实测生产链路：详情正常，原画选择器和source兼容分支各返回相同8个转码，没有original/source行；本地没有该作品的历史原片记录。

完整detail、嵌套video_model和两份fplay经过离线核对：

- 三组(file_id,file_hash)集合相同，各8个。
- 全部32个加密主/备地址能正常解码。
- 递归检查48个JSON字符串、130个Base64值及实际播放URL，未找到参考对象、MD5、SHA256或精确字节数。
- 现有8个对象都与参考对象不同，没有遗漏的第9个原画条目。

新目标的已知选择器对照也完成：原样issued查询仅改codec8返回status2002；source与force original组合返回原8个转码；10月精简source请求返回2个normal。没有因这些对照取得参考文件。

## 目标文件中发现的另一资源标识

当前详情VID为 `v02033g10000dbqncrvog65l6dmpd7rg`。normal文件moov/comment保存 `v02033g10000dbpkhdnog65u9q5nd820`；参考文件moov没有VID。仅检查顶层box与moov，没有从mdat随机字符串猜测资源ID。

基于此前公开实现里codec8确实可返回原画的证据，对这两个实际VID分别请求官方懂车帝token接口签发codec_type=8，同时保留source/original/mp4/unwatermarked上下文。签发结果明确接受并签名codec8；随后使用原始签发查询调用官方VOD，两者均正常返回正确VideoID，却只列2个normal，哈希和大小与当前已有普通档一致。该实验没有使用参考MD5。

两条VID的对应normal file_id不同，但file_hash和大小相同。此处不额外推断两条作品的原发布/重发关系，也不把不同VID直接当作原片路径。

## 本地证据

稳定临时目录：`C:/Users/EDY/AppData/Local/Temp/douyin-test-7707196543073275177/`。

其中包括完整参考文件 `xiaoshuai-reference.mp4`、普通档下载、媒体探测结果及：

- `reference-hash-summary.json`、`transcode-identity-summary.json`；
- `media-comparison-findings.md`、`media-sample-comparison.json`、`media-contact-sheet.jpg`；
- `media-moov-identity.json`、`offline-object-audit-summary.json`；
- `known-selector-summary.json`、`dcar-codec8-summary.json`。

含完整签名地址和token的原始响应仅保存在私有研究文件中。本轮未修改生产解析逻辑，也未将参考文件身份加入original_metadata.json。

## 18:23后补充：实际文件ID、直接分发与旧播放器入口

以下请求均未使用参考文件哈希、对象键或本地原片catalog作为取址输入：

- 将现有fplay的force_fids精确设为Base64(当前VID)，codec5，仍返回已知8个转码。官方SDK静态签名入口对当前VID及MP4内嵌VID采用source、codec5和精确VID选择，亦只返回已有转码。证据：`exact-fid-recovery-summary.json`。
- 详情直接下发的14条下载/播放地址去重后有10条。保持原签名、路径和参数，实际跟随官方分发跳转：两个download_addr均404；其余媒体只有36,153,126字节的normal540p和18,992,672字节的adapt540p。共14次HTTP请求、8次16字节媒体读取，没有新对象。证据：`direct-issued-address-summary.json`。
- 根据固定公开you-get实现构造旧CRC32签名的`ib.365yg.com/video/urls/v/1/toutiao/mp4/`请求，当前及内嵌VID均返回HTTP200、`video_play acl deny`、status2002，没有媒体列表。此路径与SDK的MD5签名路径不同，但未恢复原片。证据：`protocol-new/legacy-crc-target-summary.json`。
- normal720的check_info确为实际MP4头部CRC16，不是原片索引。参考MP4的artwork中发现剪映编辑UUID；官方APK的已核实读取链用于编辑来源和分享信息，尚无该UUID映射到原片取址的依据。证据：`opaque-payload-findings.md`。

独立历史官方Action `GetOriginVideoPlayInfo`确实存在，但需要针对该Action和资源的签名；现有GetPlayInfo token不能代用。本轮没有把这个接口名称或现代NeedOriginal参数当成已具备的调用能力。

## 公开实现补充核查

四个用户指定仓库和主动搜索结果已经汇总至同目录 `public-original-research-roundup-2026-11-13.md`，脱敏实测索引为 `public-original-research-evidence-2026-11-13.json`。

Evil0ctal 的原解析器／下载计划离线回放仍选普通档；jiji262 的 A-Bogus 原片 play 探测实际返回 404。新增 DokiTool-Go 的 api.amemv 详情能返回本作品，但原片分发入口在完整匹配其 GET／Range／UA／Accept 后仍返回 404。新详情列出 10 个码率档，其中新增的 3 个媒体对象均为 low/adapt_low 转码，最大仍为 57,651,328 字节；递归检查没有参考文件的对象、哈希或大小。这个新接口没有补出目标原片映射，本作品的未知原片首次发现仍未恢复。

## 20:xx后续公开候选复核

公开 `douyin-8k-parser` 固定版本（`eb3a1b1ac0e65e380fbcc31fe46918a0b04201a1`）只是在已有 VID 的 `/aweme/v1/play/` 上加 `ratio=default&improve_bitrate=1` 等参数。对本作品、`7704677676878925119` 和阳性 `7707561244894580004` 按上游参数请求均为 HTTP 404；访客 UIFID 和已有网页签名头没有改变结果。阳性同样失败，因此不能把当次 404 当成目标源文件不存在的证明；上游代码也没有提供独立原片文件发现步骤。

官方开放平台的[查询抖音视频来源接口](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/douyin-video-origin/)要求作者授权和 `video.data` 权限，响应只说明来源类别，不含文件身份或媒体地址。32.2.6 APK 审计也没有发现从公开作品 ID 获取上传原片的另一调用链，详见 [APK 审计报告](douyin-apk-origin-api-audit-2026-11-13.md)。

再次运行当前 `parse_links.py`，本作品仍为 `source_unavailable`，返回 8 个转码档且无 `original/source`。小帅参考文件仍只用于离线内容对照，没有加进 catalog。故此作品原画解析尚未修复。
