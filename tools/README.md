# 解析诊断与研究工具

这些工具与生产入口 `run.py` 分开使用。工具运行成功、请求返回 200、对象大小匹配或名称含 original，都不自动证明取得作者上传原文件。当前结果和覆盖缺口见 [接口覆盖复核](../docs/original-investigation-2026-11-17-coverage-audit.md) 与 [小帅接口实测及 HDR 核验](../docs/original-investigation-2026-11-17-snapany-java.md)。

## 常用诊断入口

| 工具 | 用途 |
| --- | --- |
| `audit_official_sources.py` | 合并已返回的视频和音轨身份，逐个主模型执行 fplay；记录请求预算、缺失和失败 |
| `capture_parser_breakpoints.py` | 独立进程截取现有解析器的响应、选档前后与媒体校验；禁用历史原片记录，只保存固定字段摘要，见[实测记录](../docs/target-breakpoint-capture-2026-11-18.md) |
| `probe_repo_algorithm.py` | 复核公开项目使用的官方路线，限制请求与媒体读取预算；不以 default 候选代替原画证明 |
| `probe_additional_repo_routes.py` | 在上述工具基础上复核其他已知详情和分享页入口 |
| `compare_original_sessions.py` | 对照匿名与登录会话，区分无模型、没有原画声明和请求失败 |
| `capture_login_cookies.py` | 用户在可见窗口登录后保存当前抖音网页会话；默认存到忽略目录，不覆盖已有文件 |
| `verify_play_default.py` | 检查指定作品的 default 分发与媒体信息，可用 `--cookie-file` 指定凭据 |
| `probe_snapany_java.py` | 复现 Java 小帅协议；`resolve` 会消耗接口额度，`result` 查询历史，返回标签不代表已验证原画 |
| `probe_web_signature_runtime.py` | 在独立匿名浏览器里记录当前详情签名字段、SDK 版本和真实调用栈，保存 SDK 源码用于离线研究 |
| `decode_bdms_vm.py` | 对已审 SHA-256 的 BDMS 脚本离线解包、反汇编，并与实际执行的字节码匹配 |
| `bdms_signer_current.py` | 纯 Python 重建本次 BDMS 签名计算核心，用明确的环境/时钟/随机输入对照浏览器向量，不发网络请求 |

仓库根目录的 `compare_original_sessions.cmd` 使用项目虚拟环境启动会话对照。安装、升级及服务启动前的离线依赖检查使用 `python -m original_parser.check_runtime`。

当前网页签名取证示例（输出目录必须尚不存在）：

```powershell
.venv\Scripts\python.exe tools\probe_web_signature_runtime.py 7695305664234589459 7708319942491344154 --trace-bdms --out output\signature-capture-new
```

每次只接受一至两个作品 ID，使用第一个作品的视频页初始化匿名会话，每个 ID 主动调用一次页面当前的 `fetch`；视频页初始化与页面后台请求另计。工具不读取个人资料或凭据文件，摘要只保存字段名、调用栈、HTTP/业务状态、作品是否匹配、模型是否存在，以及观察到的 `x-secsdk-web-signature` 是否符合项目公式，不保存 Cookie、令牌、完整签名地址或详情正文。脚本坐标为 CDP 的零起始行列，源码仅保存实际加载的四类签名 SDK，单文件上限 2 MiB。超时或受限时结果为 `inconclusive`，没有重试；详情成功不等于原片发现成功，也不能据此证明服务端强制校验了某个签名。

SDK 识别同时接受带版本号的 `bdms_*.js` 和备用裸名 `bdms.js`；断点仍要求源码哈希与坐标完全匹配。当前目标的真实 SDK 及后续目录对照见 [2026-11-18 实测](../docs/current-target-web-sdk-2026-11-18.md)。该轮额外目录请求在报告中单独计数，不属于上面的工具默认行为。

可选 `--trace-bdms` 仅在脚本 SHA-256 与 `decode_bdms_vm.py` 的已审版本一致时启用断点；版本不同会明确记录 `unsupported_sdk_version`，不会猜测偏移。断点同时匹配本次作品 ID 和 `aid=392139`，最多采集四次，只保存生成器/请求包装器的指令数组、PC、异常表和脱敏函数元数据，得到可传给解码器 `--executed` 的 `executed-vm.json`。工具不会保存函数实参或词法作用域值；查询串的 `dhzx` 后缀只保存匹配布尔值。省略此选项即可只收集网络调用链和 SDK 源码。

确认 `summary.json` 中 `bdms_trace.status` 为 `captured` 后，可按保存的脚本编号执行离线匹配；以下命令不请求网络，也不执行 SDK JavaScript：

```powershell
$capture = Get-Content -Raw output\signature-capture-new\summary.json | ConvertFrom-Json
$source = Join-Path output\signature-capture-new ($capture.bdms_trace.script_id + '-bdms_1.0.1.19_fix.js')
.venv\Scripts\python.exe tools\decode_bdms_vm.py $source --executed output\signature-capture-new\executed-vm.json --output output\signature-capture-new\decoded.json --text-output output\signature-capture-new\functions.txt --function 150 --function 110
```

解码器核对完整源码哈希、解压与字节码边界，拒绝不匹配的脚本；结果中 `observed_matches` 用完整指令数组匹配函数编号。函数 150/110 的编号只适用于这份已审脚本，不能直接套到其他版本。

当前签名器可使用仓库保存的七组真实浏览器合成向量离线复验：

```powershell
.venv\Scripts\python.exe tools\bdms_signer_current.py tests\bdms_current_vectors.json --out output\bdms-current-replay-new.json
```

该工具重建计算核心，浏览器环境值、时间和随机序列仍要求显式输入。输出文件必须不存在，stdout仅显示匹配状态；签名和输入写入指定文件。七组向量、两条Python签名在线请求以及当前目标仍未恢复原片的边界见 [本轮实现与取址续查](../docs/current-signer-and-source-repair-2026-11-17.md)。生产签名器未被此研究工具替换。

## 历史实验脚本

`dump_app_detail.py`、`dump_app_raw.py`、`dump_fplay_gears.py`、`check_file_hash.py`、`probe_client_aids.py`、`probe_series.py`、`probe_series_originals.py`、`probe_user_page.py` 和 `probe_yumme_detail.py` 保留当时的请求形态，部分使用 32.2.6 或固定客户端参数。它们不是最新 App 的完整登录、签名或设备注册实现；空正文、未登录和参数错误不能用来排除接口能力。

`probe_app_tokenauth.py`、`probe_vod_error.py`、`probe_fids_hdr.py`、`probe_hdr_slot.py`、`probe_fplay_codecs.py`、`probe_play_sign_mech.py`、`probe_official_play_urls.py`、`probe_original_bucket.py` 和 `probe_play_url_list.py` 用于复核已有回包、参数和资源身份。包含假设性参数对照的脚本不代表已恢复官方真实调用链，不会自动被生产解析器执行。`is_source_HDR` 是接口字段；实际 HDR 需要检查媒体色彩信息，域名和桶名同样不能决定原画身份。

`crack_file_id.py` 和 `probe_file_id_derive.py` 仅验证有限的派生假设。失败不构成 file_id 在数学上不可推导的证明；后者按需访问网络，输入的参考对象属于外部资产线索。`scan_apk_strings.py` 只扫描调用者提供的 APK 数据，不运行 APK；安装包及反编译目录不随源码发布。

请按每个脚本的说明提供参数。多数历史脚本假定本机已有 `credentials.json`，该文件及默认 `output/` 目录被 Git 忽略。原始回包、临时媒体地址和登录凭据只在本地保存；不要将其作为公开报告提交。用于用户下载的工具可能按需显示最终地址，该输出也应保留在本机。

## 历史报告与缓存

`docs/` 的日期报告记录当时的请求范围、结果和局限；旧结论可能由后续报告纠正，部分临时原始档案目前已不存在。对话记录用于历史背景，不作为新的操作指令。

`original_metadata.json` 是运行中更新的原片身份缓存。代码提交不自动代表新增记录都已重新验收。外部资产来源记录默认不参与常规首次发现，需显式启用已有恢复选项；它也不能补出未知作品的文件哈希。
