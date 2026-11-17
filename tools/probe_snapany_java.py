"""复现 NiKa Java 的小帅调用协议；明确区分历史查询和新解析，不认定原画质量。

凭据读取环境变量或指定 Java 文件的默认配置，不写入结果和日志。
resolve 会消耗第三方解析额度；每次执行只发一次请求，不自动重试。
完整回包含临时媒体地址，只写入本地 output 目录。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JAVA = Path(
    "D:/Project/NiKa/nika-modules/nika-basic/src/main/java/com/nika/basic/"
    "content/dxj/client/SnapanyVideoParserClient.java"
)


def load_config(java_path: Path) -> tuple[str, str, str]:
    names = ("base-url", "api-key", "api-secret")
    env_names = ("SNAPANY_BASE_URL", "SNAPANY_API_KEY", "SNAPANY_API_SECRET")
    source = None
    values = []
    for name, env_name in zip(names, env_names):
        value = os.environ.get(env_name, "").strip()
        if not value:
            if source is None:
                source = java_path.read_text(encoding="utf-8")
            match = re.search(
                r"\$\{nika\.video-parser\.snapany\." + re.escape(name) + r":([^}]*)\}",
                source,
            )
            value = match.group(1).strip() if match else ""
        if not value:
            raise ValueError(f"缺少配置：{env_name}")
        values.append(value)
    base, key, secret = values
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("接口根地址无效")
    return base.rstrip("/"), key, secret


def request_id(url: str) -> str:
    return "nika_" + hashlib.md5(url.strip().encode("utf-8")).hexdigest()


def summarize(payload: dict) -> dict:
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {"code": payload.get("code"), "data_type": type(data).__name__}
    result = {"code": payload.get("code"), "data_fields": list(data)}
    if "video_list" in data:
        result["vid_present"] = bool(data.get("vid"))
        result["videos"] = []
        for row in data.get("video_list") or []:
            url = urlsplit(row.get("url") or "")
            marker = "/video/tos/cn/"
            result["videos"].append({
                "quality_claim": row.get("quality"),
                "level_claim": row.get("level"),
                "declared_size": row.get("size"),
                "host": url.hostname,
                "object": url.path.split(marker, 1)[1] if marker in url.path else None,
                "query_names": sorted({piece.split("=", 1)[0] for piece in url.query.split("&") if piece}),
                "original_verified": False,
            })
    for key in ("balance", "total_used", "cost_per_request", "remaining_requests"):
        if key in data:
            result[key] = data[key]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("result", "usage", "resolve"))
    parser.add_argument("--url", help="作品链接；新入口请求 ID 为 nika_ 加链接 MD5")
    parser.add_argument("--request-id", help="精确历史 ID；旧快照入口使用作品 ID")
    parser.add_argument("--java-source", type=Path, default=DEFAULT_JAVA)
    parser.add_argument("--force-refresh", action="store_true", help="只用于显式 resolve")
    args = parser.parse_args()
    if args.action != "usage" and not (args.url or args.request_id):
        parser.error("result/resolve 需要 --url 或 --request-id")
    if args.action == "resolve" and not args.url:
        parser.error("resolve 需要 --url")
    if args.force_refresh and args.action != "resolve":
        parser.error("--force-refresh 仅适用于 resolve")

    base, key, secret = load_config(args.java_source)
    rid = args.request_id or (request_id(args.url) if args.url else None)
    body = ""
    params = None
    method = "GET"
    if args.action == "resolve":
        method = "POST"
        body = json.dumps({"url": args.url.strip(), "force_refresh": args.force_refresh,
                           "request_id": rid}, ensure_ascii=False, separators=(",", ":"))
    elif args.action == "result":
        params = {"request_id": rid}
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode("utf-8"),
                         f"{key}.{timestamp}.{body}".encode("utf-8"),
                         hashlib.sha256).hexdigest()
    response = requests.request(
        method, base + "/api/v1/" + args.action, params=params,
        data=body.encode("utf-8") if body else None,
        headers={"X-API-Key": key, "X-Timestamp": timestamp, "X-Signature": signature,
                 "Content-Type": "application/json"},
        timeout=(15, 120), allow_redirects=False,
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("接口没有返回 JSON 对象")
    output = ROOT / "output" / "snapany-java-probes"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"{time.time_ns()}-{args.action}"
    raw_path = output / f"{stem}.private.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"http_status": response.status_code, "action": args.action,
               "response": summarize(payload), "private_response": str(raw_path)}
    (output / f"{stem}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if response.status_code == 200 and payload.get("code") == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, requests.RequestException) as error:
        # 异常正文可能包含签名地址，只输出类型。
        print(f"调用未完成：{type(error).__name__}", file=sys.stderr)
        sys.exit(2)
