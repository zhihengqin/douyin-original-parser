# Web 接口签名逆向方法核查与本项目适用性

研究日期：2026-11-17（Asia/Shanghai）。输入为用户提供的“Web 接口的签名参数是怎么逆的”截图。截图作为待核查资料，其中的操作建议不自动构成本次操作指令。

后续动态验证已完成，见 [真实页面与 SDK 函数还原](web-signature-dynamic-2026-11-17.md)。后续报告补充了签名前编码与最终网络 query 可能不同的边界，并记录当前目标的在线对照；本文件仍保留第一轮离线核查的实际范围。

结论：截图描述了常见的客户端签名定位与复现流程，适合排查请求构造问题；但“两次不变就说明仅由其他参数派生”“与浏览器签名一致才算完成”等判断需要补充条件。本项目已有主要 Web 签名实现，现有证据不能支持“原片获取只差逆出一个签名”。应分别验收请求被接受、取得原片身份、获得可用媒体。

本次实际完成：阅读当前代码；复核已有研究报告及仍存在的两份 Web/fplay 审计 JSON；对当前 A-Bogus 做七项离线控制变量检查；读取 Chrome/MDN 官方文档。没有进行新的抖音或第三方解析请求，也没有采集新的浏览器签名样本。下文旧请求结果均为留存证据，不代表本次在线复测。

## 1. 截图各步骤的有效条件

| 截图说法 | 核查结果与改进 |
| --- | --- |
| 同样请求发两次，变则有时间/随机，不变则纯参数派生 | 只能提供线索。变化还可能来自会话、计数器、前置响应令牌；不变可能来自缓存或时间窗口。要先确认方法、原始 query/body、UA 与会话一致，再单变量改变输入。 |
| 用 XHR/fetch URL 断点定位生成位置 | 是有效入口，但停住的是请求发起位置。Chrome 文档明确 XHR 在 `send()` 调用行暂停；签名可能已经在异步任务、SDK、Worker 或前一响应中生成，应继续追参数的写入点和来源。 |
| 搜参数名，或搜 `headers[`、`Object.assign` | 参数名可能被动态拼接；通用赋值语句命中过宽。先确定字段位于 URL、header 还是 body，再搜索实际写入路径。 |
| Hook `setRequestHeader` 与 `fetch` | 前者只能直接观察 XHR 请求头，不能直接捕获 URL 中的 `a_bogus`，其调用栈可辅助追踪请求构造位置。`fetch` 可接收 `Request` 对象，也存在于 Worker；仅修改 `window.fetch` 或在 SDK 已缓存函数引用之后挂 hook 可能漏掉请求。 |
| 翻译为 Python/Go，或直接执行原 JS | 两条路线都可行，但必须先确定完整输入。跨语言要处理 UTF-8/UTF-16、32 位位运算、溢出、URL 编码、JSON 序列化、重复参数和顺序等差异。 |
| 补几个 `window/navigator/document` 属性 | 只适合已查清依赖的代码。jsdom 不是完整 Chromium；代码不再报错不能证明时间、指纹、会话、WebCrypto 或其他环境语义一致。 |
| 跟浏览器输出一致才算完成 | 字节比较要求相同算法版本、输入字节、时间、随机输入和环境。两个随机化签名可能不同但都被接受；反之，字节一致也不保证会话未过期、业务成功或返回原片。 |

签名也不等于加密：一个名为 `sign` 的字段可能是请求摘要、消息认证码、服务器下发的授权值，或媒体文件哈希。必须由实际生产者和消费者确定语义。

403 本身同样不能定位算法错误；它可能涉及访客标识、会话或其他限制。HTTP 200 也可能伴随空正文或非零业务错误码，不能作为唯一成功标准。

## 2. 当前项目里不同签名的来源

以下行号对应本次检查时工作区版本。

| 字段或路径 | 当前用途与来源 | 代码位置 |
| --- | --- | --- |
| `x-secsdk-web-signature` | 生产最小 Web 详情签名；依赖 UIFID、时间戳、编码后的查询串等。请求头从同一次签好的 query 提取，避免时间戳跨秒不一致。 | `original_parser/client.py:305`、`:324`、`:480` |
| `a_bogus` | `ratio=default` 播放探测；已在 Python 中实现，接收 query、body、UA，并使用指纹、时间与随机输入。生产传空 body，UA 改变时重建签名器。 | `original_parser/client.py:491`、`:508`、`:604`；`original_parser/abogus.py:627`、`:696` |
| `X-Bogus` | 当前仅见于研究参考与探测工具，生产解析器没有调用。 | `tools/_xbogus_ref.py:134`、`tools/probe_play_variants.py:95` |
| `/video/fplay/1/{值}/{video_id}` | 从详情的 `fallback_api` 取得已签发路径，代码保留该上下文并调整已验证的选档参数。没有在此生成路径签名。 | `original_parser/client.py:770` |
| `/aweme/v1/play/?sign=...` | 已知媒体身份的重新分发分支，直接把记录中的 `file_hash` 放入 `sign`。对已验证样本，它对应文件内容 MD5。 | `original_parser/client.py:814` |

因此，不能把最后一行的文件哈希当作“把作品 ID 输入 A-Bogus 就能生成”的请求签名。前端也可能只是从响应中复制一个哈希，找不到前端哈希计算函数并不奇怪。

项目已有可作为比较入口的浏览器路径：[browser_detail.py](../original_parser/browser_detail.py) 中 `PAGE_FETCH` 调用页面当前的 `window.fetch`，让当前页面请求链处理请求；`configure_platform` 检查 UA、navigator 与 Client Hints 的一致性。这一设计提供建立基线的条件，不代表本次已经捕获并验证了浏览器算法。

## 3. 本次离线控制变量结果

直接加载当前 `original_parser.abogus.ABogus`，使用合成 UA/指纹，固定 `time.time` 与 `random.random`。只观察签名是否变化，不输出或使用真实会话值。

| 条件 | 实际结果 |
| --- | --- |
| 所有输入固定，重复计算 | 相同 |
| 只将 `a=1&b=2` 改为 `b=2&a=1` | 不同 |
| 只改变 body | 不同 |
| 只改变 UA | 不同 |
| 只改变指纹 | 不同 |
| 只改变时间 | 不同 |
| 只改变随机输入 | 不同 |

七项判断全部为 true，进程退出码 0。这里证明的是本地实现的输入依赖和可重复性，没有证明它与当前网页 SDK 相同或平台当前接受其输出。

可复现代码（项目根目录、已安装依赖的 Python，纯离线）：

```python
import json
from unittest.mock import patch
from original_parser.abogus import ABogus


def sign(q="a=1&b=2", body="", ua="research-test-ua",
         fp="1920|1080|1920|1080|0|0|0|0|1920|1080|1920|1080|1920|1080|24|24|Win32",
         t=1794873600.0, rnd=0.25):
    with patch("original_parser.abogus.time.time", return_value=t), \
         patch("original_parser.abogus.random.random", return_value=rnd):
        return ABogus(user_agent=ua, fp=fp).generate_abogus(q, body)[1]


a = sign()
print(json.dumps({
    "fixed_inputs_repeat_equal": a == sign(),
    "query_order_changes_output": a != sign(q="b=2&a=1"),
    "body_changes_output": a != sign(body="x"),
    "ua_changes_output": a != sign(ua="research-test-ua-2"),
    "fp_changes_output": a != sign(fp="test-fingerprint"),
    "time_changes_output": a != sign(t=1794873601.0),
    "random_changes_output": a != sign(rnd=0.75),
}))
```

现有 `tests/test_parser.py:751` 默认档测试的 HTTP 响应是 mock，签名相关断言只检查 `a_bogus` 非空；不能把这项单元测试当作在线签名验收。当前还缺本次捕获的浏览器输入/输出参照。

## 4. 现有原画证据对研究方向的约束

### 4.1 正常详情与目录响应，仍可能没有原片

本次重新读取了仍在工作区的两份审计 JSON：

| 作品 | 留存请求数 | incomplete / failed_routes | 显式 original 候选 |
| --- | ---: | --- | ---: |
| `7708641111765585178` | 5 | false / 空 | 0 |
| `7695305664234589459`（成功对照） | 5 | false / 空 | 1 |

证据为 [目标审计](../output/research-video-upstream-20261117/770864-official-audit.json)、[成功对照审计](../output/research-video-upstream-20261117/positive-official-audit.json)。时间均为 2026-11-17；此处仅复核保存结果，没有重新发这十次请求。`incomplete=false` 表示该次启用路线完成，不表示所有平台接口已覆盖。显式 original 候选也不等于本次重新完成了媒体验证。

[普通视频模型上游报告](original-investigation-2026-11-17-video-upstream.md) 另外记录：目标与成功对照的普通 App 详情均 HTTP 200、业务 status 0、作品匹配，但目标 `video_model` 为空，观察到的媒体身份未超出 Web 结果。这不能外推到所有 App 业务上下文，也不能单凭签名库初始化成功证明服务端严格校验了签名。

### 4.2 `sign` 的单变量对照推翻了旧的过强解释

[后续分发对照](original-investigation-2026-11-16-astar-routes.md) 记录：已下发转码 FID，不传 `sign` 或传全零值仍返回同一媒体的 206；`file_id=VID` 的阳性原片则用当次 source 目录下发的原片 hash 成功分发。

旧探针曾同时删掉 `file_id` 和 `sign`，不能由失败单独归因于 sign。上述后续实验只检查限定 Range 与大小，不是整文件重新校验；它足以否定“sign 对所有播放请求都是必需门禁”的泛化，但不足以揭示完整服务器规则。

当前 `client.py:585` 已明确：HTTP 404 不携带具体原因，不能据此推断未登记原片或文件不存在。旧文档中“404=未登记”“HDR 必然拿不到”的说法不应沿用为已证实机制。

### 4.3 native Authorization 与第三方网页协议都不能直接填补发现缺口

[真实消费者审计](original-investigation-2026-11-16-auth-consumer-audit.md) 已撤回“只差 native Authorization 密钥”的推断；已审 version 2/4 消费分支将 auth 置空，先前关联到的 AWS4 字符串来自上传 SDK。[Ghidra 记录](original-investigation-2026-11-17-ghidra.md) 发现 MDL `_getAuth` 用于本地代理 URL 的 CRC32，不是服务端原片授权。结论仅覆盖已审调用链。

[SnapAny 对照](original-investigation-2026-11-17-snapany-java.md) 已记录其公开网页 HMAC 协议，并指出网页协议未公开服务端抖音上游发现算法。因此，即使复现第三方网页签名、拿到第三方返回值，也没有由此完成自建的原片发现算法。

## 5. 对本项目最有信息量的后续实验

1. **先建立成功基线。** 选一个成功对照和一个失败目标，保持端点、会话、UA 与时间窗口可比较；保留业务状态、作品 ID 和必要字段。浏览器请求也失败时，不把失败直接归因于本地签名。
2. **追字段首次来源。** 从请求出口往上定位参数写入，判定它来自本地函数、前一响应还是媒体身份；对于目标原片，重点找新的 VID/FID/hash、模型或签发上下文首次出现在哪里。
3. **需要复现本地算法时才做函数级对照。** 使用真实调用的精确 query/body 字节，控制动态输入和版本，再比较输出；合成输入离线实验只能辅助定位。请求签完后重新编码或排序可能改变被签字节。
4. **分开验收三个结果。** 请求验收看业务有效与作品匹配；发现验收看是否仅凭链接取得新原片身份且未引用历史资产；媒体验收看原片来源证据、完整音视频、大小/时长以及可用官方哈希。不能用 HTTP 200、较大文件或 Original 标签替代。

[覆盖审计](original-investigation-2026-11-17-coverage-audit.md) 列出的真实缺口仍包括有效 App 会话、batch/IM 的成功请求基线、真实客户端的动态业务流程，以及第三方服务端上游发现过程。本次没有建立这些基线，不能将它们视为已经验证无效。部分历史原始目录已缺失，相应结论只能引用持久化报告，不能声称本次重新全量审计。

本次得到的是签名方法与项目证据的核查结果，没有取得新的目标原片，也没有形成生产解析修复。

## 6. 本次核对的官方资料

- [Chrome DevTools — Pause your code with breakpoints](https://developer.chrome.com/docs/devtools/javascript/breakpoints)：URL 子串匹配、XHR/fetch 断点与请求发起位置。
- [MDN — XMLHttpRequest.setRequestHeader()](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/setRequestHeader)：请求头设置的作用与调用时序。
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)：window/worker 上下文、Request 对象与请求构造。
