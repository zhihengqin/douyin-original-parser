"""在 PyCharm 里直接运行；修改 LINKS 即可更换目标。"""

import json
import sqlite3
import sys
import time
from pathlib import Path

from original_parser import OriginalParser, ParseError
from original_parser.client import load_credentials
from original_parser.web_attempts import WebAttemptJournal

LINKS = ["https://www.douyin.com/video/7701401474567343403"]
DOWNLOAD = True
OUTPUT_DIR = Path(__file__).parent / "output"
# 默认自动取得匿名访客标识；也可指定包含 Cookie 和 User-Agent 的凭据文件。
COOKIE_FILE = None
# 历史已核对过的外部来源原片身份默认不参与取址；设 True 或命令行加 --allow-external
# 才会使用（仍走官方分发重签与 MP4 媒体校验）。None 表示跟随环境变量
# DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY。
ALLOW_EXTERNAL = None
# 官方原画不可用时是否接受最高普通档源候选；None 表示跟随
# DOUYIN_ALLOW_SOURCE_CANDIDATE 环境变量。
ALLOW_SOURCE_CANDIDATE = None


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else list(argv)
    unknown = [item for item in argv if item.startswith("-") and item not in ("--allow-external", "--retry-pending")]
    if unknown:
        print(f"无法识别的参数：{' '.join(unknown)}", file=sys.stderr)
        return 2
    retry = "--retry-pending" in argv
    requested = [item for item in argv if not item.startswith("-")]
    if retry and (requested or "--allow-external" in argv):
        print("--retry-pending 单独使用，从 Web 复查待查作品。", file=sys.stderr)
        return 2
    allow_external = ALLOW_EXTERNAL
    if "--allow-external" in argv:
        allow_external = True
    output = OUTPUT_DIR
    output.mkdir(exist_ok=True)
    journal = WebAttemptJournal(output / "web_attempts.sqlite3")
    if retry:
        allow_external = False
        try:
            links = journal.pending_ids()
        except (OSError, sqlite3.Error) as exc:
            print(f"无法读取待查记录：{type(exc).__name__}", file=sys.stderr)
            return 2
        if not links:
            print("没有待复查的 Web 作品。")
            return 0
    else:
        links = requested or LINKS

    def remember(work, outcome, **details):
        if not isinstance(work, str) or not (work.isascii() and work.isdigit() and 15 <= len(work) <= 22):
            return False
        try:
            journal.record(work, outcome, catalogs=parser.web_catalog_observations, **details)
        except (OSError, sqlite3.Error) as exc:
            print(f"无法保存此次 Web 记录：{type(exc).__name__}", file=sys.stderr)
            return False
        return True
    cookies, user_agent = load_credentials(Path(COOKIE_FILE)) if COOKIE_FILE else ({}, None)
    failed = False
    with OriginalParser(cookies=cookies, user_agent=user_agent,
                        allow_external_asset_recovery=allow_external,
                        allow_source_candidate=ALLOW_SOURCE_CANDIDATE) as parser:
        for link in links:
            try:
                result = parser.parse(link)
                data = result["data"]
                downloaded = None
                if DOWNLOAD:
                    target = output / f"{data['aweme_id']}_source.mp4"
                    if target.exists():
                        target = output / (f"{data['aweme_id']}_source_"
                                           f"{time.strftime('%Y%m%d_%H%M%S')}.mp4")
                    downloaded = parser.download(result, target)
                    data = result["data"]
                path = output / f"{data['aweme_id']}.json"
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                evidence = data.get("source_evidence")
                size_bytes = downloaded["bytes"] if downloaded else data["size_bytes"]
                if evidence in ("official_quality", "official_play_hash"):
                    remember(str(data["aweme_id"]), "success", source_evidence=evidence, file_size=size_bytes)
                elif parser.web_catalog_only_transcodes:
                    remember(str(data["aweme_id"]), "only_transcodes", error_code="source_unavailable")
                if evidence == "official_quality":
                    tier = f"官方原画档位 {data['official_quality']}"
                elif evidence == "official_play_hash":
                    tier = f"官方原片分发（已验证 file_hash，档位 {data['official_quality']}）"
                elif evidence == "official_web_pc_bitrate":
                    tier = "PC Web 详情独有档位（上传原件身份未经确认）"
                elif evidence == "official_play_default":
                    tier = "官方默认播放档（原画身份未经确认）"
                elif evidence == "platform_source_candidate":
                    tier = (f"源候选（最高普通档 {data['official_quality']}；"
                            f"内嵌源 VID {data.get('source_vid')}，非平台原画）")
                else:
                    tier = f"官方原画档位 {data['official_quality']}"
                print(f"{data['aweme_id']}：{data['level']}，{data['width']}×{data['height']}，"
                      f"{size_bytes/1_000_000:.2f} MB，{tier}")
                if downloaded:
                    print(f"已合并文件：{downloaded['path']}（{downloaded['bytes']:,} 字节，视频+音频）")
                else:
                    print(data["url"])
                    if data.get("dash_mux_required"):
                        print(f"音视频：DASH 分轨，下载时自动合并；音频地址：{data.get('audio_url') or ''}")
                print(f"结果已保存：{path}")
            except ParseError as exc:
                failed = True
                print(f"解析失败 [{exc.code}]：{exc}")
                only_normal = exc.code == "source_unavailable" and parser.web_catalog_only_transcodes
                saved = remember(parser.web_attempt_work_id, "only_transcodes" if only_normal else "error",
                                 error_code=exc.code)
                if saved and only_normal:
                    print("本次 Web 目录只返回了普通档，已列入待查。稍后运行 parse_links.py --retry-pending 复查。")
    return 2 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"解析失败 [local_error]：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
