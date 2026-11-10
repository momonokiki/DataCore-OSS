from typing import List, Optional
from app.layers.l3_structured.addons.finunce_parser.parsers.base import BaseCsvParser
from app.layers.l3_structured.addons.finunce_parser.parsers.jcb import JcbCardCsvParser
from app.layers.l3_structured.addons.finunce_parser.parsers.yuucho import YuchoBankCsvParser

class ParserRegistry:
    def __init__(self):
        # 今後新規パーサを追加する場合はこのリストへの追記のみで拡張可能
        self._parsers: List[BaseCsvParser] = [
            JcbCardCsvParser(),
            YuchoBankCsvParser(),
        ]

    @property
    def parsers(self) -> List[BaseCsvParser]:
        return self._parsers

    def select_parser(self, content_bytes: bytes) -> Optional[BaseCsvParser]:
        for parser in self._parsers:
            if parser.can_parse(content_bytes):
                return parser
        return None

