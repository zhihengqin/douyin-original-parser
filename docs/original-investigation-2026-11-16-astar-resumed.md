# 2026-11-16 继续研究：请求一致性、SDK 会话与官方桌面客户端

本记录汇总已经取得的实测证据与局限。目标仍是从作品链接独立发现并验证原画文件；最高码率转码、仅有原画字样、外部提供的原画哈希均不能替代这一目标。**官方 Windows 客户端的真实业务 UI 和 GET 桥已完成动态验证，六个作品均取得匹配详情；阳性对照取得官方 source 媒体，五个目标的原画发现仍未修复。** 本记录不宣称遍历了全部接口，也不据本轮结果判断原画不存在。无 `original` / `source` 标签的候选仍需保留并核验身份。

对应脱敏数据：[original-investigation-2026-11-16-astar-resumed.json](original-investigation-2026-11-16-astar-resumed.json)。文中不收录登录凭据、请求签名值、完整请求地址或账号通知内容。以下路径均相对于仓库根目录。

## 1. 原生请求签名输入与实际发送对象

检查了此前保存的四次原生请求：两个业务状态为 0 的样本、两个业务状态为 8 的样本。离线复现经过实际 `native.request`、`Session.send`、`HTTPAdapter.send` 和内存中的 HTTP 序列化；本项没有联网，也没有重新执行签名器。

- 四个样本均只 prepare 一次，签名与 transport 接收同一个 `PreparedRequest`。
- 记录中的签名输入 URL 和请求头均可复现。送至 adapter、HTTP 序列化时，路径、查询、原输入头及七个 SDK 输出头保持一致，序列化仅补充预期的 Host 头。
- SDK 输出头没有覆盖 Cookie、User-Agent 或时间票据等输入头。
- 另一个合成对照在签名过程中修改 CookieJar，已 prepare 的请求仍发送原来的已签名 Cookie 头，没有混入新增项。
- 四个历史样本均为一次签名尝试。请求票据与查询时间相符；SDK 时间相对查询为 1–2 秒，服务端响应时间相对 SDK 时间为 3–4 秒，没有发现失败样本特有的过期差异。

这排除了已检查实现中的“签名后再次 prepare 导致本地字段变化”解释，但离线复现不能追溯捕获历史 TLS 字节，也不能证明服务端已经接受签名、设备身份或登录态。

证据：`output/research-astar-resumed/request-integrity/integrity-report.json`、`audit_integrity.py`。

## 2. 官方 APK 的 SDK 会话写入与四次实测

在主抖音 41.1.0 / 410101 的官方代码中找到可定位的差异：`CookieUtils.getSessionId` 从 Cookie 中选择名称恰好等于 `sessionid` 的值；SDK 初始化的一条受功能/运行状态条件控制的调用链，把该值写入管理器配置，并执行操作号 `33554436` 的 session setter。原研究 harness 获取管理器后只设置设备和安装标识，配置中的 session 槽为空，未调用该 setter。

因此在隔离副本中加入这一实际调用，使用已有刷新会话；没有要求再次登录，没有改生产代码或原 harness。两个处理组均完成本地 SDK 初始化和 setter 调用。历史成功请求也缺少此调用，因此不能预先认定它就是此前状态 0 变成 8 的原因。

本次只向 `/aweme/v1/series/aweme/detail/` 发送四次请求：

| 作品 | 用途 | harness | HTTP | 业务状态 | 响应字节 | 返回匹配作品 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `7698054262056552561` | 历史阳性对照 | 原 baseline | 200 | 8 | 106 | 否 |
| `7698054262056552561` | 历史阳性对照 | 写入 SDK session | 200 | 8 | 106 | 否 |
| `7708319942491344154` | 当前目标 | 原 baseline | 200 | 8 | 106 | 否 |
| `7708319942491344154` | 当前目标 | 写入 SDK session | 200 | 8 | 106 | 否 |

四次实际发送均断言：签名与发送使用同一对象，URL、输入头和签名头未改变，禁止重定向；响应关联的请求也确为签名对象。没有发送媒体请求。这里的“历史阳性”描述该作品曾经的结果，本轮并未建立可用的登录阳性基线。

实验还发生一次**联网前**的本地初始化错误：隔离副本缺少原 harness 使用的外部 license 文件。复制未改动的原文件后，只继续剩余三次 HTTP 请求，没有重复第一条 baseline。恢复时重建了 Session；两个处理组共享新 Session，但两个 baseline 不保证复用同一条原始连接。因此不能称为连接生命周期完全受控的实验，也不能把本地错误算作第五次接口请求。

当前证据只表明：补齐该 SDK session 状态，在这四次实测中没有恢复服务端接受登录的结果；没有足够的作品详情用于判断该轮的原画字段。

证据：`output/research-astar-resumed/request-integrity/FINDINGS.md`、`cookieutils-methods.json`、`harness-build-summary.json`、`session-binding-report.json`。原始请求、响应、签名器输入和 license 保留在私有研究目录，不进入文档。

## 3. 官方 Windows 8.8.0 包与真实静态调用链

从官方站点下载页发现并下载完整 Windows ia32 客户端包，文件名为 `douyin-v8.8.0-win32-ia32-douyin.exe`，大小 **265,324,480 字节**，与下载前声明一致；SHA-256 为 `f05cf9c2f8e1ef24f81f7f9855daf631ac943737f89224d11538d763a2f62037`。安装包 Windows Authenticode 检查为 Valid，签名人为 **Douyin Vision Co., Ltd.**。静态解包提取 1,025 个 payload 文件和三个 ASAR；没有通过运行安装器执行安装。

应用版本为 **8.8.0**，build ID 为 **540056698**。`main.dll` 的内嵌构建标识是 Electron **39.5.1-rs.35.release.pgo.0** / Chromium **142.0.7444.48**。独立 `sscronet.dll` 中的 Chromium 73 标识属于另一网络组件，不能当作主渲染引擎版本；本次未识别出独立 CEF 运行时。这些精确版本来自静态资源和字符串，并非运行时版本 API。

`win32ia32.node` 在 ASAR 中声明 356,352 字节，实际 368,504 字节；差额 12,152 字节恰好是 PE 证书表，起点和文件尾也一致。该文件的 CMS 签名、CMS 内容摘要和 PE Authenticode 摘要均通过离线验证，证书与已验证的官方安装包相同。该模块未重新检查在线撤销或 Windows 信任链，结论不扩展为已验完全部 native 文件。

在 `pages/wallpaper/index.98e9e63f58ca3dd2.js` 中追到真实业务调用，而非仅发现接口常量：

1. 公共 query 为 `device_platform=webapp`、`aid=6383`、`channel=channel_pc_web`，合并当前浏览器指标和业务参数；安全 SDK 也以 aid 6383 初始化。
2. HTTP wrapper 使用 `GET` bridge，传入 `path`、`origin`、`queryParams` 和 `credentials:true`。包装器检查返回的 HTTP 状态后取业务数据；bridge helper 可落到 `window.TTE_ENV.bridge.invoke`。
3. 作品详情消费者使用 `/aweme/v1/web/aweme/detail/` 和 `aweme_id`；壁纸列表消费者使用 `/aweme/v1/web/wallpaper/item/`，带 count、cursor、version 和图文开关等字段。
4. 数据映射读取 `video.play_addr.url_list`，下载描述读取 `video.download_addr.url_list[0]` 及 `video.download_addr.file_hash`。
5. 壁纸下载按钮把该描述交给 `DOWNLOAD_WALLPAPER`。这条已读路径没有展示从 VID 推导原画身份的步骤；下载操作和 GET 的功能不同，静态调用链不等于已执行下载。

这些信息提供了应在真实客户端里验证的 GET 入口，但未证明 desktop 会返回与浏览器不同的原画字段。设置页只证明存在下载设置和路径读取；暴露方法名中的 `downloadURL` 等不能单独视为已验证原画接口。本地 player 页使用本地文件路径，也不是新增线上取原画入口。

主进程 `index.js`、`preload.js` 和多个 worker 是 native `.link(...)` 短包装；完整 handler 尚未从可读 JavaScript 恢复。193 个可读 route 字符串只是静态清单，**不代表 193 个接口都已成功执行或已遍历全部 API**。

证据：`output/research-astar-resumed/desktop-client/STATIC-FINDINGS.md`、`verified-consumers.json`、`full-client-download.json`、`full-client-signature.json`、`version-audit/client-runtime-versions.json`。`verified-consumers.json` 保存九处有界源码片段、偏移和源文件哈希。

## 4. 初次隔离运行、日志与关闭后的缓存核查

主任务已直接启动隔离布局中的官方客户端。以下只记录第一次运行的日志与 **23:23:56 +08:00** 关闭后核查，不将静态阶段“未运行”误用于后续，也不覆盖后续诊断运行。

- stdout 为 18,817 字节、496 行；stderr 为 722,918 字节、6,145 行。
- renderer 日志来源为官方网页 `/jingxuan`，出现远程 JavaScript、Mammon 初始化和 service worker 活动；23:17:54.186 记录 `first_screen_time`。
- 这些事实证明 renderer 执行和首屏计时事件；不能替代当前目标作品的详情响应或播放验证。
- `remote-debugging` 多次出现在命令行遥测，没有 `DevTools listening`。参数出现在日志不能证明调试端口已监听。
- 这份日志没有记录可确认的目标详情/播放请求或包含 `aweme_detail`、`video_model`、`play_addr`、`download_addr` 的响应体，也没有证明网页自身可调用壁纸 GET bridge。

初次缓存扫描有五个主 block-cache 文件因运行锁无法读取。客户端关闭后成功读取两个研究 Cache 目录的 **629 个文件，零读取失败**，未匹配到上述明文字段。该步骤是原始字节搜索，没有完整重组 Chromium cache 或解压全部响应体，故不能推导“缓存从未含有详情响应”。

与运行前 baseline 比较，关闭后两个默认目录 `%APPDATA%/douyin`、`%LOCALAPPDATA%/douyin` 仍不存在；HKCU Run 的 Douyin 项前后均为空；extracted-client 路径下残余进程为 0。这只是该时刻对已列项目的检查，不表示审计了所有系统位置。核查本身没有停止进程、修改注册表或删除文件。

证据：`output/research-astar-resumed/desktop-client/RUNTIME-LOG-FINDINGS.md`、`runtime/side-effects-snapshot.json`。完整日志含无关账号通知内容，保持私有。

## 5. 当前 Android 运行环境核查

本轮重新检查宿主环境，ADB 37.0.1 可执行，`devices -l` 返回 0 个设备；该检查自动启动本机 ADB server，没有连接设备或下发设备命令。在已检查的注册表、进程、服务及常用工具/软件目录中，未找到可以直接启动的已安装模拟器；磁盘存在经签名验证的安装包，不能据此宣称已有可用运行时。

CPU 三个虚拟化相关 CIM 字段为 false，但同时 HypervisorPresent 为 true、VBS 运行且内存完整性服务存在，不能只凭前者判断 BIOS 虚拟化关闭。WHP、VirtualMachinePlatform 与 WSL 可选组件为禁用状态；未改系统组件、VBS 或固件，也未重启。目标 ARM64 原生库能否在拟用 Android 环境执行，尚未实测。

证据：`output/research-astar-resumed/runtime/FINDINGS.md`、`runtime-summary.json`、`adb-summary.json`。

## 6. 真实 desktop 动态验证与结果

客户端禁用了 Node inspector。为获得诊断入口，主任务对研究副本的 `app.asar` 原入口增加 **124 字节诊断前缀**，原 166 字节 loader 保持相同；核验 2,401 个其它 packed 条目及 525 个 unpacked 条目保留。期间关闭两个空的预创建 target，并在一次 REPL 超时后重启研究运行时。**不能称本实验完全未修改客户端**；实际页面、GET 请求和签名仍走原业务实现，临时改动用于观测。

截图已核对真实页面播放和控件。UI 显示头像及通知，实验未手动导入凭据；当前证据不能确认具体会话来源，也不能称为匿名上下文。完整截图和日志保持在私有研究目录。

页面自然加载的六条 detail 响应覆盖阳性和当前目标，均为 HTTP 200、业务状态 0，作品 ID 匹配。随后真实 GET 桥批量取得以下六作品详情；此处“档位数”是 `bit_rate` 条目数，不是原片数量：

| 作品 | GET 详情 | 档位数 | `video_model` | 同会话 default 分发 |
| --- | --- | ---: | --- | --- |
| `7698054262056552561`，阳性 | 200 / 0，ID 匹配 | 10 | 空 | 206，40,087,514 字节 |
| `7708319942491344154` | 200 / 0，ID 匹配 | 4 | 空 | 404 |
| `7708052871413075238` | 200 / 0，ID 匹配 | 11 | 空 | 404 |
| `7707993970332290314` | 200 / 0，ID 匹配 | 12 | 空 | 404 |
| `7707964786692083007` | 200 / 0，ID 匹配 | 8 | 空 | 404 |
| `7706218040236444937` | 200 / 0，ID 匹配 | 5 | 空 | 404 |

下载场景的详情对照对阳性和当前目标也返回状态 0，档位数仍为 10/4、model 仍空。fplay 的 source 与 codec8 选择器在阳性返回同一个 40,087,514 字节 source 条目；实际容器检查通过，1080×1920、46.249 秒、HEVC + AAC。该证据是官方 source 声明加媒体检查，没有与作者原始文件做完整哈希比对。当前目标 source 请求仍返回四档，codec8 返回业务状态 2002、无档位。

default 路线不要求 original/source 标签。经桥 Range 传递校准后，阳性返回 `bytes 0-15/40087514`，与独立 source 探针总长一致；16 字节读取本身不能证明全文件逐字节相同。五个目标的 default 404 只描述这些请求没有返回媒体，不能推导原文件不存在。

递归审计 **24 份捕获 JSON** 后，五目标独立视频文件身份组分别为 **4、11、12、8、5**。当前目标四个对象全部与此前记录相同，无新增 VID。在另三个目标发现 **10 个此前未记录的对象**，已对全部对象完成限定 Range 元数据检查：共 40 次 HTTP 尝试、读取响应体 19,332 字节；不下载 mdat，不重算整文件哈希。这十个对象均声明 DASH，位于 0051/0051-ce 桶，路径以 `media-video-avc1` 结束；实际是 AVC1 视频单轨、含 `mvex/trex`，并有音频文件绑定。它们是需要保留的分轨候选，尚无证据把它们认定为作者原文件，不能仅因标签为 normal/low 排除身份。

在当前目标 UI 选择“1080”后，实际 video 元素仍为 720×1280、348.666667 秒、readyState 4；播放对象匹配已捕获的 44,695,234 字节 adapt_lowest 对象，也匹配前轮记录。因此 UI 清晰度文案不能替代实际媒体检查。

本节证据均位于 `output/research-astar-resumed/desktop-client/runtime/`：`response-manifest.json`、`batch-bridge-summary.json`、`download-origin-summary.json`、`selector-native-summary.json`、`positive-current-source-probe.json`、`default-native-summary.json`、`candidate-audit.json`、`new-object-probes.json`、`debug-compatibility.json`、`asar-diagnostic-patch.json`。私有 UI 记录只提取尺寸、时长和状态，未公开其完整地址。桶关联、源码算法与新增音频发现见 [桶与算法报告](original-investigation-2026-11-16-bucket-algorithms.md)。

## 7. 本轮清理和验证范围

**23:55:11 +08:00** 核查研究进程为 0；两个默认 Douyin profile 仍不存在；HKCU Run 无 Douyin 项。`app.asar` 已恢复，SHA-256 与实验前 `fde20fce17eeb52b2533e40fef9887965338589b0a7e38e90775811304b52708` 完全一致。备用浏览器研究 profile 的 Cache index 可独占打开；此项不证明全系统不存在 Chrome 进程。证据为 `runtime/final-cleanup-summary.json`。

本轮实际修复审计器对字典形状 `url_list` 的递归遗漏，补回 6 条音频地址和 3 组同 parent 的音视频关系，未改变生产原画鉴定。专项回归为 **10 passed、2 subtests passed**；`git diff --check` 通过，仅有已有 CRLF 提示。此前全套 **155 passed、152 subtests passed** 属于前轮结果，本阶段未重跑，不能算作此次新增代码的全套验证。
