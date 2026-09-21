import argparse
import json
import sys
from pathlib import Path

import requests

from .client import OriginalParser, ParseError, load_credentials


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="抖音原画解析：官方取址、地址还原、完整 MP4 校验")
    ap.add_argument("url", nargs="?", help="视频链接、分享文案或作品 ID")
    ap.add_argument("--download", type=Path, help="下载到指定 MP4 文件，不覆盖已有文件")
    ap.add_argument("--reference", type=Path, help="下载后与本地对照文件做 SHA-256 比较")
    ap.add_argument("--json", type=Path, dest="json_path", help="保存完整解析结果")
    ap.add_argument("--url-only", action="store_true", help="仅在控制台输出播放地址")
    ap.add_argument("--no-probe", action="store_true", help="跳过远程 MP4 大小和轨道校验")
    ap.add_argument("--cookie-file", type=Path,
                    help="Cookie 文件或 dtk-parse credentials.json（当前抖音接口需要 UIFID_TEMP）")
    ap.add_argument("--serve", action="store_true", help="启动本地 HTTP 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--max-concurrent", type=int, default=2, help="HTTP 服务最大并发数，默认 2；三实例共享可设为 6")
    args = ap.parse_args(argv)
    if not 1 <= args.max_concurrent <= 32:
        ap.error("--max-concurrent 必须在 1 到 32 之间")
    if args.serve:
        from .server import serve
        try:
            if args.cookie_file:
                load_credentials(args.cookie_file)
            serve(args.host, args.port, max_concurrent=args.max_concurrent, cookie_file=args.cookie_file)
            return 0
        except (ParseError, OSError, ValueError) as exc:
            print(json.dumps({"code": getattr(exc, "code", "local_error"), "msg": str(exc), "data": None},
                             ensure_ascii=False), file=sys.stderr)
            return 2
    if not args.url:
        ap.error("请提供视频链接，或使用 --serve 启动本地服务")
    if args.reference and not args.download:
        ap.error("--reference 需要同时指定 --download，完整下载后才能验证文件一致性")
    try:
        cookies, user_agent = load_credentials(args.cookie_file) if args.cookie_file else ({}, None)
        with OriginalParser(cookies=cookies, user_agent=user_agent) as parser:
            result = parser.parse(args.url, with_probe=not args.no_probe)
            if args.download:
                parser.download(result, args.download, reference=args.reference)
        if args.json_path:
            args.json_path.parent.mkdir(parents=True, exist_ok=True)
            args.json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        data = result["data"]
        if args.url_only:
            print(data["url"])
        else:
            print(f"{data['desc']}\n作者：{data['author']}\n作品：{data['aweme_id']}")
            print(f"原画：{data['width']}×{data['height']}，{data['size_bytes']:,} 字节 "
                  f"({data['size_bytes']/1_000_000:.2f} MB)，{data['duration_seconds']:.3f} 秒")
            print("来源：抖音官方 source 档位；未使用第三方解析服务")
            print("媒体校验：" + ("通过，包含视频与音频轨道" if data['probe'] else "已跳过"))
            print("播放地址：" + data["url"])
            if data.get("download"):
                record = data["download"]
                print("下载文件：" + record["path"])
                print("SHA-256：" + record["sha256"])
                if record["reference_match"] is not None:
                    print("对照文件：" + ("字节一致" if record["reference_match"] else "不一致，请核对链接和对照文件"))
        return 3 if data.get("reference_match") is False else 0
    except (ParseError, OSError, ValueError, requests.RequestException) as exc:
        print(json.dumps({"code": getattr(exc, "code", "local_error"), "msg": str(exc), "data": None},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
