from abc import ABC, abstractmethod
from app.layers.l3_structured.addons.finunce_parser.schemas import ParsedCsvResultSchema

class BaseCsvParser(ABC):
    parser_id: str      # L3Toolの prompt_version にマッピングされる識別子
    account_id: str     # ツール名決定用 (例: 'jcb_card')

    @abstractmethod
    def can_parse(self, content_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def parse(self, content_bytes: bytes) -> ParsedCsvResultSchema:
        pass

