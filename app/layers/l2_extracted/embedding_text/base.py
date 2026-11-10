#app/layers/l2_extracted/embedding_text/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextEmbeddingResult:
    vector: list[float]
    dimension: int
    metadata: dict[str, Any]


class BaseTextEmbeddingPlugin(ABC):
    """すべてのL2 テキストEmbeddingプラグインが遵守すべき共通インターフェース"""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """l2_tools.name に登録する一意なツール識別子。例: 'nomic_embed_text'"""
        pass

    @property
    @abstractmethod
    def tool_version(self) -> str:
        """ツールまたはモデルのバージョン。例: '1.5.0'"""
        pass

    @property
    @abstractmethod
    def output_dim(self) -> int:
        """このモデルが返却するベクトルの次元数。例: 768"""
        pass

    @abstractmethod
    async def embed_text(
        self,
        text_input: str,
    ) -> TextEmbeddingResult:
        """平文テキストを受け取り、Ollama等の外部APIと非同期通信してベクトルを返却する心臓部"""
        pass

