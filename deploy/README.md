# Linux 无 Docker：三个 NiKa 实例共用一个原画解析服务

**当前策略：**只返回经过完整媒体校验的官方原画。官方没有下发 `original/source`，或可信的官方原片分发无法签发时，HTTP 返回 `source_unavailable`（消息包含“获取原画失败”），普通转码档不会作为成功结果返回，也不会缓存。2026-11-06 的“最高可用画质降级”只保留在历史调查记录中，不是当前部署行为。

更新时需要替换 Python 源码并重启解析服务，同时编译发布使用该服务的 NiKa 后端；旧 Java 客户端会拒绝 `source_selected=false` 的普通档。依赖和既有启动参数无需改变，已启用自建渠道的前端无需改动。先升级 NiKa 后端可兼容仍返回原画的旧 Python 服务，再更新 Python。严格原画选档、媒体校验和 HTTP 缓存已经在 Windows 本地联调通过，目标 Linux 是否已更新需按下方命令复查。

更新后用作品 `7706466342664277290` 调用 `/parse`，成功回包只返回 `{"code":0,"msg":"原画解析成功","data":{"url":"..."}}`，应验证 `data.url` 可下载且为约 185,591,975 字节的原片；可信记录来自部署包中的 `original_metadata.json`，服务账户无法写入项目目录时不影响静态记录读取。没有匹配原片记录且官方只返回普通档的作品，例如 `7704212621922159898`，应返回 HTTP 502、`code=source_unavailable`、`data=null`。这些是本地官方接口与 MP4 Range 校验结果，若上游返回发生变化应以新回包及媒体校验为准。

当前主解析节点为 Linux `172.31.0.4`，三个 Java 实例的主调用地址为 `http://172.31.0.4:8765`。安装目录为 `/opt/software/python`，`run.py` 直接位于目录内。只有运行解析服务的节点需要安装 Python、Playwright 和 Chromium，Java 节点无需同步 Cookie。已部署成功的 04 升级步骤见 [请求保护说明](REQUEST_PROTECTION.md)，无需重装依赖。

Python 服务由 systemd 独立管理，Java 发布或重启不应同时停止它。已由服务器截图确认 `.3` 为 Ubuntu 22.04.4 LTS，使用 `/usr/bin/python3`，版本 3.10.12，无需另装一套 Python。可用 `uname -m` 再确认 CPU 架构；浏览器安装仍须与当前 Playwright 支持的架构匹配。其他服务器若使用 CentOS、Rocky、AlmaLinux，不能直接套用这里的 `apt` 或假定 `--with-deps` 可用。

## 1. 上传和解压

以下首次安装与服务管理命令在解析节点 `172.31.0.4` 执行，假定与 03 一样使用 Ubuntu。先补齐 Ubuntu 的虚拟环境组件和下载工具；`python3 -m venv --help` 能显示帮助，不代表创建环境所需的 ensurepip 组件一定已经齐全。

```bash
sudo apt-get update
sudo apt-get install -y python3-venv ca-certificates curl
```

把 `douyin-original-parser-deploy.tar.gz` 上传到选定服务器，例如 `/tmp`。这个包包含源码、依赖清单和服务启动文件；服务器需要 Python 3.10+。安装时需要访问 Python 包仓库、Playwright 浏览器下载站和发行版软件源；解析时需要访问抖音官方页面、接口及视频 CDN。

当前详情接口要求 UIFID 访客标识。程序通过无界面的 Chromium 新建匿名访客，随后用 Python 请求原画接口；不需要服务器桌面、登录抖音或个人浏览器资料。源码压缩包仍较小，Chromium 在服务器安装时单独下载，占用明显大于源码包；虚拟环境须在目标服务器创建，不要搬用其他电脑的 `.venv`。

```bash
sudo mkdir -p /opt/software/python
sudo tar -xzf /tmp/douyin-original-parser-deploy.tar.gz --strip-components=1 -C /opt/software/python
cd /opt/software/python
python3 --version
sudo bash deploy/linux/install.sh
```

压缩包自身已带 `douyin-original-parser/` 顶层目录，上面的 `--strip-components=1` 会去掉这一层。解压后应能看到 `/opt/software/python/run.py` 和 `/opt/software/python/deploy/linux/start.sh`。使用 ZIP 备份包或手动复制时，同样把项目文件夹里面的内容放入 `/opt/software/python`，不要额外套一层项目名目录。虚拟环境和浏览器会安装到该目录下的 `.venv` 与 `.browsers`；如果之前已在其他路径安装，不要搬用旧的 `.venv`，应在新目录重新执行安装脚本。

Linux 安装脚本使用 Playwright 的 `--with-deps` 安装 Chromium 系统依赖，需要 root / sudo 权限；自动安装面向 Playwright 当前支持的 Debian / Ubuntu 版本和 CPU 架构。其他发行版不能仅凭 Python 版本判断兼容，需按 Playwright 支持范围准备浏览器及共享库。若较新的 Python 使用单独命令名，例如 `python3.12`，安装时指定：

```bash
sudo env PYTHON_BIN=python3.12 bash deploy/linux/install.sh
```

安装脚本在项目内创建 `.venv`，安装 `requirements.txt` 后执行 `playwright install --with-deps chromium --no-shell`，将 Chromium 放到项目 `.browsers`。pip 或浏览器安装失败都会停止安装；仅安装 Python 依赖不足以运行默认的访客初始化。

## 2. 注册 systemd，开机自动启动

创建专用运行账户（首次部署执行），安装服务文件并启动：

```bash
id douyin-parser >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /home/douyin-parser --create-home --shell /usr/sbin/nologin douyin-parser
sudo install -d -m 750 -o douyin-parser -g douyin-parser /home/douyin-parser
sudo install -m 644 deploy/linux/douyin-original-parser.service /etc/systemd/system/douyin-original-parser.service
sudo systemctl daemon-reload
sudo systemctl enable douyin-original-parser
sudo systemctl restart douyin-original-parser
sudo systemctl status douyin-original-parser --no-pager
```

服务以 `douyin-parser` 账户运行，异常退出会自动重启。项目目录、`.venv` 和 `.browsers` 必须允许该账户读取和进入；安装脚本已为 `.browsers` 设置读取及必要的执行权限，不需要让该账户拥有源码写权限。访客浏览器使用临时上下文，不需要该账户登录桌面。若服务器的 nologin 路径不同，替换 `--shell` 的路径。

父目录 `/opt/software` 也必须允许该账户进入。如出现权限错误，可用 `sudo -u douyin-parser test -r /opt/software/python/run.py` 和 `sudo -u douyin-parser test -x /opt/software/python/.venv/bin/python` 检查；失败时用 `namei -l /opt/software/python/.venv/bin/python` 定位具体目录，再针对性处理权限，不要递归修改整个 `/opt/software`。上面的 `restart` 同时适用于首次安装及已有服务更换启动目录。

默认监听 `0.0.0.0:8765`。查看日志、重启、停止：

```bash
sudo journalctl -u douyin-original-parser -n 100 --no-pager
sudo journalctl -u douyin-original-parser -f
sudo systemctl restart douyin-original-parser
sudo systemctl stop douyin-original-parser
```

如果先在终端试运行而不注册服务，可执行 `bash deploy/linux/start.sh`；关闭终端会停止。不要同时运行前台进程和 systemd 服务，以免占用同一端口。

默认 HTTP 详情模式自动获取匿名访客凭据，在进程内复用 20 分钟。受保护的服务不会在一个任务内刷新访客重复请求，限制类错误统一累计并触发冷却。browser 模式沿用独立匿名页面获取详情。启动成功不代表平台一定允许访问，配置说明见 [请求保护说明](REQUEST_PROTECTION.md)。

已有外部维护的访客文件时，可在 systemd 服务的 `[Service]` 中添加 `Environment=COOKIE_FILE=/opt/software/python/credentials.json`，再执行 `daemon-reload` 和 `restart`。文件必须允许 `douyin-parser` 读取。支持普通 Cookie 文本 / JSON，以及带 `cookies`、`user_agent` 的 dtk-parse 文件；指定文件后不自动获取或覆盖 Cookie。服务每次解析重新读取文件，后续替换文件无需重启服务；无效或过期凭据需要由维护者更新。

## 3. 三台 NiKa 都填同一个服务地址

三个实例的配置：

| 实例 | Python 服务 | NiKa 的 base-url |
| --- | --- | --- |
| NiKa-1，172.31.0.3 | 不作为主解析服务 | http://172.31.0.4:8765 |
| NiKa-2，172.31.0.4 | 运行，包含 Chromium | http://172.31.0.4:8765 |
| NiKa-3，172.31.0.6 | 可按需另部署备用服务 | http://172.31.0.4:8765 |

在 `nika-basic` 的 Nacos / Spring 配置中合并下面节点：

```yaml
nika:
  video-parser:
    selfhosted:
      base-url: http://172.31.0.4:8765
      timeout-ms: 180000
      max-concurrent: 2
      queue-timeout-ms: 1200000
```

`base-url` 不要加 `/parse`，客户端会自动拼接。其他两台机器不能填写 `127.0.0.1`，它只表示各自本机。

可复制的配置文件为 [linux/nika-selfhosted.yaml](linux/nika-selfhosted.yaml)，请合并到原有配置中，不要覆盖整个业务配置文件。`timeout-ms: 180000` 为浏览器初始化和解析留出等待时间；如果链路中有代理，也需检查代理超时。`queue-timeout-ms` 是各 Java 进程的本地排队时间，不是全局队列。

如果三个实例读取同一份 Nacos 配置，修改一次，然后重启三个 `nika-basic` 实例；配置独立时分别修改并重启。三个后端都需要包含 `selfhosted` 接入代码，前端发布一次对应的新版本。使用同一业务数据库时，在“抓取任务中心”选择“自建原画（抖音）”并保存一次即可；不同数据库需分别选择。

## 4. 检查内网连通和真实解析

在解析服务器先执行：

```bash
curl --fail --connect-timeout 5 --max-time 10 http://127.0.0.1:8765/health
```

再在三台 NiKa 服务器上分别执行：

```bash
curl --fail --connect-timeout 5 --max-time 10 http://172.31.0.4:8765/health
```

应返回 `ok=true`、`provider=douyin-official-source` 以及新增的 `protection` 状态。在 `.4` 的安全组及主机防火墙中，允许来源 `172.31.0.3/32`、`172.31.0.4/32`、`172.31.0.6/32` 访问 TCP 8765。若容器网络做了地址转换，应按 `.4` 实际看到的来源地址放行，并从 Java 容器内验证连通性。当前服务没有公网鉴权，使用内网访问。

若 `.4` 已启用 UFW，可添加下面三条规则；未启用时不要为了这一端口盲目启用或重置防火墙，避免影响生产 SSH 和业务端口。使用其他防火墙时在现有策略中添加同等规则。

```bash
sudo ufw allow from 172.31.0.3 to any port 8765 proto tcp
sudo ufw allow from 172.31.0.4 to any port 8765 proto tcp
sudo ufw allow from 172.31.0.6 to any port 8765 proto tcp
```

真实解析检查：

```bash
curl --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://172.31.0.4:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7685326449011608873","with_probe":true}'
```

成功响应的 `code` 为 0，`data.size_bytes` 对这条已核验视频应为 61,314,387；`data.probe.ok` 为 true。健康检查只证明进程在线，真实解析还会检查 Chromium 能否启动、访客初始化是否成功，以及服务器能否访问抖音。先在 systemd 启动后做一次真实解析预热，再让三个 Java 实例分别完成一条素材的解析、TOS 转存和入库。验收需确认任务实际分别由三个实例处理；Python 能读到 CDN 地址，并不等于 TOS 转存一定成功。

如果出现浏览器不存在或缺少共享库的错误，重新执行安装脚本并确认 `.browsers` 对服务账户可读。如果出现 `403 Uifid Not Found` 或访客初始化失败，查看服务日志确认正在运行包含访客初始化的新包；使用外部 `COOKIE_FILE` 时还需确认文件包含有效 UIFID 及对应 User-Agent。`parse_links.py` 的解析失败现在会返回退出码 `2`。

## 5. 三实例请求保护

Java 的 `max-concurrent: 2` 是每个后端的限制，三个实例合计最多提交 6 个请求。Python 的 `MAX_CONCURRENT=6` 表示同时受理数量，包含等待者；实际访问上游只有一个任务，完成后默认随机间隔 3～6 秒，以实际 `REQUEST_INTERVAL` 配置为准。同作品合并和有效期缓存会减少实际执行次数。

默认成功结果最多缓存 5 分钟，提前 60 秒避开地址到期；累计 3 次限制类失败后冷却 15 分钟，真实解析成功清零。队列满或等待超时返回 HTTP 429；冷却期间无有效缓存返回 HTTP 503，并提供重试时间。参数、升级和验收见 [请求保护说明](REQUEST_PROTECTION.md)。

受理数量可设 1 到 32，提高该值只增加等待者数量，不增加上游并发。三个 Java 共用同一进程时共用保护状态；如果启用另一台备用解析服务，其队列、缓存、计数分别独立。本轮未修改 Java 的备用切换逻辑。

HTTP 模式保留进程内访客缓存，browser 模式仍使用独立匿名页面，两者都受外层控制。状态在内存里，重启会清空；不要频繁重启来跳过冷却。直接 CLI 解析不经过 HTTP 保护，不适合与生产服务并行批量使用。

## 6. 后续重新打包

在项目根目录执行；以下以 `/opt/software/python` 为例：

```bash
cd /opt/software/python
.venv/bin/python package.py --output-dir /tmp/douyin-parser-packages
```

上例在 `/tmp/douyin-parser-packages` 生成 `.tar.gz`、`.zip` 和 `.sha256` 校验文件；省略 `--output-dir` 时默认输出到项目父目录，需确保当前账户对输出目录有写权限。打包采用文件白名单，不包含 `.venv`、`.browsers`、`.git`、`.idea`、缓存、访客凭据、历史视频或解析结果。目标服务器通过安装脚本下载适合自身系统的 Chromium。包内 Linux 脚本使用 LF 换行和可执行权限。

## 验证记录（2026-09-21）

本轮修改前的部署检查已确认压缩包解压后可独立启动、健康接口与无效输入处理正常；使用本地替代解析器确认 6 个请求可同时执行、第 7 个返回 429，完成后槽位可再次使用。新增访客初始化后，使用项目 `.venv` 启动 HTTP 服务，`/health` 正常，`/parse` 和 `/api/v1/resolve` 均完成真实视频解析，返回 HTTP 200、`code=0`，大小及音视频轨道校验通过；24 项离线测试通过。当前电脑为 Windows，未在目标 Linux 主机执行 systemd 或 Chromium 系统依赖安装。

本轮最初的匿名 HTTP 请求返回 `403 Uifid Not Found`，已确认需要补充访客身份和网页签名。随后使用新建匿名访客，已取得作品 `7685326449011608873` 的 61,314,387 字节、1920 × 1080、175.149 秒原画，以及作品 `7659627743507778842` 的 232,472,151 字节、720 × 1280、456.622 秒原画，并完成远程媒体校验。这证明当前访问链路可行，但不代替目标服务器的真实解析检查，也不代表本轮已重新完成所有下载哈希对照。
