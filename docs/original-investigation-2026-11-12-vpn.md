# 2026-11-12：VPN 下的国内外公开实现与官方请求复查

## 结果和范围

仍未恢复旧目标 `7706282108947385626` 在没有历史可信记录时的首次原片取址。
验收文件为33,507,060字节、1080×1920、101.667秒、完整H264/AAC；本轮没有
将已知样本身份加入catalog，没有修改生产解析代码，没有部署或重启服务。

研究证据位于本机被Git忽略的 `output/original-recovery-20261112/vpn-research/`。
完整临时播放URL、Cookie和token仅保存在private文件，不随部署发布。

## VPN 与搜索的实际可用性

用户开启的本地HTTP代理可正常访问国外资料。系统ProxyEnable为0，因此研究
请求需显式使用本地代理；没有修改系统代理、VPN设置或生产服务配置。

通过代理，Sourcegraph `/.api/search/stream` 从先前直连403变为200，并实际
返回源码匹配。GitHub/GitLab公开接口及raw源码也可读取。Google的普通HTTP200
是JavaScript占位页，独立匿名浏览器渲染后显示验证页；Bing部分查询虽200，
结果主题无关。这些没有计为有效技术搜索或“全网不存在”的证明。

使用playwright-interactive技能读取公开搜索页；未打开个人浏览器配置或登录状态，
未监听流量，研究浏览器已关闭。

## 国内公开实现

中文GitHub readme查询“抖音 原画/原片/无损”，各取近期更新前50项，共138个
不同仓库，下载并检查14个相关项目的实际实现；此外读取Gitee、博客及论坛正文。
这不是138个实现都已逐行审计，也不代表穷尽公开仓库。

新增相关实现分别使用最高码率排序、默认play跳转、playwm改play、外部解析API，
或给普通play_addr补“官方原画”标签。例如：

- `MoyerZhang-Claude/video-downloader` 将ratio=default结果直接改标original，
  即使与普通档同大小也覆盖标签。
- `111wan/liuying` 按bit_rate提取后，把顶层play_addr标为“官方原画”。
- Gitee `vibecode-lqc/video-downloader` 按分辨率、FPS、码率及大小取最大。
- `aweiribao/DouYinParse` 取Web detail的play_addr；腾讯云1935189文章的
  PHP及博客园wpoo代码是旧iteminfo和普通play去水印方法。

这些均未提供隐藏原片身份发现步骤，未运行其外部签名或解析服务。
证据：`china/FINDINGS.md`、`china/github-readme/FINDINGS.md`及固定源码。

## 国外公开代码与协议

Sourcegraph真实全局匹配及GitLab新候选中，重点核实：

- `ihmily/doubao-nomark` 的codec8/unwatermarked输入是现成豆包或Dola会话
  fallback，不是抖音旧分享ID取址。
- `Everless321/dYm` 读精选SSR后用VID请求普通default播放；没有独立原片验证。
- `Su-1003/douyin-fetch` 技术文档明确网页最高为normal_1080_0，无法取得
  上传的4K原片，实际仍按bit_rate选择。
- `jianzhichu/dysync.net` 的原画优先分支只拼VID/default/PUBLISH，HTTP下载层
  直接下载现成URL，没有二次原片接口或远端签名身份生成。
- `zyronon/douyin` 固定fixture中18条PUBLISH播放地址的sign均等于同一
  play_addr.file_hash，且处于普通h264_1080p结构。PUBLISH不是独立原片证据。
- `cv-cat/DouYin_Spider` 的两处SourceInfo都在新文件实际上传并
  CommitUploadInner之后取得。输入是上传会话SessionKey，不是公开作品ID。
  GetMeta是该提交里的上传后处理函数，没有独立旧VID查询。

新发现的旧CRC32头条地址与既有you-get/官方SDK路线相同；历史已实测未返回
原片，本轮未重复。未修改已签字段、跨作品复用token或猜测原片哈希。

证据：`global/FINDINGS.md`、`global/publish-source-findings.md`、
`route-audit/cvcat-sourceinfo-findings.md`、`root/`内Sourcegraph结果和固定源码。

## 官方客户端“保存视频”链路

本轮补查独立于合拍的 `DownloadAction → X.14HR → SharePrivacyVideoApi → X.14HS`。
权限接口只返回status/msg；后续读取已有playH264/downloadAddr/suffixLogoAddr
或播放器缓存，没有新原片身份查询。下载URL构造器只补公共参数。
`merchant/download/mget`实际为企业认证证书任务；投屏接口是此前已验证的旧路由，
本轮没有再发请求。

证据：`route-audit/save-video-route-findings.md`及完整方法指令。

## 目标的实际官方请求

仅对目标做了以下有限对照，不使用catalog或第三方解析：

| 请求 | 实际结果 |
| --- | --- |
| 保存的官方fplay，保留上下文，原片选择器，经VPN | HTTP200/status10，正确VID，10个转码，无原片 |
| 同一官方fplay，source选择，经VPN | HTTP200/status10，正确VID，9个转码，无原片 |
| 通过VPN取得新详情后，原样token请求vod.bytedanceapi.com | HTTP200，AccessDenied/100013，无资源列表 |
| 同一新token原样请求vod-luna.douyin.com | 同上 |

最大normal仍为34,092,503字节，与此前已完整比较确认的重新编码文件身份一致。
没有因文件更大、桶名、标签或普通302跳转放行为原片。

token请求没有替换签名绑定参数或补猜测字段。AccessDenied是授权失败，不能
写成“已经成功查完所有档位但没有原片”，也不能证明原文件已删除。
证据：`root/vpn-fplay-summary.json`、`root/vpn-exact-playauth-summary.json`。

## 验证和后续边界

新增研究脚本作语法检查，证据JSON作解析验证，文档通过git diff --check。
没有生产代码改动，因此没有重新运行生产测试套件。

本轮扩大了可访问资料和已核协议范围，但没有找到可重复的旧作品首次原片发现
机制。现有新作品直接原画、可信原片记录重签能力继续保留；未知旧作品取不到
真实原片时仍返回获取原画失败。本记录不作为算法已恢复的交付声明。
