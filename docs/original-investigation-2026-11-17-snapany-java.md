# 2026-11-17：从 NiKa Java 小帅接口反向核对原画取址

已经复现 Java 的请求协议，实际解析三条作品，完整下载核对三个文件，并抓取 SnapAny 公开网页当前协议作一次匿名对照。发现一份此前未取得的官方对象，但没有得到第三方服务端的原片发现算法。生产解析器未因第三方质量标签而放宽原画判定。

本轮使用 `SnapanyVideoParserClient.java` 的默认服务配置 `http://114.55.234.134`。未读取运行中 Nacos 覆盖配置，因此结果准确适用于该默认接口，不能直接外推所有已部署实例。凭据未写入工具、报告或命令输出；完整回包、签名媒体地址和文件只保存在被忽略的 `output/snapany-java-audit-20261117/`。

## 实测结果

三次请求均为 `force_refresh=false`，输入只有公开作品链接及 Java 规则生成的幂等 ID，未输入历史原片 MD5、文件 ID 或 CDN 对象键。

| 作品 | 第三方标签 | 实际完整文件 | 尺寸及编码 | 本轮判定 |
| --- | --- | ---: | --- | --- |
| 7707196543073275177 | source / 原画 | 36,153,126 字节 | 540×962，H.264 + AAC | 与已知 normal 540p 的文件 MD5 完全相同，当前结果不是此前的 132,665,774 字节参考原片 |
| 7708052871413075238 | source / 原画 | 140,778,272 字节 | 1280×720，H.264 + AAC | 与此前参考原片大小、MD5、对象键一致 |
| 7708319942491344154 | source / 原画 | 266,189,150 字节 | 720×1280，HEVC + AAC | 本轮新取得的官方对象；可由官方分发再次取回，原画身份尚未独立证明 |

完整文件身份：

| 作品 | 整文件 MD5 | 稳定对象 |
| --- | --- | --- |
| 7707196543073275177 | e050f8be8915a2b4ea7de381939e8aa9 | tos-cn-ve-51/ocRq8hDtQABEEn8qfDAgIKeFb0z2GIQiP7nNCt |
| 7708052871413075238 | 351f10c0e8f038973f2a63c9c749cb41 | tos-cn-v-0051/ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8 |
| 7708319942491344154 | 33e0fcccc4e31fa5d9a8ccdf1d5ff97f | tos-cn-v-0000c2287/okJ0wCfMN9In2J93ObgII9FEBd7xtqoLDmABBf |

第三个文件容器时长 348.667 秒，视频 30 fps、10,460 帧，视频码率约 5.90 Mbps，音频约 196 kbps。已用作品原有 VID `v03033g10000dbqb7pfog65ls2ibfar0` 和本次下载计算出的 MD5 请求官方 `/aweme/v1/play/`，返回 HTTP 206、`Content-Range: bytes 0-15/266189150`，重定向到 `v11-chd.douyinvod.com` 的同一对象。该步骤证明官方分发承认这个文件身份，不证明仅凭作品链接已独立发现它，也不证明作者上传前逐字节一致。

三个接口地址均来自 `v26-dy.ixigua.com`。其中已确认普通档同样带 `a=392139`，所以该域名、aid 不能单独用于原画判定。新对象所在桶为 `tos-cn-v-0000c2287`，不应只允许此前列出的 `0051` 和 `15c800-ce`。桶名仍然只是对象位置，不是质量证据。

## Java 中能完整复现的部分

`D:/Project/NiKa/nika-modules/nika-basic/src/main/java/com/nika/basic/content/dxj/client/SnapanyVideoParserClient.java`：

- 第 28–30 行：`POST /api/v1/resolve`、`GET /api/v1/usage`、`GET /api/v1/result`。
- 第 67–78 行：解析正文仅有 `url`、`force_refresh`、`request_id`。
- 第 102–104 行：新入口 `request_id = "nika_" + MD5(trim(url))`。
- 第 121–122 行：秒级时间戳，签名消息为 `apiKey + "." + timestamp + "." + exactBody`，使用 API Secret 作 HMAC-SHA256 密钥，输出小写 hex。
- 第 156–169 行：头为 `X-API-Key`、`X-Timestamp`、`X-Signature`，POST 发送上述同一正文。

这里的链接 MD5 是幂等 ID；HMAC 是小帅服务的账户鉴权。两者都不是视频文件 MD5，也不生成抖音 CDN 对象键。

`SnapanyManualMaterialWorkflow.java:1056` 遍历 `data.video_list`，仅检查 `quality` / `level` 是否包含 `source`、`original` 或“原画”，符合者按 `size` 取最大。第 1148 行直接将选中 URL 交给 TOS 转存，没有修改域名、桶、aid 或文件身份。770719 的本次实测说明：这套标签选择会接收被第三方标成原画的普通档。

旧快照入口 `DxjDramaMaterialSnapshotSyncServiceImpl.java:2368` 也调用同一服务，但第 2382 行起以 URL path 的最后一段作品 ID 生成 `request_id`，与新入口规则不同。本轮对 770719、770805 的旧 ID 各查询一次，均返回 `404 / code=40013`。770719 新规则 ID 在解析前也查不到；770805 在本轮解析成功后，再按回包中的相同 ID 查询仍返回 40013。因此不能只凭该错误判断“从未解析过”，当前历史查询的持久化或可见性未确认。

三个完整回包 `data` 的字段均为：

```text
trace_id, request_id, vid, title, cover, video_list, balance
```

`vid` 均为空；`video_list` 均只有一条 `{quality, level, url, size}`。没有下发 `file_id`、`file_hash`、官方完整 `video_model` 或上游接口信息。所有字段均已检查，没有把隐藏候选留在未读字段里。

Java 手动素材表保存 request ID、trace ID 和选中 URL；工作流短暂返回完整 `parseResponse`，但 `DxjFrontendMaterialService.java:533` 的批次调用只摘取入库字段，没有持久化完整回包。另需注意 `SnapanyManualMaterialWorkflow.java:1171` 的文件 MD5 存储有 ETag 和本地对象键 MD5 回退，不能直接把数据库中名为 MD5 的字段当作视频内容哈希。

## SnapAny 公开网站的进一步对照

读取 [公开入口](https://snapany.com/zh/start) 及实际引用的 43 个 JS，约 1.24 MB。当前网页请求为 `POST https://api.snapany.com/v1/extract/post`，正文 `{"link": url}`；网页签名已改成 HMAC-SHA256，消息为 `url + locale + timestampMilliseconds`，密钥是公开前端的静态常量。头包括 `G-Footer`、`G-Timestamp`、`Accept-Language`、`G-Api-Version: 2`、`G-Timezone`；匿名请求不带 `G-Session-ID`。

网页当前消费 `medias[].variants[]`，`quality=9999` 显示 Original；不是旧开源适配器中的 `formats[]`。前端也有会员提示，但请求构造中没有 `original/source` 强制选择字段。公开 JS 展示的是第三方网页协议，没有公开抖音上游发现算法。

本轮按当前协议匿名请求一次 770805，HTTP 200。网站回包标为 `quality=9999 / Original`，实际文件却为：

- 68,568,404 字节、1280×720，H.264 + AAC；
- 完整下载 MD5 `ff52aa3872a929aac9ca740e6095c51e`，精确匹配既有官方 normal 720p；
- 对象 `tos-cn-ve-51/oUD496aNyQ5ZDeKAEqWgx6D4FlfiAB5CPIRryr`。

同一作品在 Java 接口取得 140,778,272 字节参考原片，在公开网站匿名接口取得已知普通档。不能把两个服务当作已确认的等价入口；差异可能与服务实现或请求上下文有关，本轮不能定位其原因。两边的“原画”标签都不能代替实际验证。

## 已落实的工具和验证

新增 `tools/probe_snapany_java.py`，从环境变量或指定 Java 文件读取配置，不复制凭据；每次执行只发一个请求，不自动重试。支持：

```powershell
python tools/probe_snapany_java.py usage
python tools/probe_snapany_java.py result --url https://www.douyin.com/video/7708052871413075238
python tools/probe_snapany_java.py result --request-id 7708052871413075238
# 下行会消耗第三方接口额度，使用时才执行：
python tools/probe_snapany_java.py resolve --url https://www.douyin.com/video/7708052871413075238
```

可覆盖 `SNAPANY_BASE_URL`、`SNAPANY_API_KEY`、`SNAPANY_API_SECRET`，或者用 `--java-source` 指定本机源文件。工具摘要明确将返回值记为第三方质量声明，`original_verified=false`，不把标签提升为验证结论。完整回包存入被 Git 忽略的 `output/snapany-java-probes/`，控制台仅显示脱敏摘要。

验证包括 Python 语法编译、真实 usage / result 调用、三个实际回包的幂等 ID 与摘要脱敏检查；三份 Java 接口文件均完整下载并计算 MD5，再由本项目 MP4 解析和 ffprobe 核对。公开网站普通档也完整读取并计算 MD5。没有新增测试文件，没有运行与本工具无关的全套测试。

Java 接口只执行三次新解析。usage 前后额度 42.4 → 42.1，剩余次数 424 → 421，`cost_per_request=0.1`，实际消耗 0.3 接口账户单位。未发 `force_refresh=true`，没有自动加入生产第三方回退。

脱敏证据汇总见同目录 `original-investigation-2026-11-17-snapany-java.json`。本轮实际补齐的是第三方调用协议、原画标签反证、参考原片复验和新官方对象。尚未复现第三方服务端从作品链接首次找到原片身份的算法。

## 追加：HDR 是否解释原画取址差异

对本轮下载的三个完整文件重新执行 ffprobe，检查编码 profile、像素格式、色域、传递函数及流级附加数据；另外对 770805、770831 的前五个视频帧检查色彩标记和附加数据：

| 作品及本轮文件 | 编码 profile | 像素格式 | 色域 / 传递函数 | 文件声明 |
| --- | --- | --- | --- | --- |
| 770719 普通档 | H.264 High | yuv420p，8 位 | BT.709 / BT.709 | SDR |
| 770805 参考原片 | H.264 Main | yuv420p，8 位 | BT.709 / BT.709 | SDR |
| 770831 新候选 | HEVC Main | yuv420p，8 位 | BT.709 / BT.709 | SDR |

本次检查没有出现 PQ、HLG、HDR10 静态元数据或 Dolby Vision 配置；逐帧检查只覆盖前五帧，没有声称扫描整片所有 SEI。HEVC 本身不表示 HDR。上述结果说明拿到的文件按 SDR 编码和标记，不能据此排除平台或上传前曾有另一份 HDR 素材。

770805 旧官方详情记录为 `is_source_HDR=1`，但本轮取得的参考文件为 8 位 BT.709。更早的 7695411862271315236 在 10 月成功取得 207 MB 原片时已有该标记；2026-11-06 报告第 91 行记录其原片同样为 HEVC Main、8 位 Rec.709。2026-11-07 报告第 63 行还记载该作品在 Web / 精选详情分别出现 0 / 1。故不能将业务标记直接等同于实际文件 HDR，更不能把它当作此次失败才新增的开关。

770799 报告中的历史 11 样本表曾呈现相关性：4 个可列举样本为 0、7 个不可列举样本为 1，正文曾误写为 6 个；该组并非随机样本，本轮未重取其全部原始详情。已有 HDR=1 仍能成功的历史反例，所以相关性不能升级为因果结论。此前关于“这些就是 HDR 源”“HDR 源必然不登记默认档”的表述过强，应以这里的限定为准。

HDR 或设备能力影响服务端下发目录仍是可检验假设，但本轮没有证明它是根因，也没有以 `support_hdr=1` 或 `force_fids=hdr` 作为已验证修复。要验证因果，需要同一作品在受控的 SDR / HDR 播放上下文中出现可重复的文件身份差异，并核对新文件的实际色彩信息。此次 HDR 核验仅操作本地文件，没有新增付费解析。
