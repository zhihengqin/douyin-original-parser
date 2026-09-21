# Linux 无 Docker：三个 NiKa 实例共用一个原画解析服务

只在其中一台服务器运行 Python 解析服务，三台 NiKa 后端统一访问它的内网 IP。以下以解析服务器内网 IP `10.0.0.11`、安装目录 `/opt/douyin-original-parser` 为例，IP 必须改成实际值。

## 1. 上传和解压

把 `douyin-original-parser-deploy.tar.gz` 上传到选定服务器，例如 `/tmp`。这个包包含源码、依赖清单和服务启动文件；服务器需要 Python 3.10+。安装时需要访问 Python 包仓库、Playwright 浏览器下载站和发行版软件源；解析时需要访问抖音官方页面、接口及视频 CDN。

当前详情接口要求 UIFID 访客标识。程序通过无界面的 Chromium 新建匿名访客，随后用 Python 请求原画接口；不需要服务器桌面、登录抖音或个人浏览器资料。源码压缩包仍较小，Chromium 在服务器安装时单独下载，占用明显大于源码包，不能只传 Windows `.venv` 到 Linux。

```bash
sudo tar -xzf /tmp/douyin-original-parser-deploy.tar.gz -C /opt
cd /opt/douyin-original-parser
python3 --version
sudo bash deploy/linux/install.sh
```

压缩包自身已带 `douyin-original-parser/` 顶层目录，不要再解压到同名子目录中。ZIP 备份包可用 `sudo unzip /tmp/douyin-original-parser-deploy.zip -d /opt` 解压。

Ubuntu 22.04+ / Debian 12+ 如果缺少 Python 或 venv，可先执行：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ca-certificates curl
```

Linux 安装脚本使用 Playwright 的 `--with-deps` 安装 Chromium 系统依赖，需要 root / sudo 权限；自动安装面向 Playwright 当前支持的 Debian / Ubuntu 版本和 CPU 架构。其他发行版不能仅凭 Python 版本判断兼容，需按 Playwright 支持范围准备浏览器及共享库。若较新的 Python 使用单独命令名，例如 `python3.12`，安装时指定：

```bash
sudo env PYTHON_BIN=python3.12 bash deploy/linux/install.sh
```

安装脚本在项目内创建 `.venv`，安装 `requirements.txt` 后执行 `playwright install --with-deps chromium --no-shell`，将 Chromium 放到项目 `.browsers`。pip 或浏览器安装失败都会停止安装；仅安装 Python 依赖不足以运行默认的访客初始化。

## 2. 注册 systemd，开机自动启动

创建专用运行账户（首次部署执行），安装服务文件并启动：

```bash
id douyin-parser >/dev/null 2>&1 || sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin douyin-parser
sudo install -m 644 deploy/linux/douyin-original-parser.service /etc/systemd/system/douyin-original-parser.service
sudo systemctl daemon-reload
sudo systemctl enable --now douyin-original-parser
sudo systemctl status douyin-original-parser --no-pager
```

服务以 `douyin-parser` 账户运行，异常退出会自动重启。项目目录、`.venv` 和 `.browsers` 必须允许该账户读取和进入；安装脚本已为 `.browsers` 设置读取及必要的执行权限，不需要让该账户拥有源码写权限。访客浏览器使用临时上下文，不需要该账户登录桌面。若服务器的 nologin 路径不同，替换 `--shell` 的路径。

默认监听 `0.0.0.0:8765`。查看日志、重启、停止：

```bash
sudo journalctl -u douyin-original-parser -n 100 --no-pager
sudo journalctl -u douyin-original-parser -f
sudo systemctl restart douyin-original-parser
sudo systemctl stop douyin-original-parser
```

如果先在终端试运行而不注册服务，可执行 `bash deploy/linux/start.sh`；关闭终端会停止。不要同时运行前台进程和 systemd 服务，以免占用同一端口。

默认自动获取匿名访客凭据，在服务进程内复用 20 分钟；平台拒绝签名时最多更新一次。第一次真实解析需要启动 Chromium，通常比后续请求慢。访客初始化仍可能受服务器网络或平台访问限制影响，启动成功并不代表上游一定允许访问。

已有外部维护的访客文件时，可在 systemd 服务的 `[Service]` 中添加 `Environment=COOKIE_FILE=/opt/douyin-original-parser/credentials.json`，再执行 `daemon-reload` 和 `restart`。文件必须允许 `douyin-parser` 读取。支持普通 Cookie 文本 / JSON，以及带 `cookies`、`user_agent` 的 dtk-parse 文件；指定文件后不自动获取或覆盖 Cookie。服务每次解析重新读取文件，后续替换文件无需重启服务；无效或过期凭据需要由维护者更新。

## 3. 三台 NiKa 都填同一个服务地址

示例：

| 实例 | Python 服务 | NiKa 的 base-url |
| --- | --- | --- |
| NiKa-1，内网 IP 10.0.0.11 | 运行 | http://10.0.0.11:8765 |
| NiKa-2 | 不运行 | http://10.0.0.11:8765 |
| NiKa-3 | 不运行 | http://10.0.0.11:8765 |

在 `nika-basic` 的 Nacos / Spring 配置中合并下面节点：

```yaml
nika:
  video-parser:
    selfhosted:
      base-url: http://10.0.0.11:8765
      timeout-ms: 120000
      max-concurrent: 2
      queue-timeout-ms: 1200000
```

`base-url` 不要加 `/parse`，客户端会自动拼接。其他两台机器不能填写 `127.0.0.1`，它只表示各自本机。

如果三个实例读取同一份 Nacos 配置，修改一次，然后重启三个 `nika-basic` 实例；配置独立时分别修改并重启。三个后端都需要包含 `selfhosted` 接入代码，前端发布一次对应的新版本。使用同一业务数据库时，在“抓取任务中心”选择“自建原画（抖音）”并保存一次即可；不同数据库需分别选择。

## 4. 检查内网连通和真实解析

在解析服务器先执行：

```bash
curl --fail http://127.0.0.1:8765/health
```

再在三台 NiKa 服务器上分别执行：

```bash
curl --fail http://10.0.0.11:8765/health
```

应返回 `{"ok":true,"provider":"douyin-official-source"}`。安全组或防火墙只需允许 NiKa 服务器访问 TCP 8765；当前服务没有公网鉴权，使用内网访问。

真实解析检查：

```bash
curl --fail-with-body -X POST http://10.0.0.11:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7685326449011608873","with_probe":true}'
```

成功响应的 `code` 为 0，`data.size_bytes` 对这条已核验视频应为 61,314,387；`data.probe.ok` 为 true。健康检查只证明进程在线，真实解析还会检查 Chromium 能否启动、访客初始化是否成功，以及服务器能否访问抖音。随后在 NiKa 提交一条素材，确认该环境的 TOS 转存和入库。

如果出现浏览器不存在或缺少共享库的错误，重新执行安装脚本并确认 `.browsers` 对服务账户可读。如果出现 `403 Uifid Not Found` 或访客初始化失败，查看服务日志确认正在运行包含访客初始化的新包；使用外部 `COOKIE_FILE` 时还需确认文件包含有效 UIFID 及对应 User-Agent。`parse_links.py` 的解析失败现在会返回退出码 `2`。

## 5. 三实例并发配置

Java 的 `max-concurrent: 2` 是每个后端进程的限制，三个实例合计最多发起 6 个正常解析请求。因此本包的 Linux 启动脚本和 systemd 模板使用 `MAX_CONCURRENT=6`，Python 服务最多同时解析 6 条；直接运行 `python run.py --serve` 的默认值仍为 2。

每个 Java 实例多余的请求在本实例内排队，`queue-timeout-ms` 只控制本地等待，并非跨三实例的全局队列。Python 槽位用尽时仍返回 429，当前 Java 客户端最多重试 5 次、总退避约 15 秒；额外手工请求或后端超时后仍在执行的解析可能占用槽位。

要改服务并发，编辑 `/etc/systemd/system/douyin-original-parser.service` 中的 `Environment=MAX_CONCURRENT=6`，再执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart douyin-original-parser
```

并发数可设 1 到 32。增加并发会增加服务器网络开销和对上游的请求量，需要结合实际成功率调整；本机只验证了并发控制机制，未对抖音进行 6 路并发压力测试。三个实例共享这一台解析服务，解析服务器停止时三台的自建解析都会不可用。

## 6. 后续重新打包

在开发电脑的项目根目录执行：

```powershell
python package.py
```

默认在项目父目录生成 `.tar.gz`、`.zip` 和 `.sha256` 校验文件。也可以用 `python package.py --output-dir 指定目录`。打包采用文件白名单，不包含 `.venv`、`.browsers`、`.git`、`.idea`、缓存、访客凭据、历史视频或解析结果。目标服务器通过安装脚本下载适合自身系统的 Chromium。包内 Linux 脚本使用 LF 换行和可执行权限。

如果服务器以后更换为 Windows，包内也保留了 `deploy/windows/install.ps1` 和 `start.ps1`，需先安装 Python 3.10+；Windows 安装脚本同样将 Chromium 安装到项目 `.browsers`。

## 验证记录（2026-09-21）

本轮修改前的部署检查已确认压缩包解压后可独立启动、健康接口与无效输入处理正常；使用本地替代解析器确认 6 个请求可同时执行、第 7 个返回 429，完成后槽位可再次使用。新增访客初始化后，使用项目 `.venv` 启动 HTTP 服务，`/health` 正常，`/parse` 和 `/api/v1/resolve` 均完成真实视频解析，返回 HTTP 200、`code=0`，大小及音视频轨道校验通过；24 项离线测试通过。当前电脑为 Windows，未在目标 Linux 主机执行 systemd 或 Chromium 系统依赖安装。

本轮最初的匿名 HTTP 请求返回 `403 Uifid Not Found`，已确认需要补充访客身份和网页签名。随后使用新建匿名访客，已取得作品 `7685326449011608873` 的 61,314,387 字节、1920 × 1080、175.149 秒原画，以及作品 `7659627743507778842` 的 232,472,151 字节、720 × 1280、456.622 秒原画，并完成远程媒体校验。这证明当前访问链路可行，但不代替目标服务器的真实解析检查，也不代表本轮已重新完成所有下载哈希对照。
