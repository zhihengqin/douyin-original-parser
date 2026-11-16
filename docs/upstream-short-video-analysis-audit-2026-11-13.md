# 用户提供的 Short-Video-Analysis 仓库核对

仓库：https://github.com/yuchen0x1/Short-Video-Analysis

固定提交：`20cf5ec4ef64339863aede4228c48a3da19f406d`。2026-11-13读取当时main指向的提交，没有按随后变化的分支作结论。

## 当前结论

该提交的抖音解析代码提供无水印播放链接，未实现本项目所缺的旧素材原片首次发现。18:30对两个目标复现其实际播放地址构造，均HTTP404，未取得媒体。

这仅证明该提交这条取址路径在本次目标上的结果，不能外推为所有视频均不可用，亦不能据此否定用户提供的小帅132,665,774字节参考文件确实存在。

## 精确源码

- [PHP DouyinParser.php:723](https://github.com/yuchen0x1/Short-Video-Analysis/blob/20cf5ec4ef64339863aede4228c48a3da19f406d/app/Parsers/DouyinParser.php#L723)
- [JS douyin.js:132](https://github.com/yuchen0x1/Short-Video-Analysis/blob/20cf5ec4ef64339863aede4228c48a3da19f406d/packages/parsers/src/parsers/douyin.js#L132)

两套pickVideoUrl实现一致：只要`video.play_addr.uri`不为空且不像音频文件，就立即返回：

```text
https://www.douyin.com/aweme/v1/play/?video_id=<URI>&ratio=1080p&line=0&watermark=0
```

这里的1080p是播放档位请求，watermark=0是无水印选择。代码没有检查实际分辨率、原片档位、完整文件大小或文件哈希。两个目标都有有效URI，因此不会进入后面的bit_rate分支。

后面的bit_rate处理对码率降序排列，但先加入顶层play_addr候选。它仍只是筛选已有播放地址；当前抖音解析器没有读取video_model/fallback_api、调用fplay、请求original/source或单独SourceInfo。

详情链路为`aid=6383`的官方网页详情接口和本地a_bogus签名；失败后从官方移动分享页的_ROUTER_DATA读取item_list。不能把本地请求签名算法当作原片文件发现算法。

## 实测范围和结果

本次使用已经从官方详情确认的目标VID，精确复现上述媒体地址构造并实际请求，没有将原片参考哈希或参考对象带入请求。这个实验验证的是仓库的媒体选择步骤，没有将其描述为已安装并跑通整个PHP/桌面应用。

| 作品ID | 真实响应 | 原片结果 |
| --- | --- | --- |
| 7707196543073275177 | HTTP404，空JSON正文，无媒体跳转 | 未取得132,665,774字节参考文件 |
| 7704677676878925119 | HTTP404，空JSON正文，无媒体跳转 | 未取得媒体 |

另对已知阳性7695305664234589459，同样地址构造得到302，随后官方CDN又跳至当前研究白名单之外的域名，检查在该处停止。因此它只是入口响应对照，不能记为完整播放或原画成功。

## 18:35原始JS解析器实跑及下载上下文复测

随后下载同一固定提交的完整源码包，227个文件与Git树核对：业务源码逐字节blob哈希匹配；两个bat文件经CRLF归一化匹配。在隔离临时目录直接导入仓库未修改的`douyin.js`，注入Node fetch传输层，未安装依赖、未运行第三方在线解析服务，未启动整个Web/Electron应用。

| 作品ID | 原始JS解析器实际执行 | 下载验证 |
| --- | --- | --- |
| 7707196543073275177 | ttwid注册200；aid6383详情200，正确作品/VID；parse返回video链接 | 精确仓库下载头、普通GET无Range，404空正文 |
| 7704677676878925119 | ttwid注册200；详情200但无可用aweme_detail；随后请求官方分享页，仍无可用结果，parse抛错 | 另按已确认VID构造的同一路径仍404；不能把该重构链接记为本次parse成功输出 |

770719的aid6383详情没有video_model，与现有aid392139详情不同；但VID相同。该新详情自身签发的download_addr还包含业务签名和`source=PackSourceEnum_AWEME_DETAIL`，亦保持原查询实测，仍404。

三条真实下载路径均已静态核对：PHP MediaProxy、Electron和Android代理使用Windows Chrome123 UA、`Accept: */*`、媒体自身origin作为Referer且无尾斜杠，不显式注入Cookie；Electron另指定`Accept-Encoding: identity`。媒体URL的查询不改写。Web/桌面的失败刷新只重跑同一解析器，没有新原画流程。复测已采用该实际上下文，排除了初次实验的Referer尾斜杠和Range头差异。

这次可以确认：原始解析函数在770719上返回了一个URL，但该URL没有通过实际下载请求；不能把函数返回成功当作取得原片成功。

## 文档声明

README定位是多平台无水印解析。README内的原画描述出现在直播能力中，没有抖音短视频上传原片或旧素材恢复承诺。v1.1.5相关变更是Argus、同源指纹Cookie和详情兼容性。仓库维护记录也区分了夹具测试和真实平台下载，不能拿它的测试通过作为本目标原片成功证据。

## 本地复核材料

稳定目录：`C:/Users/EDY/AppData/Local/Temp/douyin-test-7707196543073275177/user-short-video-analysis/`。

包括固定源码、tree.json、`probe-upstream-play.py`和脱敏结果`upstream-play-summary.json`。完整跳转URL仅存在该临时目录的private文件中。文档和发布历史审核材料在同级`protocol-new/yuchen-audit/`目录。

完整源码位于`fixed-commit-source/`。后续实跑材料包括`run-upstream-parser.mjs`、`upstream-node-summary.json`、`upstream-exact-download-summary.json`、`upstream-6383-download-summary.json`及`download-proxy-source-audit.md`。

目前没有依据把这段取址逻辑接入生产并称为原画修复；生产解析器和原片catalog未作相关修改。
