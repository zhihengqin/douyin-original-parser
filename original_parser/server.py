"""默认仅监听本机的 HTTP 接口，方便业务系统接入。"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import OriginalParser, ParseError, load_credentials


def serve(host="127.0.0.1", port=8765, max_concurrent=2, cookie_file=None):
    if not 1 <= max_concurrent <= 32:
        raise ValueError("解析并发数必须在 1 到 32 之间")
    slots = threading.BoundedSemaphore(max_concurrent)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def send_json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"ok": True, "provider": "douyin-official-source"})
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
            except (ValueError, UnicodeError) as exc:
                self.send_json(400, {"code": "invalid_input", "msg": str(exc), "data": None})
                return
            if not slots.acquire(blocking=False):
                self.send_json(429, {"code": "busy", "msg": "正在处理其他解析，请稍后重试", "data": None})
                return
            try:
                # 外部指定的凭据每次读取，替换文件后不必重启服务。
                cookies, user_agent = load_credentials(cookie_file) if cookie_file else ({}, None)
                with OriginalParser(cookies=cookies, user_agent=user_agent) as parser:
                    self.send_json(200, parser.parse(text, with_probe=with_probe))
            except ParseError as exc:
                status = 400 if exc.code in ("invalid_input", "invalid_url") else 502
                self.send_json(status, {"code": exc.code, "msg": str(exc), "data": None})
            except Exception as exc:
                self.send_json(502, {"code": "upstream_error", "msg": "解析失败：" + type(exc).__name__, "data": None})
            finally:
                slots.release()

    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"原画解析服务：http://{host}:{port}，最大并发 {max_concurrent}，按 Ctrl+C 停止", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
