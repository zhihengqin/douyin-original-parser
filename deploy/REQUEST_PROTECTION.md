# 04 解析服务的请求保护

三个 Java 实例调用同一个 Python 服务时，`/parse` 和 `/api/v1/resolve` 共用队列、缓存和冷却状态。正常成功响应保持兼容；这些保护不依赖 Java 升级。04 已验证可以解析，当前主调用地址为 `http://172.31.0.4:8765`。

## 默认配置

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `PARSE_WORKERS` | `3` | 实际工作线程数，1～32，浏览器并发也与此值对齐 |
| `REQUEST_INTERVAL` | `0.5-1` | 每个工作线程完整解析结束后，独立等待0.5～1秒再启动下一个 |
| `CACHE_TTL` | `300` | 成功缓存最多 300 秒；0 关闭结果缓存 |
| `CACHE_MAX_ENTRIES` | `128` | 成功结果最多 128 项 |
| `QUEUE_SIZE` | `6` | 最多6个额外等待任务，另有`PARSE_WORKERS`个执行位置；还受HTTP受理上限约束 |
| `QUEUE_WAIT_TIMEOUT` | `150` | 单个调用者等待排队和结果的总秒数，低于 Java 默认 180 秒 |
| `FAILURE_THRESHOLD` | `3` | 自上次真实成功以来累计 3 次限制类失败后暂停 |
| `COOLDOWN_SECONDS` | `900` | 暂停 900 秒后，允许下一条请求试探恢复 |

`MAX_CONCURRENT=6`表示最多同时受理6个HTTP请求，包含等待者。短链跳转、详情、原画接口及媒体校验由默认3个工作线程并行执行。每个线程独立执行完整任务并间隔等待，单个任务内部的必要HTTP请求不单独等待0.5～1秒。每个任务创建自己的解析器和会话，浏览器模式使用独立浏览器上下文；同作品任务仍只执行一次。健康检查`protection.workers`为实际线程数，`protection.active`为正在执行的任务数。

完整作品 URL、裸作品 ID、包含完整作品链接的分享文案按作品 ID 合并。相同短链接也会合并和缓存；不同短链接即使指向同一作品，当前仍按不同输入处理。媒体校验不可关闭；外部 Cookie 文件内容改变后会隔离原缓存。

只有 `code=0`、`probe.ok=true` 且 `source_selected=true` 的官方原画结果才缓存。当前不存在普通档成功降级路径；`source_unavailable`、普通转码、失败结果和没有媒体校验的结果都不会缓存。返回结果和所有候选地址都必须有明确的 Unix 秒有效期；合并的同文件镜像取最早有效期，缓存最迟在最早地址到期前 60 秒失效。未知有效期、毫秒时间戳、即将过期或未校验的结果不缓存。缓存命中复用之前的媒体验证结果和真实档位，不重新访问视频。每个调用者拿到独立副本。

请求中的 `force_refresh` 默认为 `false`，只接受 JSON 布尔值。Java 侧发现媒体地址失效后传入 `true` 时，先删除同作品、同凭据及同预检模式的旧成功缓存，再按原队列执行或合并到同一在途任务。强制刷新受队列容量、任务间隔和冷却约束；冷却期间可能返回 503，刷新失败不会恢复旧缓存。它不会主动更新外部 Cookie，也不能保证平台重新下发未提供的原画。

HTTP 200 空正文、非 JSON、HTTP 403/444、HTTP 429、缺失或被拒绝的访客凭据参与暂停计数。无效输入、单作品不可见/无原画、普通网络超时和媒体校验失败不增加也不清零计数；实际解析成功才清零，缓存命中不清零。受保护的 HTTP 模式不会在单个任务内刷新访客重复请求详情。

达到阈值后，尚未开始的排队任务立即收到 HTTP 503，`code=upstream_cooldown`，并携带 `Retry-After` 响应头及 `retry_after_seconds` 字段。暂停期间有效缓存仍可使用。冷却结束后只允许一个真实任务试探，同作品请求可合并；成功恢复，失败重新冷却。旧批次仍在执行的任务可以返回有效结果，但其迟到成功不能关闭当前冷却或试探状态。无人请求时不会主动试探。

队列满或等待超时返回 HTTP 429。未启动且已无人等待的任务取消；已开始的任务继续，重试会合并到该任务。150 秒是调用者等待上限，不是强制杀死浏览器的时限。若底层调用永久挂起，执行槽位仍被占用，健康检查和缓存仍能工作，但新任务会等待超时，需要维护者处理。

这些数值是可调整的保守初始配置，不是平台公布的安全频率，也不能保证不会受到访问限制。

## 升级已有的 04 服务

下面保留 2026-09-28 请求保护包的手动升级示例。当前版本请优先使用部署包中的
`deploy.sh` 或 `upgrade.sh`，它们会同步服务虚拟环境的依赖并检查签名功能。
手动更新也必须同步 `requirements.txt`，仅替换源码可能遗漏新增的 `gmssl`。
以下以 root 执行，目录为 `/opt/software/python`，systemd 服务名为 `douyin-original-parser`。

先确认压缩包可读：

```bash
cd /opt/software/python
tar -tzf /tmp/douyin-original-parser-protection-20260928.tar.gz >/dev/null
```

成功后，备份当前源码，再停止服务更新：

```bash
backup_path="/tmp/douyin-before-protection-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$backup_path" original_parser run.py deploy/linux/start.sh
echo "源码备份：$backup_path"
systemctl stop douyin-original-parser
tar -xzf /tmp/douyin-original-parser-protection-20260928.tar.gz --strip-components=1 -C /opt/software/python
.venv/bin/python -m pip install -r requirements.txt || exit 1
.venv/bin/python -m pip check || exit 1
install -D -m 644 deploy/linux/request-protection.conf /etc/systemd/system/douyin-original-parser.service.d/90-request-protection.conf
systemctl daemon-reload
systemctl start douyin-original-parser
systemctl status douyin-original-parser --no-pager
```

现有 systemd 主文件及 `80-detail-mode.conf` 不会被上述步骤替换。若配置为 `DETAIL_MODE=browser`、`BROWSER_PROFILE=windows`，新版继续使用同样的模式；HTTP 模式也受支持。配置样例只写保护参数。

修改 `/etc/systemd/system/douyin-original-parser.service.d/90-request-protection.conf` 中的数值后，执行 `systemctl daemon-reload` 和 `systemctl restart douyin-original-parser`。无需数据库或 Redis。

## 验证

```bash
curl --noproxy '*' --fail --connect-timeout 5 --max-time 10 http://127.0.0.1:8765/health
journalctl -u douyin-original-parser -n 30 --no-pager
```

日志应显示原来的详情模式，以及 `protection interval=0.5-1.0s ... threshold=3 cooldown=900.0s`（采用当前默认配置时；已有实例以实际启动参数为准）。`/health` 的 `ok=true` 仍只表示服务在线，新增 `protection`：

- `state=closed` 正常；`open` 冷却中；`half_open` 正在试探恢复。
- `active`、`pending` 为实际执行和排队的任务数。
- `started` 为实际启动解析次数；`cache_hits` 为缓存命中次数；`coalesced` 为合并请求次数。
- `consecutive_failures`、`retry_after` 为限制失败计数及剩余冷却秒数。

对同一作品依次请求两次，确认返回 `code=0` 和 `data.probe.ok=true`：

```bash
curl --noproxy '*' --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://127.0.0.1:8765/parse -H 'Content-Type: application/json' -d '{"url":"7689381368630906122","with_probe":true}'
curl --noproxy '*' --fail-with-body --connect-timeout 5 --max-time 180 -X POST http://127.0.0.1:8765/parse -H 'Content-Type: application/json' -d '{"url":"https://www.douyin.com/video/7689381368630906122","with_probe":true}'
curl --noproxy '*' --fail http://127.0.0.1:8765/health
```

返回地址的有效期可确定时，`started` 应只增加 1，`cache_hits` 增加 1。日志不输出 Cookie、完整详情或带签名的视频地址。

Java 保持 180 秒请求超时。冷却会明确返回失败和重试时间，不会把任务挂起 15 分钟。本轮未修改 Java 调度器；若需要自动稍后重试，应由业务队列遵守 `Retry-After` 安排。即使旧 Java 立即重试，Python 也不会在冷却中继续打上游。

## 适用范围与回退

所有状态保存在本 Python 进程内，重启会清空，不要反复重启来跳过冷却。若有多个 Python 服务或备用地址，各进程分别计数，本实现不提供跨解析服务器的全局限速。三个 Java 统一使用同一解析节点时才共用这一份控制。

直接运行 `run.py <链接>`、`parse_links.py` 或自行创建 `OriginalParser` 不经过 HTTP 保护，不适合与生产服务并行批量抓取。浏览器模式仍使用独立匿名页面，本轮没有引入跨请求浏览器复用、登录资料或代理。TOS 文件复用属于 Java 业务逻辑，本轮未改。

回退时先停止服务，使用升级时输出的实际备份路径恢复，再移除本次专用配置：

```bash
systemctl stop douyin-original-parser
tar -xzf /tmp/替换为实际备份文件名.tar.gz -C /opt/software/python
rm -f /etc/systemd/system/douyin-original-parser.service.d/90-request-protection.conf
systemctl daemon-reload
systemctl start douyin-original-parser
```

旧代码不引用的新 `guard.py` 无需删除。备份不包含 Cookie、虚拟环境或浏览器目录。

## 0.5～1秒随机间隔（2026-11-18）

代码默认值、CLI默认值、Linux启动脚本、systemd主配置及请求保护配置均改为`0.5-1`。默认3个实际工作线程，每个线程完整解析任务结束后，在0.5～1秒之间独立随机等待，再启动下一条；这不是总解析耗时，也不是每个内部HTTP请求单独等待。

已有服务的systemd环境变量优先于代码默认值。本次多线程需先更新Python代码。沿用`upgrade.sh --no-units`升级时，应将`/etc/systemd/system/douyin-original-parser.service.d/90-request-protection.conf`中的`Environment=REQUEST_INTERVAL`改为`0.5-1`，并设置`Environment=PARSE_WORKERS=3`，再执行`systemctl daemon-reload`和`systemctl restart douyin-original-parser`。不要用整份主配置覆盖已有详情模式或自定义服务参数。启动日志和健康检查应显示3个工作线程；若还有更高优先级的环境变量配置，以实际运行值为准。
