# 2026-11-16：`7707993970332290314` 取不到原片的原因（第三方可取）

## 现象

用户给出 `https://www.douyin.com/video/7707993970332290314`，其对接的第三方解析服务能返回"原画"，本项目返回 `source_unavailable`（提示：原画接口返回 9 个视频档位，但未返回 `original/source` 原画档位）。

第三方返回的原画地址：

```
https://v26-dy.ixigua.com/85583c6bfca1b9db32a472e21560aae6/6afd44e5/video/tos/cn/
tos-cn-v-0051-ce/ogDEHdDJFAfS9M33ANsYABiDAw6EEoAfwqzH7E/?mime_type=video_mp4&expire=1794813615
```

## 作品侧事实（全部来自官方详情，`aid=392139`）

| 字段 | 值 |
| --- | --- |
| `video.play_addr` | 576×1024，40,274,983 字节 |
| `video.play_addr_h264` | 40,274,983 字节 |
| `video.play_addr_265` | 18,473,036 字节 |
| `video.download_addr` | 720×720，52,471,983 字节 |
| `video.ratio` / `duration` | `540p` / 326,937 ms |
| **`video.is_source_HDR`** | **1** |
| **`video.is_long_video`** | **1** |
| `detail.original` | 1 |
| `xigua_base_info` | 全 0 |
| 公开播放量 | 19,138 |
| `video_model.video_list` | 与该作品 9 个转码档完全一致，无原片行 |

两个选择器（`force_fids=Base64("original")`+`codec_type=5`、`stream_type=source`）都只返回 9 行，全部在转码桶 `tos-cn-ve-51-ce`，`quality` 只有 `low/adapt/normal/adapt_low/adapt_lowest/adapt_lower`；每行都带 `file_id` 与 `file_hash`（都是转码对象的哈希）。

## 第三方那条地址是什么

对 `tos-cn-v-0051-ce` 上的对象做 Range 读：

- HTTP 206，`Content-Range: bytes 0-15/38562411`，`Content-Type: video/mp4`；
- `Content-MD5: tGZekVoxd4l8LP/Iv/c17Q==`（→ `b4665e915a3177897c2cffc8bff735ed`），`ETag` 同值；`x-amz-meta-etag: 30919c0d…-2`（分片上传）；
- moov 实读：**38,562,411 字节 / 326.937 秒 / 720×1280 / avc1 + mp4a**；
- `expire=1794813615`，比签发时刻约晚 27 分钟，说明是**实时签发的短时地址**，不是缓存。

即这条"原画"是 720×1280 的上传原始文件（比转码 `normal` 的 52,471,983 字节还小，因此不能用大小判断）。

## 它是官方原片：官方分发接受这个对象

用该对象 MD5 作 `sign` 打官方分发 `/aweme/v1/play/`（`video_id` 与 `file_id` 都取 `video.play_addr.uri` = `v28033gi0000dbs4nevog65jrl6u1s10`）：

| `sign` | 结果 |
| --- | --- |
| `b4665e915a3177897c2cffc8bff735ed`（来自 CDN 头） | 302 → `v95-aw-chd.douyinvod.com`（另一次 `v26-chd.douyinvod.com`）→ **206，`Content-Range: bytes 0-15/38562411`，`ftyp`** |
| 全零 32 位 | 404 |
| 转码档 MD5 `8cb2358a9f30b153326f5a9c06267948` | 404 |

302 落点同样是 `tos-cn-v-0051-ce` 桶、`?mime_type=video_mp4` 形状，与第三方地址只差 CDN 边缘节点（`douyinvod` vs `ixigua`）。

结论：已知参考对象的 MD5 可使本项目通过官方 `/aweme/v1/play/` 取回相同对象；本次全零和转码哈希请求均失败。这没有揭示第三方如何发现该对象，也不能断定第三方使用相同的 MD5 取址流程。

## 本项目的缺口：这一行根本没被列举

原片对象存在、官方会签发，但详情与 fplay 都不给 `original` 行——没有 `file_id`/`file_hash` 就无从签发。`file_hash` 是整文件 MD5，算不出来，只能等平台下发。

## 已排除的取址尝试（全部无 `tos-cn-v-` 桶行）

| 尝试 | 结果 |
| --- | --- |
| fplay `vquality=8`（模型原值，基线） | 9 行，全转码 |
| fplay `vquality=9` / `vquality=5`+`source` | 2 行，全转码 |
| fplay `codec_type=1`+`source` / `codec_type=6`+`source` | 4 / 5 行，全转码 |
| fplay `force_fids=Base64("source")` | 9 行，全转码 |
| fplay 保留模型原值 `force_fids`（`normal`/`source`）、完全去掉 `force_fids` | 9 行，全转码（排除"本项目改写 `force_fids` 反而抑制了原片行"的可能） |
| fplay `aid=2329` / `aid=1128`（只改 query，路径签名不变） | `status` 空、0 行 |
| fplay `support_hdr=1` / `hdr_type=1` / `enable_hdr=1` | 9 行，全转码 |
| 详情 `play_addr` / `play_addr_265` / `play_addr_h264` / `download_addr` | 全是转码 |
| `video_model.video_list` | 与该作品 9 个转码档一致 |
| `/aweme/v1/play/` 不带 `sign` | 404 |
| `iesdouyin iteminfo` | 200 空 |
| web 详情 `aid=6383` | 403 |
| app 详情 `aid=1128` | 200 空 |

## 与"列举状态"相关的字段级解释：`is_source_HDR`

对 11 个有记录的作品逐个取官方详情，把 `is_source_HDR` 与"是否仍列举原片"对齐：

| 作品 | `is_source_HDR` | `is_long_video` | 公开播放量 | 是否列举原片 |
| --- | --- | --- | --- | --- |
| `7695305664234589459` | 0 | 1 | 413,156 | 是 |
| `7706430541934972201` | 0 | – | 2,356,952 | 是 |
| `7706477018388536499` | 0 | – | 284,512 | 是 |
| `7707264789998849307` | 0 | 1 | 6,568,095 | 是 |
| `7706466342664277290` | **1** | 1 | 351 | 否 |
| `7706732556430953770` | **1** | 1 | 68 | 否 |
| `7707196543073275177` | **1** | 1 | 37,293 | 否 |
| `7707234108203650342` | **1** | 1 | 64 | 否 |
| `7707561244894580004` | **1** | 1 | 134 | 否 |
| `7706282108947385626` | **1** | 1 | – | 否 |
| `7707993970332290314`（本轮目标） | **1** | 1 | 19,138 | 否 |

**4 个列举原片的全部 `is_source_HDR=0`；6 个不列举的全部 `=1`。** 这是本次第一次把"能不能列"落到一个具体字段上，比此前"播放量相关"的解释更贴合：播放量只是伴随现象（HDR 样本多为小播放量），`is_long_video` 也无法区分两组（列举侧有两个 `=1`）。

原始数据在 `output/hdr-vs-listing.json`，探针 `tools/probe_hdr_flag.py`。

## 结论

1. 本项目取不到这条作品的原片，不是参数没调对、也不是桶名识别问题：**平台在当前请求上下文里根本不列举该作品的 `original` 行**，而该作品是 HDR 源（`is_source_HDR=1`）。
2. 本项目已用参考资产的整文件 MD5 验证官方重签可用，但尚未从作品 ID 的官方响应发现该 MD5；第三方的发现流程未知。
3. 因此"照抄第三方接口形状"在本项目里解决不了问题——最后一个环节（用 `sign` 换地址）我们已经完全掌握并验证可用，缺的是上游那一行 `file_hash`。
4. 真正要补的是一个**会下发 HDR 原片行（含 `file_hash`）的官方入口或上下文**。本轮在本项目可构造的请求里没有找到，若不引入外部哈希，仍有待确认。

## 边界与未验证

- 样本 11 个，全部来自本项目历史记录，不是随机抽样；HDR 与列举状态是强相关，**不是已证实的因果**。2026-11-06 的记录里曾出现 `is_source_HDR=1` 的作品当时仍列举原片的例子，且 `is_source_HDR` 会随详情上下文变化，所以不能把它当作硬规则写进生产判定。
- 第三方的 MD5 来源未确定。可能的方向（均未验证）：其上游存在能列原片的上下文（其他 `aid`／设备能力画像／西瓜或中视频侧接口），或在其列举窗口内抓取入库，或来自公开的哈希库。
- 本轮未修改任何生产判定、未写 catalog、未下载整文件；对官方分发只做了 16 字节 Range 校验与对象身份比对。
- 复现脚本：`tools/probe_remote_moov.py`、`tools/probe_fplay_variants.py`、`tools/probe_hdr_flag.py`、`tools/probe_hdr_and_dispatch.py`、`tools/probe_dispatch_sign.py`；输出在 `output/`（`moov-770799.txt`、`variants.txt`、`hdr.txt`、`hdr-dispatch.txt`、`sign.txt`、`hop.txt`、`fids.txt`）。

## 续查：已验证参考资产可由官方重新签发（2026-11-16）

用户提供的当前作品参考文件对应完整 MD5 `b4665e915a3177897c2cffc8bff735ed`。它不是由作品 ID 推导出来的，因此该结果是已知资产恢复，不是首次发现算法。

用此 MD5 作为官方 `/aweme/v1/play/` 的 `sign`，并使用该作品当前官方 VID 作为 `video_id` 和 `file_id`，官方返回 HTTP 206、精确 `Content-Range: bytes 0-15/38562411` 和 MP4 `ftyp`。远程 moov 读取到 720×1280、326.937 秒、avc1 视频和 mp4a 音频；结果与目标详情时长相符。普通官方 fplay 目录在本次复测仍只有 9 个转码档，两个 selector 和详情内嵌档位均没有 original/source 行。换言之，原片对象可恢复的原因是已掌握可信资产 MD5，不是解析器漏选了原片档。

已通过完整分段下载核对 38,562,411 字节文件的 MD5。资产记录已加入 `original_metadata.json`，来源标记为 `official_play_hash_from_verified_asset`。该来源继续受项目既有开关保护：默认目录加载会过滤它；只有设置 `DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1` 才会请求官方分发，并在成功返回前继续验证实际 MP4 媒体。Linux 一次性使用示例：

```bash
DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1 .venv/bin/python run.py 7707993970332290314 \
  --download output/7707993970332290314_original.mp4
```

该开关会允许 catalog 中所有通过来源校验的外部资产恢复记录参与解析。首次只凭作品 ID 发现原片的缺口仍然存在；其他没有可信文件/哈希的目标不会因此自动恢复。

## 补记：第二轮排除清单与"两种地址形状"

上一轮"已排除"只覆盖 fplay 的少数参数。本轮把剩下能想到的官方面扫了一遍，全部只有 `tos-cn-ve-51-ce` 转码桶：

| 尝试 | 结果 |
| --- | --- |
| 详情 `device_platform` 取 `webapp` / `android` / `iphone` / `unknown` | 四种上下文的 `video_model` 完全相同（`is_source_HDR=1`、9 个转码档）；`tools/probe_detail_context.py` |
| fplay `stream_type` 取 `hdr` / `origin` / `original` / `high` / `dash` | 均返回 9 档转码 |
| fplay `vquality` 全值域 `0`–`13` 加 `hd/sd/source/original/origin/hdr`（20 个取值） | 全部只有转码桶；仅 `8` 返回全部 9 档，其余 2 档，最大 52,471,983；`tools/probe_vquality_sweep.py` |
| 详情每个 `addr` 的 `url_list` 全部条目 | 只有转码桶地址，加上 `api-play.amemv.com` / `api.amemv.com` 的分发入口 |
| 无头浏览器打开作品页并触发播放 | 页面被挡：0 个 `<video>`、无 `/aweme/` 请求、HTML 内无 `tos-cn-v-`；`tools/probe_video_page.py` |
| 分发路径矩阵 `/play/hd/`、`/play/hdr/`、`/play/source/`、`/play/original/`、`/play/hevc/`、`/play/h264/`、`/playwm/` | `www.douyin.com` 下返回网页壳（200 HTML），无真实端点 |
| 下载候选请求 | `api.amemv.com/aweme/v1/aweme/download/` 对测试输入返回 `url doesn't match`；尚未建立有效调用，不能由错误文本推断它只接受短链 |

### 地址形状的差别

- **档位分发**（本项目在用，已验证可用）：`/aweme/v1/play/?video_id&file_id&sign=…` → 302 → CDN 地址带长串参数（`a=1128&br=921&bt=921&btag=…&cquery=…&dy_q=…&ft=…&l=…&mime_type=video_mp4&qs=13&rc=…`）。转码档自己也带 `sign`（等于该档 MD5），说明 `sign` 是按对象 MD5 查。
- **小帅那条**：`…/tos-cn-v-0051-ce/ogDEHd…/?mime_type=video_mp4&expire=1794813615`，只有两个参数。

形状不同有两种解释：(a) 它是**对象级直读（对象 key + 服务端签名）**的产物，与档位分发不是同一类接口；(b) 只是**另一条 CDN 边缘**（ixigua）的跳转形状不同——我们的分发跳转落在 `douyinvod` 边缘（长参数），没有观察到 `ixigua` 边缘的形状。所以 (a) 是更可能但不被证实的解释。无论哪种，都无法从中读出对象 MD5。

### 当前唯一未证实的官方面线索

当时将 `url doesn't match` 解释为需要短链，尚无真实调用依据。后续已从官方 APK 找到可由目标长链接生成有效短链的调用，无需用户另给短链；但该下载候选对新短链仍返回相同错误。

**实测结果（用户已提供该作品的分享短链 `https://v.douyin.com/9odWMuc0J9Q/`）：此线索失败。**

- `api.amemv.com/aweme/v1/aweme/download/?url=<短链>`、`?url=<整段分享口令>`、加上 `aid=1128` 的四种组合，全部返回 `status_code=0 / Url does not match`；同一接口用作品页、分享页、iesdouyin 页地址也都是这个结果。
- 短链落地页：`https://www.douyin.com/video/7707993970332290314?previous_page=web_code_link`，HTTP 200、72,914 字节的 SPA 空壳，`play_addr` 出现 0 次、`tos-cn-*` 桶 0 个、`_ROUTER_DATA` 不存在。
- 追加的 UA 试验（iPhone Safari、`com.ss.android.ugc.aweme` 安卓、Windows Chrome）里，只有 Windows Chrome 走通；另外两种没有返回可解析页面。

这些请求尚未建立有效的下载调用基线，不能从 `url doesn't match` 直接推断需要 App 签名，也不能声称已穷尽官方入口。后续已经根据官方 APK 找到长链接生成短链的真实调用，但新签发短链仍没有使此下载请求成功；禁用全部历史记录的首次原片发现也仍失败。准确复测条件、结果及限制见[仅输入链接的验收记录](original-investigation-2026-11-16-link-only.md)。

## 代码改动：`--allow-external` 成为一等参数（同日）

只给作品链接时，这条作品能否取到原片完全取决于外部来源记录是否放行。此前只能靠环境变量，现改为显式参数：

- `run.py <链接> --allow-external`：本次运行放行外部来源记录，仍走官方分发重签 + MP4 媒体校验；`--serve` 同样支持。
- 实例参数 `OriginalParser(allow_external_asset_recovery=True/False)` 优先于环境变量，`False` 可显式压掉环境里的开关。
- 默认策略下失败时错误信息追加：`（本地已有该作品经官方重签与媒体校验的原片身份记录，外部来源默认屏蔽；加 --allow-external 或设置 DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1 即可取到原画）`。
- 该提示只在"记录存在但被策略挡住"时出现；`tools/compare_original_sessions.py` 的诊断流程重写了 `_catalog_original_candidate`，因此不会触碰 catalog，对应回归用例仍通过。

实测（唯一输入 `https://www.douyin.com/video/7707993970332290314`）：

| 调用方式 | 结果 |
| --- | --- |
| 默认 | `source_unavailable`，9 个转码档 + HDR 说明 + 放行提示 |
| `--allow-external` | `原画（官方原片分发），720×1280，38,562,411 字节，326.937 秒`，媒体校验通过 |

新增回归 `test_allow_external_flag_replaces_env_and_hints_when_blocked`（实例参数放行、默认提示、显式 False 压环境变量三种情形）。全套 94 passed, 106 subtests passed。

## 还要注意：VOD `play_auth_token` 线索（仍未打通）

详情自带 `video.token_auth.play_auth_token`：一条完整的 `GetPlayInfo / Version=2019-03-15` AWS4 签发 query（`aid=392139&codec_type=0&format_type=mp4&stream_type=video&video_id=<VID>`，`X-Amz-Expires=3600`，`X-Amz-SignedHeaders` 为空）。它完全来自链接自身，若打通就是对象级播放信息，恰好对应第三方那条 `?mime_type=video_mp4&expire=…` 的形状。

实测（脚本 `tools/probe_vod_token.py`，原始签发 query 原样使用，未改签名字段）：

- `https://vod.bytedanceapi.com/?<token>`、`https://vod-luna.douyin.com/?<token>`：均 HTTP 200、`{"CodeN":100013,"Code":"AccessDenied","Message":"User is not authorized to perform: vod:GetPlayInfo on resource: []"}`。
- 资源标识为空，追加 `Vid` / `vid` / `VideoId` 不改变结果（未列入 `X-Amz-SignedQueries` 的参数被忽略）。

结论：这条线索方向正确但调用形态未建立，需要知道资源标识怎么带（签名 query 内、还是经某个内部网关转译）。未伪造签名、未改写签发字段。


