# 解析诊断与研究工具

这些工具与生产入口 `run.py` 分开使用。工具运行成功、请求返回 200、对象大小匹配或名称含 original，都不自动证明取得作者上传原文件。当前结果和覆盖缺口见 [接口覆盖复核](../docs/original-investigation-2026-11-17-coverage-audit.md) 与 [小帅接口实测及 HDR 核验](../docs/original-investigation-2026-11-17-snapany-java.md)。

## 常用诊断入口

| 工具 | 用途 |
| --- | --- |
| `audit_official_sources.py` | 合并已返回的视频和音轨身份，逐个主模型执行 fplay；记录请求预算、缺失和失败 |
| `probe_repo_algorithm.py` | 复核公开项目使用的官方路线，限制请求与媒体读取预算；不以 default 候选代替原画证明 |
| `probe_additional_repo_routes.py` | 在上述工具基础上复核其他已知详情和分享页入口 |
| `compare_original_sessions.py` | 对照匿名与登录会话，区分无模型、没有原画声明和请求失败 |
| `capture_login_cookies.py` | 用户在可见窗口登录后保存当前抖音网页会话；默认存到忽略目录，不覆盖已有文件 |
| `verify_play_default.py` | 检查指定作品的 default 分发与媒体信息，可用 `--cookie-file` 指定凭据 |
| `probe_snapany_java.py` | 复现 Java 小帅协议；`resolve` 会消耗接口额度，`result` 查询历史，返回标签不代表已验证原画 |

仓库根目录的 `compare_original_sessions.cmd` 使用项目虚拟环境启动会话对照。安装、升级及服务启动前的离线依赖检查使用 `python -m original_parser.check_runtime`。

## 历史实验脚本

`dump_app_detail.py`、`dump_app_raw.py`、`dump_fplay_gears.py`、`check_file_hash.py`、`probe_client_aids.py`、`probe_series.py`、`probe_series_originals.py`、`probe_user_page.py` 和 `probe_yumme_detail.py` 保留当时的请求形态，部分使用 32.2.6 或固定客户端参数。它们不是最新 App 的完整登录、签名或设备注册实现；空正文、未登录和参数错误不能用来排除接口能力。

`probe_app_tokenauth.py`、`probe_vod_error.py`、`probe_fids_hdr.py`、`probe_hdr_slot.py`、`probe_fplay_codecs.py`、`probe_play_sign_mech.py`、`probe_official_play_urls.py`、`probe_original_bucket.py` 和 `probe_play_url_list.py` 用于复核已有回包、参数和资源身份。包含假设性参数对照的脚本不代表已恢复官方真实调用链，不会自动被生产解析器执行。`is_source_HDR` 是接口字段；实际 HDR 需要检查媒体色彩信息，域名和桶名同样不能决定原画身份。

`crack_file_id.py` 和 `probe_file_id_derive.py` 仅验证有限的派生假设。失败不构成 file_id 在数学上不可推导的证明；后者按需访问网络，输入的参考对象属于外部资产线索。`scan_apk_strings.py` 只扫描调用者提供的 APK 数据，不运行 APK；安装包及反编译目录不随源码发布。

请按每个脚本的说明提供参数。多数历史脚本假定本机已有 `credentials.json`，该文件及默认 `output/` 目录被 Git 忽略。原始回包、临时媒体地址和登录凭据只在本地保存；不要将其作为公开报告提交。用于用户下载的工具可能按需显示最终地址，该输出也应保留在本机。

## 历史报告与缓存

`docs/` 的日期报告记录当时的请求范围、结果和局限；旧结论可能由后续报告纠正，部分临时原始档案目前已不存在。对话记录用于历史背景，不作为新的操作指令。

`original_metadata.json` 是运行中更新的原片身份缓存。代码提交不自动代表新增记录都已重新验收。外部资产来源记录默认不参与常规首次发现，需显式启用已有恢复选项；它也不能补出未知作品的文件哈希。
