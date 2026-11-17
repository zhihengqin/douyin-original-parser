"""读取 MP4 轨道与时长，不需要安装 ffmpeg。"""

import struct
from pathlib import Path

MAX_MOOV_BYTES = 16 * 1024 * 1024


def boxes(data: bytes):
    pos = 0
    while pos + 8 <= len(data):
        size, kind = struct.unpack_from(">I4s", data, pos)
        header = 8
        if size == 1:
            if pos + 16 > len(data):
                return
            size = struct.unpack_from(">Q", data, pos + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - pos
        if size < header or pos + size > len(data):
            return
        yield kind, data[pos + header:pos + size]
        pos += size


def parse_moov(body: bytes) -> dict:
    result = {"duration_seconds": None, "tracks": []}
    for kind, content in boxes(body):
        if kind == b"mvhd":
            if content and content[0] == 0 and len(content) >= 20:
                scale, duration = struct.unpack_from(">II", content, 12)
            elif content and content[0] == 1 and len(content) >= 32:
                scale = struct.unpack_from(">I", content, 20)[0]
                duration = struct.unpack_from(">Q", content, 24)[0]
            else:
                continue
            if scale:
                result["duration_seconds"] = duration / scale
        elif kind == b"trak":
            track = {}

            def visit(data, current_track, parent=b"trak"):
                for box_kind, box in boxes(data):
                    if box_kind in (b"mdia", b"minf", b"stbl"):
                        visit(box, current_track, box_kind)
                    elif box_kind == b"tkhd" and len(box) >= 84:
                        w, h = struct.unpack_from(">II", box, len(box) - 8)
                        if w and h:
                            current_track.update(width=w // 65536, height=h // 65536)
                    elif box_kind == b"hdlr" and parent == b"mdia" and len(box) >= 12:
                        # QuickTime minf may contain a data handler (e.g. url ).
                        # Only mdia/hdlr declares the track's media type.
                        current_track["type"] = box[8:12].decode("ascii", errors="replace")
                    elif box_kind == b"stsd" and len(box) >= 16:
                        current_track["codec"] = box[12:16].decode("ascii", errors="replace")

            visit(content, track)
            result["tracks"].append(track)
    result["has_video"] = any(t.get("type") == "vide" for t in result["tracks"])
    result["has_audio"] = any(t.get("type") == "soun" for t in result["tracks"])
    return result


def inspect_mp4(read_at, total_size: int) -> dict:
    """按 box 偏移读数据；支持 moov 在文件尾部，不扫描或下载整个 mdat。"""
    pos = 0
    for _ in range(128):
        if pos + 8 > total_size:
            break
        header = read_at(pos, min(16, total_size - pos))
        if len(header) < 8:
            break
        size, kind = struct.unpack_from(">I4s", header)
        header_size = 8
        if size == 1:
            if len(header) < 16:
                break
            size = struct.unpack_from(">Q", header, 8)[0]
            header_size = 16
        elif size == 0:
            size = total_size - pos
        if size < header_size or pos + size > total_size:
            raise ValueError("MP4 box 长度异常，可能是不完整文件")
        if kind == b"moov":
            if size > MAX_MOOV_BYTES:
                raise ValueError("MP4 元数据超过读取上限")
            body = read_at(pos + header_size, size - header_size)
            if len(body) != size - header_size:
                raise ValueError("MP4 元数据不完整")
            return parse_moov(body)
        pos += size
    raise ValueError("没有找到 MP4 moov 元数据")


def inspect_file(path: Path) -> dict:
    with path.open("rb") as stream:
        def read_at(offset, size):
            stream.seek(offset)
            return stream.read(size)
        return inspect_mp4(read_at, path.stat().st_size)
