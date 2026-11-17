# 2026-11-17：普通视频模型上游与 App 保存视频链

本轮继续追踪普通视频的模型生成与“保存至相册”前置请求，范围不包含壁纸。目标仍是仅凭作品链接、自建取得作者上传原片；本轮未找到可用于修复失败作品的新原片身份。时间按 Asia/Shanghai 记录。

## 目标与成功对照的实际请求

对目标 `7708641111765585178` 与成功对照 `7695305664234589459` 分别执行普通 Web 详情、完整 PC 详情及 issued/original/source 三条 fplay 路线，各 5 次 HTTP 请求。两组全部完成，作品及视频身份检查通过，没有截断或媒体探测。使用独立匿名访客，不读取登录文件或原片 catalog，不调用第三方解析。

| 作品 | Web / fplay 结果 | 身份计数 |
| --- | --- | --- |
| `7695305664234589459` | 有 1 个官方明确 original 候选 | 36 个不同 file_id 值、35 个不同 file_hash 值；两个计数不直接等于原片数量 |
| `7708641111765585178` | 4 个带具体 FID/hash 的媒体对象，均为 normal/adapt/adapt_lowest | 4 个不同 file_id、4 个不同 file_hash；此外有未合并的下载入口地址组 |

目标的 PC 响应包含 4 档，最小详情外层列 2 档，但内嵌模型和三个 fplay 目录均已覆盖这 4 个具体媒体身份。没有将“外层 2 档变成 4 档”当作新增原片，也没有将 `original_verified=false` 解释为已经对所有文件完成媒体反证；本轮没有请求完整媒体或读取 moov。

证据：[目标审计](../output/research-video-upstream-20261117/770864-official-audit.json)、[成功对照审计](../output/research-video-upstream-20261117/positive-official-audit.json)、[按来源分组的身份对照](../output/research-video-upstream-20261117/request-comparison.json)。

随后复用此前已注册的匿名 App 设备与官方库签名环境，按照已审计的 41.1.0 `DetailApi` 普通详情参数，各执行一次 GET `/aweme/v1/aweme/detail/`。两个请求均 HTTP 200、status_code 0、作品 ID 匹配，签名初始化检查通过。未携带登录 Cookie；会话中出现的 `odin_tt` 是本次响应设置的 Cookie。

- 成功对照返回 13,156 字节的 `video_model`，包含 `dynamic_video`、`fallback_api`、`key_seed`，没有 `token_auth`。
- 目标的 `video_model` 为空，没有 `token_auth`，外层 `bit_rate` 为 2 项。App 回包中观察到的 2 个 file_id 和 3 个 file_hash 均已存在于本轮 Web 结果，没有新增值。

本轮合计 **12 次官方 HTTP 请求**，计数不含 Web 匿名访客初始化的浏览器资源请求。签名在本地运行，没有启动 App。完整签名请求与响应只留在忽略目录，脱敏证据为 [App 对照](../output/research-video-upstream-20261117/native-detail-comparison.json)、[App 与 Web 身份对照](../output/research-video-upstream-20261117/native-web-comparison.json)。[复现脚本](../output/research-video-upstream-20261117/probe_native_detail.py)依赖现有本机 App 签名研究环境，不作为生产依赖。

这些结果说明目标在本次普通 App 上下文中确实没有收到视频模型，不能把这次缺失归因于详情请求失败。它们也不能证明其它业务上下文或服务端入口均没有原片。

## 模型字段从哪里进入播放器

对留存官方主 APK 41.1.0 的全部 57 个 DEX 先做精确字段表索引，定位 `Video.g/i/k0`（video_model/token_auth/play_auth_token）与 PlayTokenAuth 的直接引用，再审计命中的 4 个 DEX 中的直接写入方法。命中 11 个方法，实际来源包括：

- `X.1I3T.decode` 从 Protobuf 消息装载已有模型、授权对象和独立 token。
- `X.1I3W.decode` 从同一消息读取 vid、token、auth、hosts 等。
- `X.1I3M.LIZJ` 从已有 SimVideo 复制模型与授权；Parcel 构造函数复制序列化值。
- `X.1Ibg` 使用已有 fallback_api 刷新模型，这条链已在前轮审计。
- `Video.LJIL(DashVideoInfo)` 使用已持有的模型包装；追加的 5 个 Dash 直接写入方法没有自行签发凭据。

“全部 57 个 DEX”只描述这些精确字段的索引范围，不意味着审计了所有业务。反射反序列化、JNI 写字段和动态代码不属于直接 DEX 写入计数。原始指令与复现脚本见 [模型上游报告](C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/model-producer-20261117/FINDINGS.md)。

继续收窄最后一层直接调用边界：`VideoUrlModel.mDashVideoModelString` 的 3 个直接写入方法分别为 Parcel 装载、Dash 复制/清空、原样 setter；setter 的 2 个直接调用者分别复制已有 `Video.g` 与 SimVideoUrlModel getter 的值。两个 Dash 字符串构造重载合计命中 7 个直接调用方法，新增的 `X.1I3Q.LJFF` 从传入 `X.1I3S` getter 取得已有模型后构造，没有在该调用方法中发 HTTP 请求。没有继续递归所有通用转换层，不能将这一层覆盖扩大为所有间接调用者均已排除。

## App 的保存视频前置请求

已定位实际长按菜单下载入口：`LppDownloadModule → ShareActionImpl.LJJIJIIJI → X.0y8K → GalleryShareHelper / X.1Vri`。其中独立的服务端请求由 `X.0INp` 构造：

```text
GET https://www.snssdk.com/aweme/privacy_platform/api/privacy/permission/download
    ?item_id=<已有作品 ID>
```

该响应类的业务字段是 `status` 和 `msg`。消费者按状态继续或停止，继续时仍使用已有 Aweme 对象，没有从该响应接收新视频地址。实际 URL 选择器 `X.1Vrk` 使用详情已有的 `play_addr`、`download_addr`、`download_suffix_logo_addr` 或 `misc_download_addrs.suffix_scene`。

这是下载权限检查和已有地址选择的证据，不能把接口路径中的 download 当作原片取址能力。没有为这条权限接口发送猜测性网络请求。字段注解和指令证据见 [下载调用链报告](../output/research-video-upstream-20261117/download/FINDINGS.md)。主任务独立复核了清单中 39 份证据文件的 SHA-256，全部匹配。

## 当前结果

当前两条普通视频上游线索没有给出新的、输入完整的原片发现请求；目标 `7708641111765585178` 的作者上传原片获取仍未修复。本轮没有修改生产选档规则或部署配置。官方 original 标签的对照也未与作者持有文件做整文件哈希比较。

下一步需要能从目标自身输入获得的新资源身份或实际补发模型的业务调用；已有 URL 刷新、普通下载权限检查及模型复制函数不能填补这个步骤。
