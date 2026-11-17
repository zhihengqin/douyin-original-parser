# 第三轮：当前输入 7708319942491344154 的独立验收

2026-11-16，工作区 `parse_links.py` 的输入已换为 `7708319942491344154`。本轮按新输入重新核查，不沿用其他作品的成功结果。禁用历史原片记录的生产 `parse()` 仍返回 `source_unavailable`，尚未取得该作品原画。前两条重点目标和随后加入的失败样本也没有因本轮检查而修复。

后续用户重新登录后的有效App详情、第四个媒体对象及匿名对照，见[第四轮新会话验证](original-investigation-2026-11-16-astar-round4.md)。下文3个文件和series登录失败为第三轮当时的实际结果。

本轮没有修改生产取址代码。已完成的算法、QuickTime 媒体校验和完整下载修复见[第一轮验收](original-investigation-2026-11-16-astar.md)，新增精选 H5 入口及原生调用证据见[第二轮记录](original-investigation-2026-11-16-astar-round2.md)。155 项测试和152个子测试通过是前轮生产代码验证结果，不是本次目标原画取得成功的证明。

## 当前作品：详情、完整字段与实际媒体

新鲜 Web 详情与精选 H5 详情均返回 VID `v03033g10000dbqb7pfog65ls2ibfar0`。递归展开 JSON 字符串后分别检查715和376个叶字段，只发现下列3个不同媒体文件。作品的 `original=1`、音乐原声标记和 `is_source_HDR=1` 均不作为原画文件证据。

| 官方档位 | 文件大小（字节） | 实际分辨率 | 实际编码 |
| --- | ---: | --- | --- |
| adapt | 33,785,763 | 576×1024 | HEVC / AAC |
| normal | 57,163,128 | 540×960 | H264 / AAC |
| normal | 89,305,645 | 720×1280 | H264 / AAC |

这3个对象均完成Range与moov检查，时长都是348.667秒，具备视频及音频轨道；没有完整下载它们，也没有把其中最大文件作为原画结果。

两端各自下发的完整 fallback 分别按原样、original、source 请求，六份成功目录仍是相同3个媒体身份。两次 `codec_type=8` 都返回业务status2002及空列表。Web/H5中唯一未关联具体文件的下载地址组共有4条，实际Range全部HTTP404。生产默认档也返回404。上述失败只说明本次请求没有成功，不能推断上传原片不存在或已被删除。

普通 App 详情在现有会话和一次匿名请求下均HTTP200、空正文。这一路的审计明确保留不完整标记；不能声称它返回的所有字段已经检查。

## 由文件本身发现第二 VID

对3个对象读取1,047,791字节容器元数据，跳过mdat视频主体。adapt文件内嵌当前VID，两个normal文件内嵌另一VID：`v03033g10000dbq8slvog65gt07rs0p0`。

随后对两个已观察到的VID各请求SDK默认目录及source/codec5目录，共4次。第二VID返回的两条normal记录虽然 `file_id` 与当前VID不同，但文件哈希、字节数和分辨率对应刚检查的两个文件。因此它们是已有媒体的新目录身份，不能计作新增原片。已观察的3个媒体对象没有出现第三VID，也没有新的原画候选。

此分支共12次Range和4次SDK请求。它覆盖实际观察到的节点，不等于证明所有后台资源关系都已枚举。

## App 专用详情与当前登录基线

复用第二轮已建立的主版41.1注册设备和隔离签名器，对新输入使用真实接口注解对应的duet、locate、series请求：

| 请求 | 本次结果 | 可支持的结论 |
| --- | --- | --- |
| duet / 当前作品 | HTTP200、status0、匹配作品 | 取得完整App作品详情，可继续检查实际字段 |
| locate / 当前作品 | status3002056 | 本次没有返回作品 |
| series / 当前作品 | status8 | 本次请求没有建立有效登录结果 |
| series / 阳性7698054262056552561 | 同样status8 | 上轮series登录成功的基线本轮未复现，不能归因于目标作品 |

duet完整回包43,450字节，共检查1,085个节点，返回与Web相同的VID，`video_model` 为空，没有新增VID、file_id、file_hash或显式original/source候选。其中两组可对应到已有的33,785,763和57,163,128字节转码；另一组download_addr声明89,305,645字节但没有hash，不能仅凭大小认定它就是Web的720p对象。只对这组2条地址各做16字节Range，两者均HTTP404、空正文、无跳转。

该分支共4次详情与2次媒体请求。已有会话字段随请求发送，不等于服务器接受登录；没有由status8推断具体失效原因，也没有声称复现完整native媒体运行时请求头。

## 精选证书回调疑点已关闭

第二轮留下“APK v2/v3证书不同，Android13回调应选哪张”的问题。本轮从实际DEX switch定位callback16777218，确认它以 `GET_SIGNATURES=64` 查询 `PackageInfo.signatures[0].toByteArray()`，没有走 `SigningInfo.getApkContentsSigners()`。

APK v3的proof-of-rotation共有两张证书。第0项858字节，与现有harness的v2 DER逐字节相同；第1项899字节，为当前v3证书。已用cryptography验证旧证书对新证书的轮换签名，以及覆盖轮换属性的外层signed-data签名，均通过。[Android13官方实现](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-13.0.0_r1/services/core/java/com/android/server/pm/pkg/parsing/PackageInfoWithoutStateUtils.java#341)对GET_SIGNATURES及有效轮换历史返回最老证书。

因此现有证书输入有源码与签名验证依据，无需改为v3，也没有为这个已关闭疑点重复发网络请求。此检查没有复现完整Android运行环境，没有观察缓存或可选拦截器运行状态，也不证明服务端已接受整个native签名。

## 下载接口的实际注解与返回模型

对本地主版和精选41.1.0 APK补查下载接口字符串，并从主版提取6个方法的HTTP/参数注解和7个返回类。主版文件名虽为 `douyin-main-41.1.1.apk`，manifest实际版本为41.1.0/410101；这里以manifest为准。本分支没有发网络请求。

- `privacy/permission/download`：GET `item_id`，返回模型只有msg/status，属于下载权限查询。
- `namek/merchant/download/{list,mget,retry,delete}`：企业证书下载任务，输入download_type或已有download_id，返回任务及file_url。retry/delete虽声明GET，仍是状态变更接口，本轮未调用。
- `ai/asset_task/download/info`：GET `zlink` 与 `channel_name`，返回android_download_url、compliance_info、pop_up，没有视频资源或原画模型。
- `originVideoResourceId`：主版唯一字段owner为 `shortvideo.edit.VideoPublishEditModel`，直接用途是本地编辑模型构造、读写及parcel序列化，没有找到从任意作品ID取得该字段的网络调用。

这些明确的输入和输出没有提供新的“aweme_id → 原画身份”路径。两份APK的DEX中未发现旧猜测路径 `/aweme/v1/aweme/download` 的完整字面量；这不排除动态构造或其他服务端接口。精选对应路由字符串已索引，但没有重复提取全部同名方法注解。完整静态证据在 `download-api-static/FINDINGS.md`。

## 证据与边界

脱敏机器摘要为[第三轮结果](original-investigation-2026-11-16-astar-round3.json)，其中 `current_target_repaired=false` 保留真实结果。原始响应留在被Git忽略的本地 `output/research-astar-round3/`；文档不复制完整签名地址、Cookie、设备凭据或令牌。

- `current-production-summary.json`：禁用catalog读写后的生产解析结果。
- `current/current-response-audit.json`：Web、H5、原样及选择器目录。
- `current/current-app-retry-download-summary.json`：App空正文和4条下载地址检查。
- `current-lineage/current-lineage-report.json`：3个实际媒体、两个VID、4份SDK目录。
- `native-current/native-current-summary.json`：App专用详情与阳性对照。
- `cert/FINDINGS.md`、`cert/rotation-verification.json`：证书回调、官方源码和轮换签名验证。
- `download-api-static/summary.json`：实际下载方法、返回字段和适用范围。

本轮未使用历史原片哈希或外部直链作为发现输入，也未调用第三方解析端点。结果证明当前已测链路尚未发现目标原画；不证明全部抖音接口已穷尽，更不支持把普通转码改名后宣布修复成功。
