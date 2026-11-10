# app/layers/l2_extracted/embedding/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImageEmbeddingResult:
    vector: list[float]
    dimension: int
    metadata: dict[str, Any]


class BaseImageEmbeddingPlugin(ABC):
    """画像Embeddingプラグインの共通インターフェース。"""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """l2_tools.name に登録する一意なツール名。"""

    @property
    @abstractmethod
    def tool_version(self) -> str:
        """ツールまたはモデルのバージョン。"""

    @property
    @abstractmethod
    def output_dim(self) -> int:
        """このツールが返すEmbeddingの次元数。"""

    @property
    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """処理できるMIMEタイプ。"""

    @abstractmethod
    async def embed_image(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ImageEmbeddingResult:
        """画像bytesを受け取り、Embeddingベクトルを返す。"""
