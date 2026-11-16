"""只凭作品链接检查官方目录、MP4 内嵌 VID 和 APK 的 VID 播放接口。

这是只读研究工具，不是原画降级策略。它不读取 catalog、参考文件或外部地址，
不下载 mdat，不保存临时 URL/token，也不会把转码或内嵌 VID 当作原画证明。
SDK URL 构造依据：官方主版 41.1.0 的 X.1flM.apiForFetcher。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import requests
from urllib3.exceptions import HTTPError as TransportError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from original_parser.client import MEDIA_HOSTS, OriginalParser, ParseError, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402
from original_parser.media import inspect_mp4  # noqa: E402

MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_METADATA_REQUESTS = 16
MAX_OBJECTS = 20
MAX_VIDS = 4
VID = re.compile(r"v[A-Za-z0-9]{15,63}")


class DiscoveryParser(OriginalParser):
    """仅为这项实验允许已审计的官方 SDK 目录主机。"""

    def _get(self, url, *, hosts=MEDIA_HOSTS, headers=None):
        if urlsplit(url).hostname == "vod-urls.bytedanceapi.com":
            hosts = (*hosts, "vod-urls.bytedanceapi.com")
        return super()._get(url, hosts=hosts, headers=headers)


def sdk_url(video_id: str) -> str:
    """复现已审计 APK 的默认 MP4 builder；不改其他作品的签名或 token。"""
    if not VID.fullmatch(video_id):
        raise ValueError("invalid_video_id")
    stamp = str(int(time.time()))
    material = (f"ts{stamp}usertoutiaoversion1video{video_id}vtypemp4"
                "17601e2231500d8c3389dd5d6afd08de")
    digest = hashlib.md5(material.encode()).hexdigest()
    query = urlencode({"play_type": "1", "ssl": "1", "device_type": "Pixel 7"})
    return ("https://vod-urls.bytedanceapi.com/video/play/1/toutiao/"
            f"{stamp}/{digest}/mp4/{video_id}?{query}")


def rows_of(data: dict) -> list[dict]:
    rows = data.get("video_list") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        raise ValueError("invalid_video_list")
    return [row for row in rows if isinstance(row, dict)]


def safe_rows(data: dict) -> list[dict]:
    fields = ("quality", "size", "file_id", "file_hash", "codec_type", "vwidth", "vheight")
    return [{key: row.get(key) for key in fields} for row in rows_of(data)]


def inspect_identity(parser: OriginalParser, url: str, declared_size: int) -> dict:
    """只读 ftyp/moov；验证每次 Range 的长度、总大小和请求预算。"""
    stat = {"http_requests": 0, "bytes_read": 0}
    chunks = []

    def read_at(offset: int, length: int) -> bytes:
        nonlocal url
        if (length <= 0 or stat["http_requests"] >= MAX_METADATA_REQUESTS
                or stat["bytes_read"] + length > MAX_METADATA_BYTES):
            raise ValueError("metadata_budget_exceeded")
        with parser._get(url, headers={
                "Range": f"bytes={offset}-{offset + length - 1}",
                "Accept-Encoding": "identity"}) as response:
            stat["http_requests"] += 1
            expected = f"bytes {offset}-{offset + length - 1}/{declared_size}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("range_mismatch")
            try:
                body = response.raw.read(length + 1, decode_content=False)
            except (TransportError, OSError) as exc:
                raise ParseError("network_error", "MP4 元数据读取失败：" + type(exc).__name__) from exc
            if len(body) != length:
                raise ValueError("range_length_mismatch")
            url = response.url
        stat["bytes_read"] += len(body)
        chunks.append(body)
        return body

    if declared_size < 16:
        raise ValueError("invalid_declared_size")
    if read_at(0, 16)[4:8] != b"ftyp":
        raise ValueError("not_mp4")
    media = inspect_mp4(read_at, declared_size)
    # Separate reads must not create a synthetic match at a chunk boundary.
    embedded = {match.decode("ascii") for chunk in chunks
                for match in re.findall(rb"vid\s*:\s*(v[A-Za-z0-9]{15,63})", chunk)}
    return {**stat, "actual_size": declared_size, "media": media,
            "embedded_vids": sorted(embedded)}


def probe(parser: OriginalParser, text: str) -> dict:
    work = parser.resolve_id(text)
    detail = parser.detail(work)
    video = detail.get("video") or {}
    model = video.get("video_model")
    model = json.loads(model) if isinstance(model, str) else model
    video_id = (video.get("play_addr") or {}).get("uri")
    if not isinstance(model, dict) or model.get("video_id") != video_id:
        raise ValueError("missing_or_mismatched_model")
    fallback = model.get("fallback_api")
    fallback = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    part = urlsplit(check_url(fallback, ("snssdk.com",)))
    if not re.fullmatch(r"/video/fplay/1/[a-fA-F0-9]{32}/" + re.escape(video_id), part.path):
        raise ValueError("unexpected_fallback_path")

    # Use the issued fallback unchanged. Do not call source_streams(), which may
    # consult the local original catalog after its ordinary selectors fail.
    reply = parser._json(fallback, stage="官方现有播放目录")
    data = (reply.get("video_info") or {}).get("data") or {}
    if data.get("video_id") != video_id or data.get("status") != 10:
        raise ValueError("fallback_identity_mismatch")
    objects = rows_of(data)
    result = {"aweme_id": work, "current_vid": video_id,
              "catalog_used": False, "reference_used": False,
              "fallback_rows": safe_rows(data), "media_objects": [], "sdk": [],
              "object_limit_reached": False, "objects_omitted": 0,
              "vid_limit_reached": False, "vids_omitted": 0}
    vids = [video_id]
    observed_vids = {video_id}
    seen = set()
    for row in objects:
        identity = row.get("file_hash") or row.get("file_id") or row.get("main_url")
        if identity in seen:
            continue
        seen.add(identity)
        if len(result["media_objects"]) >= MAX_OBJECTS:
            result["object_limit_reached"] = True
            result["objects_omitted"] += 1
            continue
        item = {key: row.get(key) for key in ("quality", "file_id", "file_hash", "size")}
        try:
            url = decode_url(row.get("main_url"), data.get("key_seed") or "")
            item.update(inspect_identity(parser, url, int(row.get("size") or 0)))
            for embedded in item["embedded_vids"]:
                if embedded in observed_vids:
                    continue
                observed_vids.add(embedded)
                if len(vids) < MAX_VIDS:
                    vids.append(embedded)
                else:
                    result["vid_limit_reached"] = True
                    result["vids_omitted"] += 1
        except (ParseError, requests.RequestException, ValueError, TypeError, OSError) as exc:
            item["error_type"] = type(exc).__name__
            if isinstance(exc, ParseError):
                item["error_code"] = exc.code
        result["media_objects"].append(item)

    # One level only: discovered VIDs are candidates for further investigation,
    # not proof of a parent/upload relationship or permission to select a file.
    for candidate in vids:
        item = {"requested_vid": candidate}
        try:
            reply = parser._json(sdk_url(candidate), stage="官方 SDK 播放目录")
            data = (reply.get("video_info") or {}).get("data") or {}
            item.update(status=data.get("status"), response_vid=data.get("video_id"))
            if data.get("video_id") != candidate or data.get("status") != 10:
                raise ValueError("sdk_identity_mismatch")
            item["rows"] = safe_rows(data)
        except (ParseError, requests.RequestException, ValueError, TypeError, OSError) as exc:
            item["error_type"] = type(exc).__name__
            if isinstance(exc, ParseError):
                item["error_code"] = exc.code
        result["sdk"].append(item)
    result["repair_verified"] = False
    result["audit_complete"] = (
        not result["object_limit_reached"] and not result["vid_limit_reached"]
        and all("error_type" not in item for item in result["media_objects"] + result["sdk"]))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("link")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--direct", action="store_true", help="媒体/目录 HTTP 请求不使用环境代理")
    args = ap.parse_args()
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with DiscoveryParser(auto_guest=True, allow_external_asset_recovery=False) as parser:
            if args.direct:
                parser.session.trust_env = False
            report.update(probe(parser, args.link))
    except (ParseError, requests.RequestException, ValueError, TypeError, OSError) as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, ParseError):
            report["error_code"] = exc.code
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("audit_complete") else 2  # Exit 0 means the audit completed.


if __name__ == "__main__":
    raise SystemExit(main())
