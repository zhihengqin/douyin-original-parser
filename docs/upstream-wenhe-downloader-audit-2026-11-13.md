# wenhe-cpu/douyin-downloader 源码与目标实测

用户提供：https://github.com/wenhe-cpu/douyin-downloader

固定提交：`a51e631299fbbb553604772bf3e0c415f3342dd8`。

## 结果

2026-11-13 18:42（北京时间），执行该仓库原始签名补丁与其实际使用的yt-dlp选档链路，成功获取7707196543073275177的57,651,328字节视频。完整下载计算得到MD5 `34c1614a212475882eec27f6664552c7`，与本项目已确认normal720档完全一致；不是用户给出的小帅132,665,774字节参考文件。

这是一条有效的普通视频下载路径，但未补上旧素材原片首次发现。本次没有将该方法接入生产，也没有修改原片catalog。

## 实际执行范围

将源码克隆到隔离临时目录并固定提交。requirements.txt不固定yt-dlp版本，按照其保持最新版的要求，在临时deps目录安装当时PyPI提供的`yt-dlp 2026.10.26`，没有改项目虚拟环境依赖。

通过AST提取并执行app.py内未修改的`_install_douyin_signature_patch()`，调用真实`YoutubeDL.extract_info()`，采用仓库下载选择器`best[format_note!*=watermarked]`。最初两目标使用该补丁自身的匿名凭据初始化；未读取个人浏览器Cookie，未运行油猴、剪贴板监听或Flask服务。研究请求的超时和重试有限，媒体下载在选址完成后单独验证。

| 作品ID | 实际详情/选档结果 | 媒体验证 |
| --- | --- | --- |
| 7707196543073275177 | 正确作品和VID；选中h264_720p_1489510-2，标记Direct video | 真实MP4校验通过，720×1282、完整音视频；完整下载57,651,328字节，MD5匹配已有normal |
| 7704677676878925119 | 详情未返回可用aweme_detail，提取失败 | 无新候选；不能写为原片不存在 |

18:44对第二目标另作一次受控凭据对照：使用本项目已保存的匿名访客及其UA，保留仓库签名/详情逻辑不变，仍没有aweme_detail。该对照不使用个人浏览器身份。

770719实际下载SHA-256：`52d0edf2bc9e359c08142743f9c422d9a1ce35d278a7873621458b2131831d22`。其最终对象路径与既有fplay normal完全对应；既有官方file_id为`82ae4218ceaa4193947da577a2a509e6`。原片参考MD5只在取得结果后用于离线比较，没有作为网络请求输入。

## 源码说明

- [app.py:75](https://github.com/wenhe-cpu/douyin-downloader/blob/a51e631299fbbb553604772bf3e0c415f3342dd8/app.py#L75)：兼容补丁添加uifid、timestamp和x-secsdk-web-signature，修复网页详情请求；aid为6383。此签名机制本项目已有。
- [app.py:163](https://github.com/wenhe-cpu/douyin-downloader/blob/a51e631299fbbb553604772bf3e0c415f3342dd8/app.py#L163)：详情取得后直接交给yt-dlp的`_parse_aweme_video_app`，没有独立原片请求。
- [app.py:991](https://github.com/wenhe-cpu/douyin-downloader/blob/a51e631299fbbb553604772bf3e0c415f3342dd8/app.py#L991)：下载选择器排除watermarked标记，再选择best。best是候选格式排序结果，不是原片身份验证。

实际依赖的tiktok.py只枚举play_addr、download_addr、play_addr_h264、play_addr_bytevc1、bit_rate中的地址，不读取video_model/fallback_api/token_auth，也不请求fplay或独立SourceInfo。filesize来自详情data_size；提取器没有file_hash逻辑。本次完整MD5是研究验证计算，不能归功于仓库原片校验。

油猴脚本确实包含页面响应读取，但只用于将当前video.src映射回作品ID。三处下载请求仅传作品URL，指定归档时再传target_author，未把捕获媒体、播放模型、token或Cookie提交给后端。此支线只作静态审计，没有运行监听。

README定位为本地无水印下载工具，没有上传原片或旧素材原画承诺。公开历史两次提交：2026-10-25初始实现，2026-11-13重写README；未发现旧原片修复记录。

## 可复查材料

稳定目录：`C:/Users/EDY/AppData/Local/Temp/douyin-test-7707196543073275177/wenhe-downloader-audit/`。

- `source/`：固定提交；`deps/`：隔离yt-dlp依赖。
- `run-upstream.py`、`live-summary.json`、`live-guest-control-summary.json`：真实详情与选档执行。
- `verify-selected.py`、`selected-media-verification.json`：真实媒体检查及完整文件哈希。
- `frontend-history-findings.md`、`ytdlp-selector-findings.md`：前端及依赖调用链。
- `offline-ytdlp-selector-audit.json`：对较早保存详情的离线对照。旧详情选中21,881,031字节H265转码，与本次新鲜详情选中的57MB不同；该离线结果不能覆盖本次实际下载结论。

完整临时地址、匿名凭据相关响应和库日志仅保存在临时private文件中，不抄入本文或生产配置。
