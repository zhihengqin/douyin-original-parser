"""HDR 作品深挖：www.douyin.com/aweme/v1/play/ 上还没试过的参数维度。

维度：
  aid        ∈ 6383 / 1128 / 2329 / 2906
  ratio      ∈ default / hdr / hdr_720p / 2160p / 4k / source_hdr / bytevc1 / dash
  附加参数   ss_is_p_v_ss=1（jiji262 的 is_need_set_cookie 分支）
  stream_type∈ source / hdr / origin
  codec_type ∈ 0..5

用法：python tools/probe_play_deep.py <aweme_id>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from original_parser.client import OriginalParser, ParseError


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    lines = []
    with OriginalParser() as parser:
        detail = parser.detail(aweme_id)
        video = detail.get("video") or {}
        video_id = str((video.get("play_addr") or {}).get("uri") or "")
        lines.append(f"aweme_id={aweme_id}")
        lines.append(f"keys={sorted(video)}")
        lines.append(f"vid={video_id} HDR={video.get('is_source_HDR')} duration={video.get('duration')}")
        lines.append(f"token_auth={list((video.get('token_auth') or {}).keys()) if isinstance(video.get('token_auth'), dict) else video.get('token_auth')}")

        base = {"video_id": video_id, "line": "0", "is_play_url": "1",
                "watermark": "0", "source": "PackSourceEnum_PUBLISH", "ratio": "default"}

        def attempt(label: str, params: dict) -> None:
            query = parser._a_bogus_query(params)
            url = "https://www.douyin.com/aweme/v1/play/?" + query
            try:
                with parser._get(url, headers={
                        "Range": "bytes=0-15", "Accept-Encoding": "identity",
                        "Referer": f"https://www.douyin.com/video/{aweme_id}"}) as r:
                    total = (r.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                    lines.append(f"{label}: status={r.status_code} ct={r.headers.get('Content-Type')} total={total}")
                    if r.status_code in (200, 206):
                        lines.append(f"  final={r.url[:170]}")
            except ParseError as error:
                lines.append(f"{label}: !! [{error.code}] {error}")
            time.sleep(0.6)

        for aid in ("6383", "1128", "2329", "2906"):
            attempt(f"aid={aid} ratio=default", dict(base, aid=aid))
        for ratio in ("hdr", "hdr_720p", "2160p", "4k", "source_hdr", "bytevc1", "dash"):
            attempt(f"aid=6383 ratio={ratio}", dict(base, aid="6383", ratio=ratio))
        attempt("aid=6383 ss_is_p_v_ss=1", dict(base, aid="6383", ss_is_p_v_ss="1"))
        for stream_type in ("source", "hdr", "origin"):
            attempt(f"aid=6383 stream_type={stream_type}", dict(base, aid="6383", stream_type=stream_type))
        for codec_type in ("0", "1", "2", "3", "4", "5"):
            attempt(f"aid=6383 codec_type={codec_type}", dict(base, aid="6383", codec_type=codec_type))
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-deep-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
