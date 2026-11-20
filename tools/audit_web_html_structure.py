"""Summarize target-related embedded HTML data read as UTF-8 from stdin."""

import json
import sys
from html.parser import HTMLParser
from urllib.parse import unquote


TARGET = "7708052871413075238"
ID_KEYS = ("aweme_id", "awemeId", "item_id", "itemId")


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = {"attrs": dict(attrs), "text": ""}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


def inspect(value):
    nodes = 0
    matches = []

    def walk(node, path):
        nonlocal nodes
        nodes += 1
        if isinstance(node, dict):
            if any(str(node.get(k)) == TARGET for k in ID_KEYS):
                video = node.get("video")
                aweme = node.get("aweme")
                matches.append({
                    "path": path,
                    "keys": sorted(node),
                    "video_present": isinstance(video, dict),
                    "video_model_present": bool(video.get("video_model")) if isinstance(video, dict) else False,
                    "bit_rate_count": len(video.get("bit_rate") or []) if isinstance(video, dict) else None,
                    "aweme_type": type(aweme).__name__,
                })
            for key, child in node.items():
                walk(child, path + "." + str(key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, path + "[" + str(index) + "]")
        elif isinstance(node, str) and node.lstrip().startswith(("{", "[")):
            try:
                child = json.loads(node)
            except (ValueError, RecursionError):
                return
            walk(child, path + "#json")

    walk(value, "$")
    return {"nodes": nodes, "matches": matches}


def error_context(exc):
    """Describe parser failure without printing potentially sensitive content."""
    if not isinstance(exc, json.JSONDecodeError):
        return {}
    def category(char):
        if char in '{}[],:"\\':
            return char
        if char.isspace():
            return "space"
        if char.isalpha():
            return "letter"
        if char.isdigit():
            return "digit"
        return "other"
    return {"error_position": exc.pos, "error_message": exc.msg,
            "error_context_categories": [category(c) for c in exc.doc[max(0, exc.pos - 5):exc.pos + 6]]}


def main():
    html = sys.stdin.buffer.read().decode("utf-8")
    parser = Scripts()
    parser.feed(html)
    result = {"characters": len(html), "scripts": len(parser.scripts), "render_data": [], "target_pace": [], "other_target_inline": []}
    for index, script in enumerate(parser.scripts):
        value = script["text"]
        if script["attrs"].get("id") == "RENDER_DATA":
            entry = {"script_index": index}
            try:
                entry.update(inspect(json.loads(unquote(value))))
                entry["parsed"] = True
            except (ValueError, RecursionError) as exc:
                entry.update(parsed=False, error=type(exc).__name__)
            result["render_data"].append(entry)
        elif TARGET in value and value.startswith("self.__pace_f.push(") and value.endswith(")"):
            entry = {"script_index": index, "length": len(value)}
            stage = "envelope"
            try:
                envelope = json.loads(value[len("self.__pace_f.push("):-1])
                stage = "payload"
                payload = unquote(envelope[1])
                if len(payload) > 2 and payload[0].isdigit() and payload[1] == ":":
                    payload = payload[2:]
                entry.update(inspect(json.loads(payload)))
                entry["parsed"] = True
            except (ValueError, IndexError, TypeError, RecursionError) as exc:
                entry.update(parsed=False, error=type(exc).__name__, error_stage=stage)
                entry.update(error_context(exc))
            result["target_pace"].append(entry)
        elif TARGET in value and not script["attrs"].get("src"):
            result["other_target_inline"].append({"script_index": index, "length": len(value)})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
