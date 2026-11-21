import argparse
import json
import logging
import sys
from pathlib import Path

import requests

from .client import OriginalParser, ParseError, load_credentials, require_single_original


def parse_interval(value: str) -> tuple[float, float]:
    """解析间隔配置：``0.5-1`` 表示区间，``1`` 表示固定间隔。"""
    text = str(value).strip()
    if not text:
        raise ValueError("--request-interval 不能为空，例如 0.5-1")
    lower, separator, upper = text.partition("-")
    if not separator:
        seconds = float(text)
        return (seconds, seconds)
    return (float(lower.strip()), float(upper.strip()))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="抖音原画解析：官方取址、地址还原、完整 MP4 校验")
    ap.add_argument("url", nargs="?", help="视频链接、分享文案或作品 ID")
    ap.add_argument("--download", type=Path, help="保存已校验的单文件 MP4，不覆盖已有文件")
    ap.add_argument("--reference", type=Path, help="下载后与本地对照文件做 SHA-256 比较")
    ap.add_argument("--json", type=Path, dest="json_path", help="保存完整解析结果")
    ap.add_argument("--allow-external", action="store_true", dest="allow_external",
                    help="允许使用本地已核对过的外部来源原片身份（仍需官方分发重签与媒体校验）；"
                         "等价于设置 DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1")
    ap.add_argument("--cookie-file", type=Path,
                    help="Cookie 文件或 dtk-parse credentials.json（当前抖音接口需要 UIFID_TEMP）")
    ap.add_argument("--register-original", metavar="原片直链",
                    help="把一条已有的原片直链核验后登记为本地原片身份记录：核对它是完整 MP4、"
                         "时长与作品详情一致、不是平台转码档，再用整文件 MD5 打官方分发确认平台认可。"
                         "登记后属于外部来源，仍需 --allow-external 才参与取址")
    ap.add_argument("--detail-mode", choices=("http", "browser"), default="http",
                    help="详情获取方式；升级时保持原服务使用的模式")
    ap.add_argument("--browser-profile", choices=("current", "native", "windows"), default="windows")
    ap.add_argument("--serve", action="store_true", help="启动本地 HTTP 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--max-concurrent", type=int, default=6, help="HTTP 同时受理请求数，包含执行中及等待中的请求")
    ap.add_argument("--parse-workers", type=int, default=3, help="实际解析工作线程数，默认3，相同作品请求自动合并")
    ap.add_argument("--request-interval", default="0.5-1", metavar="下限-上限",
                    help="每个工作线程完成任务后的等待区间秒数，例如 0.5-1 表示在 0.5 到 1 秒之间随机；"
                         "单个数字表示固定间隔，默认 0.5-1")
    ap.add_argument("--cache-ttl", type=float, default=300, help="HTTP 成功缓存上限秒数，0 关闭缓存")
    ap.add_argument("--cache-max-entries", type=int, default=128)
    ap.add_argument("--queue-size", type=int, default=6, help="HTTP 等待执行的不同任务上限")
    ap.add_argument("--queue-wait-timeout", type=float, default=150, help="HTTP 等待排队及结果的总秒数")
    ap.add_argument("--failure-threshold", type=int, default=3, help="限制类错误触发暂停的次数")
    ap.add_argument("--cooldown-seconds", type=float, default=900, help="触发暂停后的冷却秒数")
    args = ap.parse_args(argv)
    if not 1 <= args.max_concurrent <= 32:
        ap.error("--max-concurrent 必须在 1 到 32 之间")
    if args.detail_mode == "browser" and args.cookie_file:
        ap.error("浏览器页面模式不能同时指定 --cookie-file")
    if args.serve:
        from .server import serve
        from .guard import GuardConfig
        try:
            config = GuardConfig(interval_range=parse_interval(args.request_interval), worker_count=args.parse_workers,
                                 cache_ttl=args.cache_ttl,
                                 cache_max_entries=args.cache_max_entries, max_pending=args.queue_size,
                                 wait_timeout=args.queue_wait_timeout, failure_threshold=args.failure_threshold,
                                 cooldown=args.cooldown_seconds)
            if args.cookie_file:
                load_credentials(args.cookie_file)
            serve(args.host, args.port, max_concurrent=args.max_concurrent, cookie_file=args.cookie_file,
                  detail_mode=args.detail_mode, browser_profile=args.browser_profile, guard_config=config,
                  allow_external_asset_recovery=args.allow_external or None)
            return 0
        except (ParseError, OSError, ValueError) as exc:
            print(json.dumps({"code": getattr(exc, "code", "local_error"), "msg": str(exc), "data": None},
                             ensure_ascii=False), file=sys.stderr)
            return 2
    if not args.url:
        ap.error("请提供视频链接，或使用 --serve 启动本地服务")
    if args.reference and not args.download:
        ap.error("--reference 需要同时指定 --download，完整下载后才能验证文件一致性")
    if args.register_original and (args.download or args.reference or args.json_path):
        ap.error("--register-original 只做身份登记，不能与 --download/--reference/--json 同用")
    try:
        cookies, user_agent = load_credentials(args.cookie_file) if args.cookie_file else ({}, None)
        with OriginalParser(cookies=cookies if args.cookie_file else None, user_agent=user_agent,
                            auto_guest=args.cookie_file is None, detail_mode=args.detail_mode,
                            browser_profile=args.browser_profile,
                            allow_external_asset_recovery=args.allow_external or None) as parser:
            if args.register_original:
                outcome = parser.register_external_original(args.url, args.register_original)
                print(outcome["record"]["aweme_id"])
                return 0
            result = parser.parse(args.url)
            data = require_single_original(result)
            if args.download:
                parser.download(result, args.download, reference=args.reference)
                data = require_single_original(result)
        if data.get("reference_match") is False:
            print("下载文件与指定原件不一致。", file=sys.stderr)
            return 3
        if args.json_path:
            args.json_path.parent.mkdir(parents=True, exist_ok=True)
            args.json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(args.download if args.download else data["url"])
        return 0
    except (ParseError, OSError, ValueError, requests.RequestException) as exc:
        print(json.dumps({"code": getattr(exc, "code", "local_error"), "msg": str(exc), "data": None},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
