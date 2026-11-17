# 第二轮：精选入口、真实登录对照和已观察 VID 图

本轮继续以四条失败作品首次取得原片为验收条件，不把上一轮修复的阳性样本替代目标。已新增并验证官方精选 H5 请求、主版登录态专用详情入口和公开 VOD SDK consumer；当前这些请求仍未给出目标原片。

前轮生产修复、完整下载和155项回归结果见 [第一轮修复验收](original-investigation-2026-11-16-astar.md)。本轮的详情可见性恢复和接口校准是研究进展，不是原画修复成功。

## 精选 H5：取得真实可调用接口

成功取得此前未读到的 [Linux.do 公开镜像](https://feedbbs.com/linuxdo/174912) 正文，其具体流程是精选页面取得 `video_model.fallback_api`，仅修改 `codec_type=8`。随后下载目标页面实际引用的14个官方脚本，追到真正的浏览器请求：

```text
GET https://jingxuan.douyin.com/yumme/v1/web/yumme/detail/
aid=392139
app_name=yumme
version_code=26.1.0
device_platform=web
request_source=50
origin_type=detail
aweme_id=<作品ID>
timestamp=<毫秒时间>_<随机数>
```

实际源码为 `669.08d6f59a.js` 的 module94886，时间戳由 `app.aa4973b6.js` module65156添加。SSR直接复制 `yumme_detail.video.video_model`，没有额外的原画转换。浏览器与SSR数据比较使用明确字段投影，原始SSR包含会话上下文，留在被忽略的本地目录中。

| 样本 | 精选详情 | codec8 / source / original |
| --- | --- | --- |
| 阳性7698054262056552561 | 匿名与登录均11个转码，和SSR一致 | codec8与source均取得40,087,514字节官方original，并再次通过媒体校验；original选择器列转码 |
| 7708052871413075238 | 匿名与登录均8个转码，和SSR一致 | codec8业务status2002；source/original仍8个转码 |
| 当前7706218040236444937 | SSR页面404；直接API匿名与登录均成功返回完整详情和5个转码 | codec8业务status2002；source/original仍5个转码 |
| 7707993970332290314 | 匿名API成功，9个转码 | codec8业务status2002；source/original仍9个转码 |
| 7707964786692083007 | 首次网络错误，限定重试成功，5个转码 | codec8业务status2002；source/original仍5个转码 |

这里找到了能恢复详情访问的新官方入口，但没有新增原片身份，故未加入生产原画回退。可复用研究工具 `tools/probe_yumme_detail.py` 默认匿名，不读取catalog、不输出签名URL，也不把目录条目直接声称为已经媒体校验的原画：

另对旧失败样本补做一次新入口核查：7704677676878925119未返回详情；7707196543073275177返回8个既有转码，codec8仍status2002，source/original仍8个转码。没有将历史保存的可用详情误写为当前状态。

```powershell
.\.venv\Scripts\python.exe tools\probe_yumme_detail.py 7706218040236444937 --probe-fallback --output output\yumme-detail-audit.json
```

## 主版专用详情：登录确实生效，仍未补出原片

复用已注册的主版41.1设备与已验证的native签名，以现有会话请求APK真实声明的locate、duet、series三个接口。三个样本共9次请求：

| 作品 | locate | duet | series |
| --- | --- | --- | --- |
| 阳性7698054262056552561 | status0，匹配作品 | status0，匹配作品 | status0，匹配作品 |
| 当前7706218040236444937 | status3002056，无作品 | status0，匹配作品 | status0，匹配作品 |
| 7708052871413075238 | status3002056，无作品 | status3075，data is empty | status4，通用服务器错误 |

去掉会话，保留同一设备和签名器，阳性和当前目标的series均变成status8。由此证实接口实际接受了登录状态，而非仅凭Cookie字段猜测。当前目标两份成功回包仍无非空video_model、无原画声明，完整Aweme分别检查1325和1460个节点，未发现新VID。

两个成功入口的36条不同地址用64次HTTP检查；4个已有转码对象通过Range/moov（39,323,874、32,237,534、27,305,197、51,437,277字节，均338.78秒）。4条download_addr为404，按native UA和API域会话复测仍404。

此前没有建立基线的KMP批量详情也做了登录态正对照：按真实35字节form、无charset的精确MIME、正确body stub和native签名请求阳性，仍HTTP200/0字节；没有对目标继续排列参数。

## 官方VOD SDK新consumer：未建立兼容基线

公开的 [@volcengine/veplayer 1.20.0](https://registry.npmjs.org/@volcengine/veplayer/1.20.0) 明确以 `vod.volcengineapi.com` 为中国区主机、`open.volcengineapi.com` 为备用。builder从Base64 JSON取 `GetPlayInfoToken`，按根路径拼接原查询，加默认 `NeedThumbs=0&NeedBarrageMask=0&Ssl=1`，不生成Authorization。

按这个真实构造，两个主要目标及原画阳性7695305664234589459各自使用新鲜web查询，共6次请求，均HTTP400、InvalidCredential/100025，无播放列表。阳性也失败，因此不能把它写成目标原片不存在。Web token与该公开云SDK的签发上下文未建立兼容基线；没有修改已签字段、借用其他作品token或尝试猜测凭据。

## 继续已观察到的容器VID图

不从参考原片输入身份，只从当前作品目录和实际MP4元数据取得VID，然后查询该VID的原样SDK目录及source目录。复用上轮已经校验的同文件hash元数据，仅新增对象再做Range/moov。

- 当前770621：此前未读的两个SDK ByteVC1对象已补查，所有已观察的7个对象只出现当前VID和同一个内嵌VID，没有第三VID。
- 770805：8个既有对象，原样/source SDK目录均指向同一组已知文件，没有额外VID或原片。
- 770799：SDK发现当前VID与 `v28033gi0000dbrj3knog65o00vl2vc0`，继续查询未得原片；再补齐详情9个对象的容器身份，未发现第三VID。
- 770796：5个既有对象，同样只出现当前和一个已观察内嵌VID，没有原片。

这些结果覆盖已实际出现的图节点与本次选择器，不是“所有隐藏资源关系都已枚举”的证明。

## 回包中编码字段的离线补查

对两主要目标上轮完整web/App回包再做JSON字符串、Base64及常见压缩标识检查，跳过认证/签名类字段和直接媒体URL。共解出142个JSON对象／数组字符串，147个合法Base64串；未出现需要解压的gzip/zlib内容。没有在这些已审字段中发现参考原片MD5，也没有新的符合实际VID格式的身份。参考MD5仅用于离线匹配，没有作为取址请求输入。

## 精选41.1原生上下文

从精选官网实际下载二维码进入[官方安装页](https://z1.nextvid.net/etdvV)，确认appId568863、包名com.ss.android.yumme.video、app_name为douyin_select、版本41.1.0。官方APK实际226,303,823字节、46个DEX，SHA-256为 `2d5b700502900e353cb1d070a1abc5c66a8619df276a47e0a520ceda3a7e2eda`。包内AppContext初始化确认appId和app_name，实际API主机为aweme.snssdk.com；Walle的meta_channel为49862221a，由AppContextManager.internalInit写入channel/tweakedChannel。douyin_select是应用名，不能与实际渠道值混称。

使用该应用身份和证书提交一次官方加密设备注册，HTTP200返回非零device/install ID，保存为独立身份，未借用主抖音设备ID。初始注册和未签名基线在渠道代码核实前使用了通用official值；后续签名对照使用已证实的49862221a。注册成功本身不代表客户端全部环境已复现。

精选arm64的libmetasec_ml.so与主版41.1库完全一致（SHA-256 `a8ec8a89be17b46bce896a1e396fc05bea7f1a7a2a771f305eac4eb25b71f519`），但应用许可证不同。隔离签名器已换成精选自身的包名、appId、328字符许可证和APK v2证书，JNI初始化及回调注册均成功。collect_mode810依据DmtSec默认分支，实际运行标志未抓取。APK v2证书MD5为aea615ab910015038f73c47e45d21466，v3为cd32e88626cfadf13857e91a91a25507。后续[第三轮证书核查](original-investigation-2026-11-16-astar-round3.md)已确认：callback16777218使用GET_SIGNATURES和signatures[0]，实际验签通过的轮换历史第0证书与现有v2输入逐字节相同，符合Android13返回最老证书的兼容规则，无需改用v3。本次仍是基于真实精选配置的隔离SDK验证，不能声称完整复现了Android客户端或已证明服务端验证了签名。

从APK真实DetailApi接口读取11个相关方法的HTTP及参数注解，再用同一独立身份做以下有限对照：

| 上下文和接口 | 阳性7698054262056552561 | 目标7708052871413075238 |
| --- | --- | --- |
| 匿名、未签名detail | HTTP200/status0，匹配作品，9个候选，video_model为空 | HTTP200/status0，无作品；filter_reason=series_control_filter |
| 匿名、精选SDK签名detail | HTTP200/status0，匹配作品，9个候选，video_model为空 | HTTP200/status0，无作品；同一series_control_filter |
| 附现有主抖音会话、精选SDK签名detail | HTTP200/status0，匹配作品，9个候选，video_model为空 | HTTP200/status0，无作品；同一series_control_filter |
| 附现有主抖音会话、精选SDK签名series | HTTP200/status8，无作品 | HTTP200/status8，无作品 |

现有主抖音会话没有建立被精选series接口接受的登录态，不能把最后两行写成“精选有效登录态仍失败”。返回作品的完整Aweme均递归检查298个节点，9个候选没有显式原画声明；因为video_model为空，没有凭空构造精选fplay地址。本轮未发现新的原片对象，也没有由过滤结果推断原片已经删除。

另静态对比精选41.1.0与主版41.1.1的Video、VideoUrlModel、VideoControl：serialized字段分别72、4、32项，未发现精选独有的新增字段。download_addr、new_download_addr、misc_download_addrs、need_set_token、play_auth_token、video_model映射一致。getPlayAddrOrigin实际只是优先返回_playAddrH265、否则_playAddr；getSourceId读取内部_sourceId，方法名均不能作为取得原片的证据。该结论仅限已核查的模型和consumer，不代表整包所有业务字段已穷尽。

可提交的脱敏机器证据保存在 `docs/original-investigation-2026-11-16-yumme-native.json`；原始回包、独立设备身份、许可证和签名仅保留在被忽略的本地output目录，没有复制到文档。

## 证据位置与范围

本轮研究文件位于被忽略的 `output/research-astar-round2/`，关键索引是：

主要结果也已按明确字段投影保存为 [第二轮脱敏机器证据](original-investigation-2026-11-16-astar-round2.json)，其中 `primary_targets_repaired=false` 保留实际验收结果。

- `public/research-summary.md`：公开文章、前端、官方安装页及对应真实来源。
- `jingxuan/h5-js/FINDINGS.md`：官方脚本、6次会话对照和当前目标三种fplay选择器。
- `jingxuan/fplay-summary.json`：论坛精确codec8流程的阳性和770805对照。
- `jingxuan/h5-api-770799.json`、`h5-api-770796-retry.json`：其余两目标。
- `routes/FINDINGS.md`：已登录专用接口、同设备匿名series对照、媒体校验与KMP请求。
- `auth/FINDINGS.md`：公开SDK consumer与6次新鲜token兼容性对照。
- `graph-*.json`、`complete-model-7707993970332290314.json`：已观察VID图和容器检查。
- `encoded-fields-summary.json`：编码字段离线补查。
- `yumme-native/signed-detail-summary.json`、`unsigned-detail-summary.json`：精选独立身份与签名对照。
- `yumme-native/config-trace/`：真实AppContext配置、签名库比较、模型schema与有限consumer证据。

本轮没有调用第三方解析端点，没有使用外部原片MD5/直链启动发现，也没有因新详情可用而宣布原画取址已经修复。
