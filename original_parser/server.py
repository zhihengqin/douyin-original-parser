"""HTTP 接口；所有实例的上游请求共用排队、缓存和失败暂停。"""

import hashlib
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import OriginalParser, ParseError, load_credentials, resolve_id_local
from .guard import GuardConfig, GuardError, RequestGuard

logger = logging.getLogger(__name__)


def public_result(result: dict) -> dict:
    """对外只返回最高画质链接，其余档位、镜像和探测信息不进入回包。"""
    data = result.get("data")
    if not isinstance(data, dict):
        return result
    return {"code": result.get("code"), "msg": result.get("msg"),
            "data": {"url": data.get("url")}}


def serve(host="127.0.0.1", port=8765, max_concurrent=6, cookie_file=None,
          detail_mode="http", browser_profile="windows", guard_config=None):
    if not 1 <= max_concurrent <= 32:
        raise ValueError("同时受理的 HTTP 请求数必须在 1 到 32 之间")
    if detail_mode not in ("http", "browser") or browser_profile not in ("current", "native", "windows"):
        raise ValueError("不支持的详情模式或浏览器配置")
    if detail_mode == "browser" and cookie_file is not None:
        raise ValueError("浏览器页面模式不能同时指定外部 Cookie")
    config = guard_config or GuardConfig()
    slots = threading.BoundedSemaphore(max_concurrent)
    guard = RequestGuard(config)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def send_json(self, status, data, *, retry_after=None):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if retry_after is not None:
                    self.send_header("Retry-After", str(max(1, int(retry_after))))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                logger.info("http_client_disconnected status=%s", status)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"ok": True, "provider": "douyin-official-source",
                                     "protection": guard.snapshot()})
            else:
                self.send_json(404, {"code": "not_found", "msg": "接口不存在", "data": None})

        def do_POST(self):
            if self.path not in ("/parse", "/api/v1/resolve"):
                self.send_json(404, {"code": "not_found", "msg": "接口不存在", "data": None})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > 8192 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("请求大小不符合要求")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("需要 JSON 对象")
                text = payload.get("url") or payload.get("share_text")
                if not isinstance(text, str) or not text.strip() or len(text) > 4096:
                    raise ValueError("请提供有效 url 或 share_text")
                with_probe = payload.get("with_probe", True)
                if not isinstance(with_probe, bool):
                    raise ValueError("with_probe 必须为布尔值")
                force_refresh = payload.get("force_refresh", False)
                if not isinstance(force_refresh, bool):
                    raise ValueError("force_refresh 必须为布尔值")
                aweme_id, normalized_url = resolve_id_local(text)
            except (ValueError, UnicodeError) as exc:
                self.send_json(400, {"code": "invalid_input", "msg": str(exc), "data": None})
                return
            except ParseError as exc:
                self.send_json(400, {"code": exc.code, "msg": str(exc), "data": None})
                return
            if not slots.acquire(blocking=False):
                self.send_json(429, {"code": "busy", "msg": "解析请求较多，请稍后重试", "data": None},
                               retry_after=max(1, config.interval_upper))
                return
            try:
                # 每次读取外部文件；凭据变化后隔离缓存和在途请求，密钥不进入日志。
                cookies, user_agent = load_credentials(cookie_file) if cookie_file else (None, None)
                credential_scope = "auto"
                if cookie_file:
                    credential_scope = hashlib.sha256(json.dumps(
                        [cookies, user_agent], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
                key = (credential_scope, "id" if aweme_id else "link",
                       aweme_id or normalized_url, with_probe)

                def parse_once():
                    # 此函数只在唯一工作线程运行；短链的跳转也受统一排队控制。
                    with OriginalParser(cookies=cookies, user_agent=user_agent,
                                        auto_guest=cookie_file is None,
                                        detail_mode=detail_mode, browser_profile=browser_profile,
                                        refresh_guest_on_rejection=False) as parser:
                        return parser.parse(aweme_id or normalized_url, with_probe=with_probe)

                result = guard.run(key, parse_once, force_refresh=force_refresh)
                self.send_json(200, public_result(result))
            except GuardError as exc:
                status = 503 if exc.code == "upstream_cooldown" else 429
                self.send_json(status, {"code": exc.code, "msg": str(exc), "data": None,
                                        "retry_after_seconds": exc.retry_after}, retry_after=exc.retry_after)
            except ParseError as exc:
                status = 400 if exc.code in ("invalid_input", "invalid_url") else 502
                self.send_json(status, {"code": exc.code, "msg": str(exc), "data": None})
            except Exception as exc:
                logger.warning("parse_failed category=%s", type(exc).__name__)
                self.send_json(502, {"code": "upstream_error", "msg": "解析失败：" + type(exc).__name__, "data": None})
            finally:
                slots.release()

    try:
        with ThreadingHTTPServer((host, port), Handler) as server:
            print(f"原画解析服务：http://{host}:{port}，最多受理 {max_concurrent} 个请求，上游串行，按 Ctrl+C 停止", flush=True)
            logger.info("detail_mode=%s browser_profile=%s credential_mode=%s", detail_mode, browser_profile,
                        "external_file" if cookie_file else "auto_guest")
            logger.info("protection interval=%s-%ss cache_ttl=%ss pending=%s wait=%ss threshold=%s cooldown=%ss",
                        config.interval_range[0], config.interval_range[1],
                        config.cache_ttl, config.max_pending,
                        config.wait_timeout, config.failure_threshold, config.cooldown)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        guard.close()
