"""Archive and retrieve authorized MP4 masters without contacting the platform."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from .client import ParseError, _verified_video_track, resolve_id_local
from .media import inspect_file


def archive_id(link: str) -> str:
    work, _ = resolve_id_local(link)
    if work is None or not work.isascii():
        raise ParseError("invalid_input", "母版归档需要作品 ID 或含作品 ID 的抖音链接；请先在浏览器打开短链")
    return work


def _copy_with_digest(source: Path, destination: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_file, destination.open("wb") as output_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            output_file.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _publish(temporary: Path, destination: Path) -> None:
    try:
        with temporary.open("rb") as source, destination.open("xb") as target:
            try:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            except BaseException:
                target.close()
                destination.unlink(missing_ok=True)
                raise
    except FileExistsError as exc:
        raise ParseError("file_exists", "目标文件已存在，未覆盖") from exc


class MasterArchive:
    """Keep an operator-supplied link-to-file mapping distinct from playback records."""

    def __init__(self, root: Path):
        self.root = root

    def add(self, link: str, source: Path) -> dict:
        work = archive_id(link)
        self.root.mkdir(parents=True, exist_ok=True)
        entry = self.root / work
        try:
            entry.mkdir()
        except FileExistsError as exc:
            raise ParseError("master_exists", "该作品已有归档记录，未覆盖") from exc
        complete = False
        try:
            stored = entry / "master.mp4"
            size, sha256 = _copy_with_digest(source, stored)
            try:
                media = inspect_file(stored)
                track = _verified_video_track(media)
            except (ValueError, ParseError) as exc:
                raise ParseError("incomplete_media", "归档文件必须是包含音视频和有效时长的完整 MP4") from exc
            result = {
                "aweme_id": work, "bytes": size, "sha256": sha256,
                "source_evidence": "operator_archived_master",
                "width": track["width"], "height": track["height"],
                "duration_seconds": media["duration_seconds"],
            }
            with (entry / "master.json").open("x", encoding="utf-8") as manifest:
                json.dump(result, manifest, ensure_ascii=False)
            complete = True
            return result
        finally:
            if not complete:
                (entry / "master.json").unlink(missing_ok=True)
                (entry / "master.mp4").unlink(missing_ok=True)
                entry.rmdir()

    def fetch(self, link: str, destination: Path) -> dict:
        work = archive_id(link)
        entry = self.root / work
        if destination.exists():
            raise ParseError("file_exists", "目标文件已存在，未覆盖")
        try:
            manifest = json.loads((entry / "master.json").read_text(encoding="utf-8"))
            if (not isinstance(manifest, dict) or manifest.get("aweme_id") != work
                    or manifest.get("source_evidence") != "operator_archived_master"):
                raise ValueError("invalid archive manifest")
        except FileNotFoundError as exc:
            raise ParseError("source_unavailable", "此作品未归档授权母版") from exc
        except ValueError as exc:
            raise ParseError("invalid_archive", "归档记录无法识别") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".master-") as folder:
            temp = Path(folder) / "master.mp4"
            try:
                size, sha256 = _copy_with_digest(entry / "master.mp4", temp)
            except FileNotFoundError as exc:
                raise ParseError("invalid_archive", "归档记录对应的 MP4 缺失") from exc
            if size != manifest.get("bytes") or sha256 != manifest.get("sha256"):
                raise ParseError("hash_mismatch", "归档 MP4 与登记时的字节数或 SHA-256 不符")
            _publish(temp, destination)
        return {"aweme_id": work, "bytes": size, "sha256": sha256, "path": str(destination.resolve()),
                "source_evidence": "operator_archived_master"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="保存已获授权的 MP4 母版，之后仅用作品链接取回")
    parser.add_argument("--archive", type=Path, required=True, help="服务端维护的本地母版归档目录")
    commands = parser.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add", help="把发布时的母版与作品链接关联")
    add.add_argument("link")
    add.add_argument("source", type=Path)
    fetch = commands.add_parser("fetch", help="按作品链接取回母版并核对 SHA-256")
    fetch.add_argument("link")
    fetch.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    archive = MasterArchive(args.archive)
    try:
        record = (archive.add(args.link, args.source) if args.action == "add"
                  else archive.fetch(args.link, args.output))
    except (ParseError, OSError) as exc:
        code = getattr(exc, "code", "local_error")
        print(json.dumps({"code": code, "msg": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
