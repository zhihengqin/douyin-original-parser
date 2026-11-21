"""在 PyCharm 里直接运行；修改 LINKS 即可更换目标。"""

import sys
from pathlib import Path

from original_parser import OriginalParser, ParseError
from original_parser.client import load_credentials, require_single_original, resolve_id_local

LINKS = ["https://www.douyin.com/video/7707954213745085746"]
DOWNLOAD = False
OUTPUT_DIR = Path(__file__).parent / "output"
# 默认自动取得匿名访客标识；也可指定包含 Cookie 和 User-Agent 的凭据文件。
COOKIE_FILE = None
# 历史已核对过的外部来源原片身份默认不参与取址；设 True 或命令行加 --allow-external
# 才会使用（仍走官方分发重签与 MP4 媒体校验）。None 表示跟随环境变量
# DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY。
ALLOW_EXTERNAL = None


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else list(argv)
    if any(item.startswith("-") and item != "--allow-external" for item in argv):
        print("参数无效；只支持作品链接、作品 ID 和 --allow-external。", file=sys.stderr)
        return 2
    allow_external = True if "--allow-external" in argv else ALLOW_EXTERNAL
    links = [item for item in argv if item != "--allow-external"] or LINKS
    cookies, user_agent = load_credentials(Path(COOKIE_FILE)) if COOKIE_FILE else ({}, None)
    failed = False
    with OriginalParser(cookies=cookies, user_agent=user_agent,
                        allow_external_asset_recovery=allow_external) as parser:
        for index, link in enumerate(links, 1):
            try:
                result = parser.parse(link)
                data = require_single_original(result)
                if DOWNLOAD:
                    target = OUTPUT_DIR / f"{data['aweme_id']}_source.mp4"
                    downloaded = parser.download(result, target)
                    require_single_original(result)
                    print(downloaded["path"])
                else:
                    print(data["url"])
            except (ParseError, OSError, ValueError) as exc:
                failed = True
                try:
                    work, _ = resolve_id_local(link)
                except (ParseError, ValueError):
                    work = None
                label = work or f"第 {index} 个输入"
                code = exc.code if isinstance(exc, ParseError) else "local_error"
                print(f"{label}：未取得原画 [{code}]", file=sys.stderr)
    return 2 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ParseError):
        print("无法初始化解析器，请检查本地配置。", file=sys.stderr)
        raise SystemExit(2)
