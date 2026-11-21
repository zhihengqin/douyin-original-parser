# 抖音原画解析器

输入抖音作品链接、分享文案或作品 ID，获取有原画来源依据、且同一 MP4 中同时含有音视频的文件。只找到普通播放档时，解析失败，不输出媒体链接。要确认与作者上传的文件逐字节一致，需要用上传原件做对照。

## 目前只能获取个别，无法获取全部视频的原画信息！！！！！！！！！！！！！！！！！！ 

## 快速使用

需要 Python 3.10+ 和 Playwright 的 Chromium。以下命令在项目根目录运行。Windows PowerShell 首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.browsers"
python -m playwright install chromium
```

Linux 安装与系统依赖见 [Linux 部署说明](deploy/README.md)。安装后运行：

```shell
python run.py "https://www.douyin.com/video/7707954213745085746"
```

将链接换成自己的作品链接。通过来源、文件大小、音视频轨道、时长和分辨率校验后，终端只输出原画临时地址；没有符合条件的文件时，标准输出为空，错误写到标准错误。

## 下载与批量处理

| 要做什么 | 在项目根目录运行 |
| --- | --- |
| 下载视频，并保存包含来源、媒体信息和 SHA-256 的结果 | `python run.py 7707954213745085746 --download output/video.mp4 --json output/result.json` |
| 下载后与本地原件比对 | `python run.py 7707954213745085746 --download output/compare.mp4 --reference upload.mp4` |
| 一次解析多个作品 | `python parse_links.py 7707954213745085746 7701401474567343403` |

下载成功只输出本地 MP4 路径，不覆盖已有视频。

批量命令每成功一个作品输出一行地址，不生成逐条 JSON 或待查数据库。单作品命令的退出码为：`0` 成功，`2` 解析或下载失败，`3` 文件已下载但与指定对照不一致。

## 怎样判断是不是原画

需要查看依据时，用 `--json` 显式保存结果，读取其中的 `data.source_evidence`：

| 来源 | 可以确认的事实 |
| --- | --- |
| `official_quality` | 平台目录明确标为 `original` 或 `source`；默认还会核对实际媒体。 |
| `official_play_hash` | 按已核验的文件身份从平台取回，可以恢复已知文件；该标记本身不证明这次仅凭链接首次发现了它。 |

`source_unavailable` 表示本次没有找到符合条件的原画。文件大小和分辨率本身不能证明来源。如果手中有作者的上传文件，用 `--reference` 核对实际下载文件的大小和 SHA-256。

### 用一个作品链接取回已归档的授权母版

对自己的作品，可以在发布后把作品链接和上传的原文件登记到本地。以下命令只操作本地归档，替换示例作品 ID 和文件路径即可：

```shell
python -m original_parser.masters --archive masters add "https://www.douyin.com/video/7707954213745085746" upload.mp4
python -m original_parser.masters --archive masters fetch "https://www.douyin.com/video/7707954213745085746" --output output/master.mp4
```

取回时核对大小和 SHA-256。没有登记的作品无法从这里取回；归档时请确保链接和文件属于同一作品。

## HTTP 接口

`python run.py --serve` 启动本地服务，默认监听 `127.0.0.1:8765`。

| 接口 | 用途 |
| --- | --- |
| `GET /health` | 检查服务和队列状态，不请求上游。 |
| `POST /parse`（也可用 `/api/v1/resolve`） | 发送 JSON，如 `{"url":"https://www.douyin.com/video/7707954213745085746"}`，默认执行媒体校验。 |

HTTP 成功时 `data.url` 是已校验的单文件原画临时地址；失败时不返回媒体地址。需要保留完整解析与校验结果时，使用 CLI 的 `--json`。

## 部署与维护

<a id="自建原画专项复查2026-11-06尚未恢复缺失原画"></a>

- 服务器安装、升级与 systemd：[Linux 部署](deploy/README.md)；排队、缓存与失败冷却：[请求保护](deploy/REQUEST_PROTECTION.md)。
- 开发检查：`python -m original_parser.check_runtime` 检查依赖；`python -m unittest discover -s tests` 运行测试。
- 更多选项：`python run.py --help`；历史验证和调查材料见 [文档索引](docs/README.md)，辅助脚本见 [工具说明](tools/README.md)。
