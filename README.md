# 抖音原画独立解析程序

输入抖音链接，直接访问平台官方接口，取得 `source/original` 档位并还原播放地址。支持完整 MP4 校验、下载、与本地样本做 SHA-256 对照，以及本地 HTTP API。

**2026-09-20 已实测成功：**作品 `7685326449011608873` 下载得到 **61,314,387 字节**，与用户提供的 `af61965f8683a01d24fc96d2ea98e935.mp4` 的 SHA-256 完全一致。程序没有硬编码该作品的 CDN 地址或目标哈希；对照文件只在下载完成后参与验证。

运行时需要 Python 3.10+、requests、cryptography、Playwright 及其 Chromium。2026-09-21 已确认抖音详情接口开始拒绝缺少 UIFID 的匿名 HTTP 请求，返回 `403 Uifid Not Found`；因此不能继续使用“无需浏览器、直接匿名请求”的旧启动方式。

程序默认用 Playwright 创建全新的匿名 Chromium 上下文，访问抖音首页取得 `ttwid`、`UIFID_TEMP` 后关闭浏览器，再使用对应的 User-Agent 和网页签名请求详情。访客凭据在进程内复用 20 分钟，签名被拒时最多更新一次。整个过程不读取个人浏览器资料或登录 Cookie，不需要手机、模拟器、APK、其他工作区项目或第三方解析 API。

## 快速使用

将项目文件放入 Linux 服务器的 `/opt/software/python`，确保 `run.py` 直接位于该目录内，然后执行：

```bash
cd /opt/software/python
sudo bash deploy/linux/install.sh
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873"
```

安装脚本创建或复用项目的 `.venv`，安装 Python 依赖，并将 Chromium 下载到项目 `.browsers`。仅安装 `requirements.txt` 不会自动下载浏览器。首次初始化访客通常比后续请求慢；Ubuntu 的虚拟环境组件、完整安装步骤和 systemd 自启配置见 [Linux 部署说明](deploy/README.md)。

默认检查实际大小、时长、分辨率以及音视频轨道。需要下载时：

```bash
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873" --download output/my_source.mp4 --json output/my_result.json
```

文件已存在时拒绝覆盖。要重新下载，请换一个输出文件名。将对照附件放到服务器的 `/tmp` 后可执行：

```bash
.venv/bin/python run.py "https://www.douyin.com/video/7685326449011608873" --download output/reference_check.mp4 --reference "/tmp/af61965f8683a01d24fc96d2ea98e935.mp4" --json output/reference_check.json
```

对照一致时退出码为 `0`；解析或下载失败为 `2`；下载成功但与指定对照文件不一致为 `3`。

也可以编辑 **parse_links.py** 顶部的 `LINKS`，再执行 `.venv/bin/python parse_links.py`。结果保存在本项目的 `output` 目录。把 `DOWNLOAD` 改为 `True` 即同时下载。任意链接解析失败时脚本退出码为 `2`，不会再显示“退出代码为 0”。

其他选项：`--url-only` 只打印地址；`--no-probe` 跳过远程媒体校验。默认自动初始化访客，无需手动配置 Cookie。

已有有效访客凭据时，可用 `--cookie-file credentials.json` 指定文件，或在 `parse_links.py` 设置 `COOKIE_FILE`。支持 `name=value; ...` 文本、名称到值的 JSON 对象、浏览器导出的 Cookie JSON 数组，以及包含 `cookies` 和 `user_agent` 的 dtk-parse `credentials.json`；后者会保留凭据配套的 User-Agent。显式指定文件时不自动获取或覆盖其 Cookie；HTTP 服务每次解析重新读取该文件，外部更新后下一次请求即可生效。

## Linux 生产部署：三个 Java 实例共用服务

当前生产方案是在 `172.31.0.3` 的 `/opt/software/python` 目录运行 Python 解析服务，`172.31.0.3`、`172.31.0.4`、`172.31.0.6` 的 Java 实例统一调用 `http://172.31.0.3:8765`。只有 `.3` 安装 Chromium，访客凭据由同一个 Python 进程管理。安装、systemd 自启、防火墙、三实例验证步骤见 [Linux 部署说明](deploy/README.md)，可合并的 Java 配置见 [nika-selfhosted.yaml](deploy/linux/nika-selfhosted.yaml)。

## HTTP 接口

Linux 无 Docker、三个 NiKa 实例共用服务的部署步骤见 [部署说明](deploy/README.md)。执行 `.venv/bin/python package.py` 可在项目父目录生成源码部署包，包含虚拟环境安装脚本和 systemd 配置。

```bash
cd /opt/software/python
.venv/bin/python run.py --serve --port 8765
```

默认监听 `127.0.0.1`，提供 `GET /health`、`POST /parse` 和 `POST /api/v1/resolve`。

直接启动默认最多同时解析 2 条；`--max-concurrent 6` 可配置为 6 条。三实例部署模板已经设为 6，与三个 NiKa 后端各自 2 条并发对应。

```bash
curl --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://127.0.0.1:8765/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7685326449011608873","with_probe":true}'
```

核心响应结构：

```json
{
  "code": 0,
  "msg": "原画解析成功",
  "data": {
    "aweme_id": "7685326449011608873",
    "provider": "douyin-official-source",
    "url": "https://平台CDN/临时播放地址",
    "size_bytes": 61314387,
    "width": 1920,
    "height": 1080,
    "duration_seconds": 175.149,
    "source_selected": true,
    "reference_match": null,
    "video_list": [
      {"quality": "source", "level": "原画", "size": 61314387, "url": "https://平台CDN/临时播放地址"}
    ]
  }
}
```

实际响应还包含备用地址、有效期、编码、官方文件 MD5、媒体探测结果等。`size` 和 `size_bytes` 均以字节计。`source_selected` 表示选择了官方标注的源档；`reference_match=true` 仅在完整下载并与指定对照文件 SHA-256 相同时设置。

NiKa 已新增独立的 `selfhosted` 渠道，页面名称为“自建原画（抖音）”，与 Snapany、muzzz 并列。默认由 Java 后端访问 `http://127.0.0.1:8765/parse`，支持排队限流、在线检查和原画媒体校验。需要同时发布修改后的 NiKa 后端与 NiKa-Admin 前端，再在任务中心保存渠道。部署配置和启用步骤见 [部署说明](deploy/README.md)。HTTP 示例服务不自带公网鉴权，跨机器部署时使用后端可达的内网地址。

## 核心算法与已有项目的区别

1. 提取作品 ID，支持视频链接、`modal_id`、分享文案和短链。
2. 初始化或复用匿名访客凭据，计算 `x-secsdk-web-signature`，请求官方 Web 详情，使用 `aid=392139` 取得非空 `video_model`。普通 `aid=6383` 的 `bit_rate` 只用于此前的转码档对比，不作为本程序的原画结果。
3. 从 `video_model.fallback_api` 读取平台签发的 `/video/fplay/1/{签名}/{video_id}` 路径。保留路径签名，将查询设置为 `aid=392139&stream_type=source`。
4. 校验响应的作品资源 ID，筛选 `quality=original/source` 且为完整 MP4 的候选。
5. 还原播放地址。本轮格式为 Base64 后的 `a8 00 01 00` 头部加 AES-CBC 密文；响应提供 32 字节 `key_seed`。派生方式为 `SHA512(SHA512(seed) + 固定64字节常量)`，前 16 字节作为 AES key，接下来 16 字节作为 IV；按 PKCS#7 去填充得到 URL。代码在 `original_parser/codec.py`。普通 URL、普通 Base64 URL 也支持。
6. 用 Range 请求核对真实大小并读取 MP4 moov，确认视频、音频、时长和分辨率。支持 moov 位于文件尾部；不用下载整个视频即可完成常规解析校验。
7. 下载时核对文件大小和官方 MD5；可再与本地参考文件做 SHA-256 比较。地址过期或全部镜像下载失败会重新解析一次。

链接提取思路参考 `douyinVd`，网页签名公式参考 `dtk/signing/native/websign.py`，匿名访客初始化参考 `dtk-parse`，档位与音轨校验吸收现有项目的经验。关键新增是 **fplay 的 source 流选择 + 播放地址还原**。已有 NiKa 第三方客户端只包含调用第三方服务的鉴权与选档逻辑，没有其内部取址算法。

本次结果推翻了此前针对这些样本的“只能经 App 链路取得原画”的判断：实际可以由 Python 直接访问官方接口获得相同源文件。它不是改大 `br` 参数，也不是把 720p/1080p 网页文件重新编码变大。

## 验证与范围

2026-09-20 的完整下载与哈希对照详见 `实测报告.md`：目标视频已使用独立 ffmpeg 检查音视频解码，另外三条视频完成取址及远程媒体校验。该历史记录中的匿名 HTTP 访问条件现已变化。

2026-09-21 使用新建匿名访客及网页签名重新请求官方接口，已取得以下原画并完成远程媒体校验；此处记录取址结果，不表示本轮重新完成了所有完整下载或目标 Linux 部署检查。

| 作品 ID | 大小（字节） | 分辨率 | 时长（秒） |
| --- | ---: | --- | ---: |
| `7685326449011608873` | 61,314,387 | 1920 × 1080 | 175.149 |
| `7659627743507778842` | 232,472,151 | 720 × 1280 | 456.622 |

离线测试需使用包含 `tests` 目录的完整源码；生产部署包不包含测试文件。在完整源码位于 `/opt/software/python` 时执行：

```bash
cd /opt/software/python
.venv/bin/python -m unittest discover -s tests -v
```

已有离线测试覆盖官方地址编码样本、未知格式、身份不一致、普通档拒绝、无声音视频拒绝、备用地址、尾部 moov、截断下载、覆盖保护和过期地址重取。安装后的实际环境仍需调用 `/parse` 验证；`/health` 只检查服务进程在线。

平台接口未公开承诺兼容性，未来可能变更签名、返回格式或访问条件。无法取得原画时程序明确报错，不把网页转码档改名为原画。当前结论是“取得与给定第三方样本逐字节相同的文件”；没有作者上传前的源文件，不能再推断这是未经平台任何处理的上传原文件。
