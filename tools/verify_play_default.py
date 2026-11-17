"""真机验证官方默认档通道：只看 play?ratio=default 能不能只凭 video_id 拿到原片。

用法：python tools/verify_play_default.py <aweme_id> [<aweme_id> ...] [--cookie-file 凭据文件]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from original_parser.client import OriginalParser, ParseError, load_credentials


def main(argv: list[str]) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("ids", nargs="+", help="要检查的作品 ID")
    cli.add_argument("--cookie-file", type=Path, help="Cookie 和 User-Agent 凭据文件")
    args = cli.parse_intermixed_args(argv[1:])
    lines = []
    parser_kwargs = {}
    if args.cookie_file:
        cookies, user_agent = load_credentials(args.cookie_file)
        parser_kwargs = {"cookies": cookies, "user_agent": user_agent, "auto_guest": False}
        lines.append(f"登录态：{args.cookie_file.name}，字段 {len(cookies)} 个")
    with OriginalParser(**parser_kwargs) as parser:
        for aweme_id in args.ids:
            try:
                detail = parser.detail(aweme_id)
            except ParseError as error:
                lines.append(f"{aweme_id}: detail 失败 [{error.code}] {error}")
                continue
            video = detail.get("video") or {}
            video_id = str((video.get("play_addr") or {}).get("uri") or "")
            gears = sorted(parser._transcode_sizes(video))
            lines.append(f"{aweme_id} vid={video_id} HDR={video.get('is_source_HDR')} "
                         f"转码档={len(gears)} 档尺寸={gears}")
            candidate = parser._play_default_candidate(detail, video_id)
            lines.append(f"  note={parser.play_default_note or '无'}")
            if candidate is None:
                continue
            try:
                info = parser.probe(candidate)
            except ParseError as error:
                lines.append(f"  默认档命中但媒体校验失败 [{error.code}] {error}")
                continue
            lines.append(f"  默认档命中 {candidate['size']} B / {candidate['width']}x{candidate['height']}"
                         f" / {info['duration_seconds']:.3f}s / 音轨={info['has_audio']}")
            lines.append(f"  地址={candidate['url']}")
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / "verify-play-default.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
