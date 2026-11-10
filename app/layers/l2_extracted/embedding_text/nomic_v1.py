# app/layers/l2_extracted/embedding_text/nomic_v1.py
from typing import Any
import httpx
from app.layers.l2_extracted.embedding_text.base import (
    BaseTextEmbeddingPlugin,
    TextEmbeddingResult,
)


class NomicTextV1Plugin(BaseTextEmbeddingPlugin):
    """Ollamaをバックエンドとし、nomic-embed-text系モデルを高効率に駆動する本番用プラグイン"""

    def __init__(self, base_url: str, model_name: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    @property
    def tool_name(self) -> str:
        return "nomic_embed_text"

    @property
    def tool_version(self) -> str:
        return "1.5.0"

    @property
    def output_dim(self) -> int:
        return 768

    async def embed_text(self, text_input: str) -> TextEmbeddingResult:
        if not text_input or not text_input.strip():
            raise ValueError("推論対象の text_input が空、または空白文字列です。")

        endpoint = f"{self.base_url}/api/embed"
        if self.base_url.endswith("/api/embed"):
            endpoint = self.base_url

        payload = {
            "model": self.model_name,
            "input": text_input
        }

        # 💡 タスク実行時のアクティブなイベントループ内でクライアントを新設・自動クローズ
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama API request failed with status {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Ollama API connection failed target=[{endpoint}]. Error: {str(e)}"
            ) from e

        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings, list):
            raise ValueError(f"Invalid embedding response format from Ollama: {data}")

        # 💡 【大逆転の修正】Ollamaが返す2次元配列から、0番目の要素（1次元のList[float]）を正しく剥ぎ取る！
        target_vector = embeddings[0]
        
        # 内側の要素を安全にfloatへキャストしてpgvector適合型にする
        vector = [float(value) for value in target_vector]

        if len(vector) != self.output_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.output_dim}, got {len(vector)}"
            )

        metadata: dict[str, Any] = {
            "provider": "ollama",
            "model": self.model_name,
            "char_count": len(text_input),
        }

        return TextEmbeddingResult(
            vector=vector,
            dimension=len(vector),
            metadata=metadata,
        )

