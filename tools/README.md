# 诊断工具

解析一个作品或下载文件，直接看[项目使用说明](../README.md)。需要解释某次解析结果时，从下表选择工具。示例命令均在项目根目录运行。

| 遇到的问题 | 用什么检查 |
| --- | --- |
| 刚安装或升级，想确认依赖是否齐全 | `python -m original_parser.check_runtime` 会在本地检查运行环境。 |
| 手头已有详情或播放目录 JSON，想知道里面有没有匹配的媒体 | [audit_saved_media_catalogs.py](audit_saved_media_catalogs.py) 离线核对作品 ID、视频 ID、目录标记与预期字节数。参数见脚本的 `--help`。 |
| 同一作品在匿名和登录时的结果不同 | [compare_original_sessions.py](compare_original_sessions.py) 对照两个会话；Windows 可用 [compare_original_sessions.cmd](../compare_original_sessions.cmd) 启动。 |

## 报告与本地数据

历史脚本常使用固定作品、当时的客户端版本或特定实验条件；重现报告前，先从[文档索引](../docs/README.md)确认它测的是什么。部分第三方工具可能产生费用。

本地凭据、原始响应、含临时媒体地址的报告请留在本地。`original_metadata.json` 是解析器使用的媒体身份登记；用已有登记找回文件，与只输入作品链接首次发现原画，是两种不同的结果。
