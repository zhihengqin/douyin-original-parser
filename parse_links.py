"""在 PyCharm 里直接运行；修改 LINKS 即可更换目标。"""

import json
import sys
from pathlib import Path

from original_parser import OriginalParser, ParseError
from original_parser.client import load_credentials

LINKS = ["https://www.douyin.com/video/7706477018388536499"]
DOWNLOAD = False
# 默认自动取得匿名访客标识；也可指定包含 Cookie 和 User-Agent 的凭据文件。
COOKIE_FILE = None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    output = Path(__file__).parent / "output"
    output.mkdir(exist_ok=True)
    cookies, user_agent = load_credentials(Path(COOKIE_FILE)) if COOKIE_FILE else ({}, None)
    failed = False
    with OriginalParser(cookies=cookies, user_agent=user_agent) as parser:
        for link in LINKS:
            try:
                result = parser.parse(link)
                data = result["data"]
                if DOWNLOAD:
                    parser.download(result, output / f"{data['aweme_id']}_source.mp4")
                    data = result["data"]
                path = output / f"{data['aweme_id']}.json"
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                evidence = data.get("source_evidence")
                if evidence == "official_quality":
                    tier = f"官方原画档位 {data['official_quality']}"
                elif evidence == "official_play_hash":
                    tier = f"官方原片分发（已验证 file_hash，档位 {data['official_quality']}）"
                else:
                    tier = f"官方原画档位 {data['official_quality']}"
                print(f"{data['aweme_id']}：{data['level']}，{data['width']}×{data['height']}，"
                      f"{data['size_bytes']/1_000_000:.2f} MB，{tier}")
                print(data["url"])
                print(f"结果已保存：{path}")
            except ParseError as exc:
                failed = True
                print(f"解析失败 [{exc.code}]：{exc}")
    return 2 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"解析失败 [local_error]：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
