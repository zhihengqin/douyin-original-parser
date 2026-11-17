"""离线检查运行依赖与 a_bogus 签名，供安装、升级及服务启动前执行。"""

import importlib
import sys
from urllib.parse import parse_qs

from .client import OriginalParser, ParseError


def check_runtime() -> None:
    # pip check 只校验已安装包之间的依赖；不会发现应用新增但根本未安装的 gmssl。
    for module in ("requests", "cryptography", "playwright.sync_api"):
        importlib.import_module(module)
    with OriginalParser(auto_guest=False) as parser:
        query = parser._a_bogus_query({"aid": "6383", "device_platform": "webapp"})
    if not parse_qs(query).get("a_bogus", [""])[0]:
        raise ValueError("a_bogus 签名检查未产生签名")


def main() -> int:
    try:
        check_runtime()
    except (ParseError, ImportError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, ParseError) else "runtime_check_failed"
        print(f"运行环境检查失败 [{code}]：{exc}", file=sys.stderr)
        return 1
    print("运行环境检查通过：Python 依赖和 a_bogus 签名可用（未访问上游）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
