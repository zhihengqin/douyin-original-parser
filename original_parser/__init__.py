"""独立抖音原画解析器，只访问平台官方接口。"""

from .client import OriginalParser, ParseError

__all__ = ["OriginalParser", "ParseError"]
