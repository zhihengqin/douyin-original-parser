# 2026-11-17：Ghidra、JADX 与桌面字节码取址审计

本轮实际使用了 Ghidra 和 JADX，目标是仅凭作品链接发现作者上传原片的身份与官方取址入口。工具运行、反编译成功和有效视频文件都不单独等于原片发现成功。当前生产解析器没有因本轮研究改变选档规则。

## 工具与输入

- Ghidra 11.4.3 PUBLIC 取自官方发行地址，安装到 `D:/ProjectPy/.tools/ghidra/ghidra_11.4.3_PUBLIC`，使用已有 JDK 21.0.11；未修改系统 Java 环境变量。ZIP 大小 456,551,841 字节，CRC 检查通过，SHA-256 为 `b22a8baebb14339f19903c54363ba7e01781930cc43ab430539aabce0d58547a`。
- Android 输入为已留存并核验版本的官方主 APK 41.1.0。其临时文件名仍含 `41.1.1`，不把文件名当版本。APK SHA-256 为 `5ac7b9d3cc1528663f4835a6c0a6666d0891e093ffd5dc00154f52ea6b17c619`。
- 实际以 AARCH64 模式分析 `libavmdlv2.so`（2,361,704 字节）、`libttmplayer.so`（4,004,504 字节）、`libvcbasekit.so`（264,328 字节）和 `libuniplayer.so`（493,664 字节）。前两库自动分析分别约 70 秒和 54 秒，随后进行了 JNI、地址刷新、模型字段来源和回调的定向反编译。
- Java 分支使用本机 JADX 1.5.3 和原始 DEX 指令交叉核对；没有运行 APK。
- Windows 输入为既有官方 8.8.0 客户端的 `win32ia32.node` 与 `Common.Build-20261030T0818160.node`。前者由 Ghidra 实际分析，后者作为数据离线解码，没有执行其业务载荷。

下载记录：[download-manifest.json](D:/ProjectPy/.tools/ghidra/download-manifest.json)。输入与证据：[Android 输入](../output/research-ghidra-20261117/native/inputs.json)、[DEX 输入哈希](../output/research-ghidra-20261117/java-chain/input-manifest.json)、[桌面模块输入](../output/research-ghidra-20261117/desktop/loader-manifest.json)。

## Android：已恢复的真实取址链

`AVMDLURLFetcherBridge.start` 要求已有 rawKey、fileKey、oldURL，新重载另外要求 engineId。旧调用方从已登记的视频模型读取 fallback API，新调用方找到已有播放器实例；刷新模型后按输入的 fileHash/fileId 匹配文件。JNI 注册、原生字符串参数和 Java 方法声明相互吻合。所审链路没有从 aweme ID 计算未知原片身份。

本轮同时核对了 fallback 为空的分支：`X.0AGe.getAPIString()` 会转向 `DataSource.apiForFetcher`。枚举该 APK 的九个直接实现及两个委托后，实际输入仍为已有 URL、token、host 或 VID，或者直接返回空；其中 legacy Toutiao SDK 路径已经在此前研究中测试。未将已知路径重复记成新发现。

`AVMDLDataLoader._getAuth` 的 JNI 入口为 `0x15d5fc`，实际调用链终点 `0x2debc4` 将输入字符串、loader 保存的字符串与 SDK 版本拼接后计算 CRC32。Java 消费者将其用于 `mdl://` 或本地 HTTP 代理 URL 的 `ah` 参数。该路径不是向服务器申请播放授权，不能以函数名推断它能补出原片权限。旧汇总中的“只差 native Authorization”和“应从 libc++_shared 找密钥”推论已同步纠正。

另定位到 native `tryRefreshVideoModelUrl`（`0x29c420`）：必须先有任务属性 `0x3a` 中的 requestUrl，缺失时直接跳过。后续定向追踪闭合了传递链：`libuniplayer 0x11a040` → 播放器 option 30057 → `video_model_request_url` 字典项 → protocol command 1008 → loader 对象 `+0x1f8` → 任务配置 `+0x1d8` → getter `0x29f8b8` 的属性 `0x3a`。同一路径的属性 `0x11` 对应已有文件 key，open 流程将其作为 `X-Loader-FKey` 使用。30057 由 native 内部设置，不能因 Java 中找不到对应 const 就推断该链不存在。

已核对 `0x11a040` 的两个输入来源。配置 63050 启用后，它优先读取已有 VideoModel `+0x138`；`0x110428` 证明该字段来自返回 JSON 的 `fallback_api`。否则读取已有 fetcher `+0x38`，该字段由构造函数 `0x13d488` 复制调用方传入的 URL。已追踪的调用方分别传入已有 `fallback_api`，或者经 `0x13cdf4` 消费模型 `+0x160` 中已有 token／JSON `GetPlayInfoToken`，拼接 GetPlayInfo 请求（默认 host 为 `vod.bytedanceapi.com`）。这里找到了已有请求的消费位置，没有找到从作品 ID 签发 token 或发现未知原片身份的步骤。

解析回调也已定位：`0x14d3a4` 注册 type 8 插件，实际解析函数为 `0x114038`。它要求传入非空 hash，解析已有回包后按 hash 精确匹配文件；输入带 `fileid` 前缀时，允许以唯一匹配的 `file_id` 选中文件。空身份或找不到对应项均返回空。因此所审刷新链依赖已有请求与文件身份，不能直接填补当前缺失的原片发现步骤；这也不排除尚未审计的其它业务入口。

关键原始证据：[30057 设置函数](../output/research-ghidra-20261117/native/uniplayer-plugin-followup/functions/0011a040.c)、[fallback_api 字段来源](../output/research-ghidra-20261117/native/uniplayer-url-origin/functions/00110428.c)、[fetcher URL 构造函数](../output/research-ghidra-20261117/native/uniplayer-fetcher-origin-v2/functions/0013d488.c)、[已有 token 消费函数](../output/research-ghidra-20261117/native/uniplayer-fetcher-origin-v2/functions/0013cdf4.c)、[按文件身份解析回包](../output/research-ghidra-20261117/native/uniplayer-parser-followup/functions/00114038.c)。

详细函数、地址、字节码及当前覆盖边界见 [Java 调用链](../output/research-ghidra-20261117/java-chain/FINDINGS.md) 和 [原生库报告](../output/research-ghidra-20261117/native/FINDINGS.md)。JADX 局部循环重建不完整的地方以原始 DEX 为准，Ghidra 的未解析外部符号也保留在报告中。

## Windows：恢复封装载荷并定位真实下载处理函数

Ghidra 恢复了 Nodeguard 加载器的实际解码逻辑：按构建文件名计算本样本的 key 18152，读取尾部架构／版本／模块表，对对应字节区间作变换后反转。离线提取了五个模块的 ia32、x64 共十份 cachedData，包含主进程、preload 和三个 worker。

十份解码结果均重新编码回原始字节区间，长度、SHA-256 和逐字节比较全部通过；主任务独立重复核对了一次。证据：[提取清单](../output/research-ghidra-20261117/desktop/payload/manifest.json)、[独立复核](../output/research-ghidra-20261117/desktop/extraction-independent-check.json)、[提取脚本](../output/research-ghidra-20261117/desktop/extract_nodeguard_payload.py)。这证明解码变换可复现，不表示已恢复原始 JavaScript 源码。

随后按公开 V8 序列化格式解析对象、常量池和字节码。主进程缓存的 16,065 个 BytecodeArray 共解码 735,418 条指令，指令边界检查没有失败。全量解码计数不等于逐个审计全部函数；语义结论只针对已追踪的处理函数。

实际 `downloadURL` 桥接函数 SFI 119334 把第二个参数传入下载管理器；管理器 SFI 89835 在指令偏移 99 读取该参数的 `url`，在偏移 195 将它传给 `sender.downloadURL`。这个已恢复的处理函数直接消费调用方给出的下载地址，没有在此处用作品 ID 另取原片。

证据：[桥接函数](../output/research-ghidra-20261117/desktop/disassembly/sfi-119334.txt)、[下载管理器](../output/research-ghidra-20261117/desktop/disassembly/sfi-89835.txt)、[指令解码检查](../output/research-ghidra-20261117/desktop/disassembly/validation.json)。

已完成的其它有限追踪也只消费已有输入：GET 桥读取调用方的 path/queryParams 并交给 Electron `net.request`；壁纸下载读取调用方的 `wallpaperInfo.downloadUrl` 并交给通用下载器。用户指出壁纸与原片目标偏离后，该支线明确停止，未发出壁纸请求，也不把视频下载器复用当作原片发现能力。普通视频的原片身份来源才是后续调查对象。

对 25 个选中函数另外检查了常量池索引、分支落点和寄存器范围，错误数为 0。V8 公共定义标签为 `14.2.231`，这里只确认所用结构和指令的兼容性，没有验证厂商引擎的精确构建版本。完整限定结论见[桌面报告](../output/research-ghidra-20261117/desktop/FINDINGS.md)和[机器摘要](../output/research-ghidra-20261117/desktop/summary.json)。

## 本轮链接实测基线

三条链接使用当前项目 Python 虚拟环境，各自在独立进程中解析。明确禁用外部资产恢复，mock 空历史记录读取并屏蔽记录写入，没有输入原片哈希或读取登录文件。

| 作品 | 本轮结果 | 验证范围 |
| --- | --- | --- |
| `7695305664234589459` | 7.74 秒成功，528,422,694 字节、1920×1248 | 官方 `original` 声明，`source_evidence=official_quality`，大小与音视频轨校验通过；未与作者文件做整文件哈希对照 |
| `7708641111765585178` | `source_unavailable` | 本轮当前解析链路仍未取得原片 |
| `7707993970332290314` | 首次与一次重试均 `network_error` | 本轮详情请求未完成，不能据此对该作品的原片目录作新结论 |

证据：[基线结果](../output/research-ghidra-20261117/baseline.json)、[770799 一次重试](../output/research-ghidra-20261117/baseline-target-retry.json)、[有界实测脚本](../output/research-ghidra-20261117/link_baseline.py)。未据静态字符串增加猜测性的上游请求。

## 执行边界

本轮未改生产取址和原片判定，未安装或运行 Android 客户端。曾对已有隔离桌面二进制执行一次意图仅输出版本的 RunAsNode 探针，进程退出 10、没有版本输出；该实验不算匹配引擎验证，也没有据此确认其全部启动行为。未向该探针提供本轮提取的 cachedData。其临时目录独立，后续检查该研究路径下没有残余客户端进程。实际字节码解析由 Python 读取数据完成，不依赖该探针。

没有因为分析出函数或下载管理器就将失败作品报告为已修复。当前需要的是能从目标自身输入建立的新原片身份与官方请求；这些证据也不能证明平台所有客户端或服务器端入口都已不存在。
