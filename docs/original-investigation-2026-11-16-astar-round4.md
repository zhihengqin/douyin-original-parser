# 第四轮：重新登录后的原画取址验证

2026-11-16，用户在新打开的抖音浏览器窗口完成登录。本轮仍以当前输入 `7708319942491344154` 仅凭链接取得原画为验收目标。首次新会话请求中，已知可用作品与当前作品的App series接口均恢复HTTP200、status0和匹配作品；当前作品仍没有原画候选，禁用catalog后的生产解析仍为 `source_unavailable`。

本轮没有改动生产取址算法，没有覆盖 `credentials.json` 或修改 `parse_links.py`。新凭据仅保存在被Git忽略的独立研究目录。登录成功由实际返回匹配作品验证，不只依据Cookie名称判断。

## 先核对请求差异

对第二轮series成功与第三轮失败的同一阳性作品，离线比较保存的实际PreparedRequest：host、path、所有非时间查询、设备身份和请求头一致；两轮初始17个Cookie名值对相同。后续唯一变化的第二个odin_tt，在检查的5次请求转换中都与紧前官方响应的Set-Cookie逐项相等。

公共native helper在两轮中都设置 `trust_env=False`；未发现真实代理差异。`cookies=False`只跳过额外访客Cookie更新，不会清除Session已加入的登录Cookie。没有发现可修复的漏传凭据问题，也没有证据确定旧会话失效的具体原因。

用户同意后运行已有的 `tools/capture_login_cookies.py`，使用全新浏览器上下文取得新会话，登录完成后窗口自动关闭。新会话复测工具先验证阳性，只有HTTP200/status0及正确作品同时满足，才访问当前目标。

## 新会话的首次有效对照

| 作品 | series结果 | 实际字段审计 |
| --- | --- | --- |
| 阳性7698054262056552561 | HTTP200、status0、正确作品 | 2,137个节点，9组候选；没有内嵌video_model或显式原画 |
| 当前7708319942491344154 | HTTP200、status0、正确作品 | 1,218个节点，3组候选；同一VID，无显式原画 |

阳性在其他已验证路径可取得原画，本表只验证series详情及登录状态。series没有原画字段本身不证明作品没有原画。

随后用新会话执行生产 `parse()`，明确禁用catalog读取、写入和外部资产恢复。当前目标仍失败：fplay目录有4个视频档位，无original/source；默认档返回HTTP404。精选H5的original/source选择器同样返回4个普通档，codec8仍业务status2002。这里没有使用参考原片MD5或直链作为请求输入。

## 新出现的第四个媒体对象

本轮目录比第三轮多了一个 `adapt_lowest` 文件，不能漏掉它，也不能仅凭它在重新登录后出现就判断登录解锁了新资源。

| 属性 | 实测结果 |
| --- | --- |
| 大小 | 44,695,234字节 |
| 官方档位 | adapt_lowest |
| 分辨率 / 编码 | 720×1280，HEVC hvc1 / AAC mp4a |
| 时长 | 348.667秒 |
| file_id | 726bbf21e70b4b4e9a50e779b166f594 |
| 官方file_hash | 40b34a2cf500f9fe7bf18cbe5249bfe2 |
| MP4内嵌VID | v03033g10000dbqb7pfog65ls2ibfar0，与当前VID相同 |

新登录H5和随后相同UA、空Cookie、关闭自动访客的匿名H5均返回完全相同的4个文件身份。因此该对象也可匿名取得，本次观察不能归因为登录。只对这个新增对象做4次Range，读取288,835字节header/moov；没有第三VID，无需重复既有SDK目录。该文件没有官方原画声明，未作为原画结果。

## 后续重点目标与登录基线变化

随后只用新凭据请求重点目标 `7708052871413075238` 的series，返回HTTP200/status8、106字节、无作品。离线比较它与本轮刚成功的阳性请求，整个Cookie头逐字相同，17个Cookie值、设备身份和所有非时间字段一致；查询中只有作品ID不同。没有发现研究脚本回退旧凭据或漏传登录信息。

此前进程已经结束，因此另外新建相同初始配置的Session做一次阳性对照，明确没有伪称沿用已结束的Session，也没有重放保存的服务端Cookie。阳性此时同样返回status8，所以跳过剩余目标 `7707993970332290314`，没有重试770805。初次新会话被接受与后续对照失败是不同时间、不同Session的实际观察；具体原因未确定，不能解释成目标作品专属限制。

对先前成功的当前series回包中新下发的两条download_addr，分别按原样地址、新凭据、native UA及16字节Range读取一次。一条连接失败，一条HTTP404、零正文、无跳转；没有取得原片身份，也没有把连接失败归类为文件不存在。本分支总计2次series和2次媒体请求。

本轮没有要求用户连续重新登录。有效的新会话已成功返回当前作品完整详情，仍无原画；后续登录基线不稳定的范围保持未验证，不能将被跳过的770799写成新登录态测试通过或原片不存在。

## 证据

本轮脱敏结果保存在[第四轮机器报告](original-investigation-2026-11-16-astar-round4.json)。详细本地证据位于 `output/research-astar-round4/`：

- `login-context/FINDINGS.md`：离线请求与Cookie轮换比较，不输出凭据值。
- `login-context/refreshed-series-run/refreshed-series-summary.json`：新会话首次阳性及当前作品详情。
- `login-context/fresh-production-summary.json`：禁用catalog的生产解析失败结果。
- `login-context/fresh-yumme-summary.json`：H5目录与三种选择器结果，目录检查不冒充完整媒体下载。
- `current-extra-tier/report.json`：新增对象的实际媒体检查及匿名对照。
- `login-context/primary-targets/primary-targets-summary.json`：随后登录错误、阳性对照和当前下载地址检查。

新会话首次成功恢复了App详情访问，未恢复当前作品的原画发现。本轮没有新的可验证原片可接入生产，也没有以重新登录成功替代原画取得成功。
