# 2026-11-16：770799 播放 token 的真实消费链复核

本次复核的结论是：**“仅链接原片发现只差 native Authorization 签名算法”没有得到证据支持。** 之前把 DEX 字符串拼成播放鉴权协议的推断有误；已检查的原生 version 2 播放链反而明确传入空 auth，不生成 Authorization。这个纠正没有恢复目标的原片首次发现。

范围限定为已保存官方 APK、官方网页脚本和目标自身详情的离线审计。本次没有网络请求，没有读取原片 catalog、参考媒体身份或参考直链，没有修改生产代码。脱敏机器证据见 [auth-consumer-evidence.json](original-investigation-2026-11-16-auth-consumer-evidence.json)。

## 目标自身下发了什么

当前保存的 Web 详情输入是 `output/official-link-research-20261116/7707993970332290314.detail.private.json`，精确匹配作品 ID。其 `video.token_auth` 只有一个字段 `play_auth_token`，值是 673 字符的完整签发查询串：

```text
Action=GetPlayInfo
Version=2019-03-15
aid=392139
codec_type=0
format_type=mp4
stream_type=video
video_id=<该作品当前播放 VID>
X-Amz-*=<已有签发字段>
```

使用 `parse_qs(..., keep_blank_values=True)` 后，`X-Amz-SignedQueries` 列出的所有字段都存在；`X-Amz-SignedHeaders` 和 `X-Amz-NotSignBody` 的值确实为空。默认解析器会丢弃空值，不能因此认为签发字段缺失，也没有依据填入 `host` 或 `true`。

这一对象不含 native `PlayTokenAuth` 使用的 `vid/token/hosts/auth/version` 包装，详情的 `video.meta` 也没有提供另一份 `token_auth`。不能把 `play_auth_token` 改名为 `token`、给它自行选择 host，再声称重现了原生请求。

已保存的当前主版 41.1.0、aid 1128 匿名原生详情同样匹配作品 ID，但 `video_model` 为空，`video.token_auth`、独立 `video.play_auth_token` 和 `meta.token_auth` 均不存在。这个结论来自该目标自己的响应，不是从其他失败作品推断。

## version 1 与 version 2 不能混用

41.1.0 的真实 adapter `X.1Hwz/X.1Hx0` 从 `Video.i : PlayTokenAuth` 分别读取 vid、auth、token、hosts 和 version。`X.1I1L.LJFF()` 只使用授权 vid，或通过有效性检查的 metadata token vid；它没有从普通 `play_addr.uri` 计算授权。

真实 URL builder `Y.ADSourceS4249S0100000_43.apiForFetcher()` 的分支为：

| 原生分支 | URL | auth 的来源 |
| --- | --- | --- |
| version 1 | `<issued base>/video/openapi/v1/?action=GetPlayInfo&video_id=<issued vid>&ptoken=<issued token>&aid=<aid><opts>` | `X.1I5w` 原样传递已有 `info.auth` |
| version 2 | `https://<issued host>/?<issued query>` | `X.1I5w` 调 `setPlayAPIVersion(2, null)` |

version 1 的业务 ptoken 和 version 2 的完整 AWS4 查询不是同一输入形态。把 Web 完整 query 放进 version 1 的 ptoken，然后收到 `InvalidAuthorization`，只能证明这次构造未建立有效调用，不能证明需要另找 native 密钥。

更直接的字节码证据在 `classes55.dex` 的 `X.0AGe.LJJLIIIJLLLLLLLZ()`：偏移 796 和 802 检查 version 2/4，跳到 892 把 auth 参数置空；偏移 848 调 `VideoInfoFetcher.LJI(version, url, auth, keyseed)`。`VideoInfoFetcher.LJI()` 保存 auth，`LIZ()` 仅在 auth 非空时加入 `Authorization`。默认网络实现 `X.17mE.buildRequest()` 直接使用传入 URL，只附加已有 header map；其初始化负责 TLS 和超时，不从 token 生成授权头。

这限定于已检查的播放器/default-client 分支。App 可以配置其他 `TTVNetClient`，本次没有据此宣称所有平台网络钩子都不存在，也没有将一个缺少授权包装的 Web 对象视为可用 native 输入。

可复核的原始离线证据在：

```text
C:/Users/EDY/AppData/Local/Temp/douyin-original-round5-20261113/
  round6-20261116/vid-player/Y_ADSourceS4249S0100000_43.java
  main-apk-update/play-auth-audit/X_1I5w.java
  main-apk-update/play-auth-audit/version2-header-chain.json
  main-apk-update/play-auth-audit/com_ss_ttvideoengine_fetcher_VideoInfoFetcher.java
  main-apk-update/play-auth-audit/X_17mE.java
```

旧版 32.2.6 还有另一条明确 consumer：`LX/jkl;->LIZ(String)` 从 Base64 JSON 取 `GetPlayInfoToken`，直接拼接官方 `https://open.bytedanceapi.com?`；调用者使用 `fetchInfo(url, null, 2)`。这同样不是 Authorization 重排算法。此前对另一个作品的原样 query 在有效期内实测为 AccessDenied/100013；该历史网络结果不能替代本目标当前 token 的成功或失败验收。

## AWS4 字符串其实属于上传 SDK；另两段属于 QoS

本次直接读取本地 32.2.6 APK 的 `classes4.dex`，按实际方法指令追溯常量消费者：

| 字面量或线索 | 实际消费者 | 字节偏移 | 业务 |
| --- | --- | ---: | --- |
| `AWS4-HMAC-SHA256 Credential=` | `com.ss.bduploader.AWSV4Auth.buildAuthorizationString` | 8 | 上传 SDK 的标准 AWS4 签名 |
| `,SignedHeaders=` / `,Signature=`，无空格 | 同上 | 96 / 116 | 同一上传鉴权头 |
| `, SignedHeaders=` / `, Signature=`，有空格 | `com.ss.android.ugc.aweme.video.qos.QOSSpeedUpApi.LIZLLL` | 838 / 854 | QoS 加速鉴权 |
| `POST\n/api/v1/mna/assurance\n\n` | 同一 `QOSSpeedUpApi.LIZLLL` | 482 | QoS 的规范请求串 |
| `HMAC-SHA256 Credential=` | 同一 `QOSSpeedUpApi.LIZLLL` | 806 | QoS 的算法前缀 |

上传类 `calculateSignature()` 读取其实例 `secretAccessKey` 并调用 `getSignatureKey()`；外部使用者是 `BDAuthHelper.getSignature()`，构造器接收上传调用的 access/secret、region、service、method、URI、query、headers、payload。这里没有网页播放 token 到播放 Authorization 的转换链。

`tools/probe_apk_auth_header.py` 原本只是对 DEX 原始字节中的字符串截取邻近片段。DEX 字符串表相邻不表示同类、同方法或同一协议。因而此前“这些片段说明 Authorization 由 token 重排生成”和“密钥必在 native 原生层”的结论都应撤回。`tools/probe_vod_auth_header.py` 的尝试是未建立有效基线的研究请求，不是协议实现。

## 网页脚本覆盖与剩余边界

已有 `round8-20261116/web-player/source-inventory.json` 列出的 105 个官方脚本文件全部仍在，逐个 SHA-256 与清单一致。本次沿用其限定 consumer 审计并复核文件完整性，没有声称重新下载整个当前官网：

- 普通视频代码解析已有 `video_model/fallback_api`；未出现按本目标 ID 生成另一份原片凭据的步骤。
- 部分 `play_auth_token` 消费者属于已有综艺/直播回放 `video_info`，不能用普通作品 VID 替代业务输入。
- 播放器中的 `Data.PlayInfoList` 适配器消费已有响应；DRM key helper 需要既有 DRM token 和 host。它们均不是只输入本目标链接即可调用的原片发行入口。
- 所审 105 份语料未找到新的 `GetOriginVideoPlayInfo/GetAllPlayInfo/GetPlayInfoToken` 请求构造；这是对该留存语料的覆盖，不是全网或全客户端的不存在证明。

因此当前可靠结论仍然是：目标的两个 fplay 分支没有列出原片身份；Web 已有签发 query 尚未建立能返回该原片的成功消费链；native 响应没有下发与其 consumer 匹配的授权包装。原片首次发现仍未修复。后续应基于目标自己新下发的有效 host/token/业务输入或实际成功请求继续核对，而不是继续猜 Authorization 字段或把转码结果改成原画。
