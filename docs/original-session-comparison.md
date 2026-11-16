# 登录前后原片目录对照

此工具用于验证同一作品在不同会话下是否会下发不同原片目录。具体效果按每次实际响应判断；工具不是两个旧素材目标已经修复的声明。

2026-11-16 先运行了匿名端到端校准：`7695305664234589459` 取得 528,422,694 字节 original，实际大小、时长、分辨率、视频和音频轨道校验通过；`7707196543073275177` 的两个选择器仍各列 8 个普通档；`7704677676878925119` 详情仍为 `series_control_filter`。该次校准仅包含匿名阶段。

同日用户已完成一次实际登录对照，报告为 `output/session-compare-20261116-145118.json`：770719 三阶段的文件身份及全部档位完全一致，770467 登录后仍被相同详情过滤；两个目标均未恢复。阳性在登录后及随后全新匿名阶段通过原片媒体检查，首次匿名阶段详情 HTTP 403，因此完整对照总标签仍为 `inconclusive`。具体证据和结论边界见[本次登录结果](original-investigation-2026-11-16-login-result.md)；无需仅为这一总标签再重复登录。

## 运行

Windows 可以直接双击项目根目录的 `compare_original_sessions.cmd`。它会定位项目自己的 Python，执行结束后保留终端窗口。

如果当前打开的是 CMD（提示符形如 `C:\Users\EDY>`），可从任意目录执行下面这一整行，路径使用双引号：

```bat
"D:\ProjectPy\douyin-original-parser\.venv\Scripts\python.exe" "D:\ProjectPy\douyin-original-parser\tools\compare_original_sessions.py" --show-verified-url
```

CMD 不支持 PowerShell 的前置 `&` 调用语法，也不会将单引号识别为路径引号。

在项目根目录的 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe tools\compare_original_sessions.py --show-verified-url
```

工具使用项目现有 Playwright/Chromium 创建新的临时浏览器会话，默认对照两个目标，并自动加入上述成功样本。

1. 自动测试匿名会话。
2. 在新开的浏览器中手动登录抖音，完成后回到终端按回车；输入 `q` 可取消，已完成的匿名报告仍保留。
3. 在同一浏览器上下文测试相同作品，然后用另一份全新匿名上下文再次测试，检查期间是否发生目录变化。
4. 自动关闭浏览器，报告保存到项目 `output/session-compare-日期时间.json`，终端显示完整路径。

`--show-verified-url` 只在官方 original/source 候选通过实际媒体校验后，向终端显示临时下载地址。报告不保存地址。省略该选项则终端也不显示地址。

可以指定其它作品和报告路径：

```powershell
.\.venv\Scripts\python.exe tools\compare_original_sessions.py 7707196543073275177 --report output\my-session-comparison.json
```

只跑匿名基线，不等待登录：

```powershell
.\.venv\Scripts\python.exe tools\compare_original_sessions.py --anonymous-only
```

已有报告文件不覆盖；需要再次执行时更换路径或使用默认时间戳文件名。

## 如何读结果

| 字段／结果 | 含义 |
| --- | --- |
| `original_verified=true` | 官方原片候选已通过实际媒体校验 |
| `valid_directory_without_original` | 两个选择器都返回身份匹配的有效目录，但没有 original/source |
| `model_not_supplied` | 返回了匹配作品的详情，但没有播放模型 |
| `session_cookie_present=true` | 观察到会话 Cookie；不单独证明账号或原片权限有效 |
| `original_only_in_session_after_login` | 三阶段控制样本都有效，两个匿名阶段没有原片，而登录后的会话取得了原片；证明本次存在会话相关差异，尚不能推出具体服务端授权规则 |
| `no_original_in_tested_sessions` | 三阶段结果都具备解释条件，但均未取得原片 |
| `inconclusive` | 控制失败、目标无详情、网络／媒体校验异常、会话标记缺失或对照未完成，不能判断登录影响 |

退出码 0 表示诊断流程执行完成，不等于目标原片恢复；原片是否取得应看每个作品的 `original_verified`。

## 数据和范围

凭据不导出、不读取个人浏览器配置、不保存 storage state；页面取得的 Cookie 仅在当前进程内传给现有解析器。报告只记录固定字段：作品和视频身份、官方文件身份、档位、大小、尺寸、过滤标记及错误码，不保存 Cookie、token、密钥、作者信息、原始详情或临时地址。

诊断子类禁用了历史原片 catalog，并直接调用现有 `source_streams()` 与 `probe()`，不调用会写入 catalog 的 `parse()`。因此成功来自本次官方响应及媒体检查。普通档不改标为原片，生产 CLI、HTTP 服务和 `parse_links.py` 不受该工具影响。

七项回归检查覆盖普通目录、catalog 禁用、敏感字段剔除、媒体校验失败、后续候选成功、身份不匹配及会话对照误判。匿名实测报告为本机 `output/session-compare-anonymous-validation-20261116.json`；该目录被 Git 忽略。
