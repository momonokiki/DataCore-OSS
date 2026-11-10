# app/layers/l2_extracted/embedding/nomic_japanese_v1.py
import base64
from typing import Any

import httpx

from app.layers.l2_extracted.embedding_img.base import (
    BaseImageEmbeddingPlugin,
    ImageEmbeddingResult,
)


class NomicJapaneseV1Plugin(BaseImageEmbeddingPlugin):
    def __init__(self, base_url: str, model_name: str = "nomic-embed-vision-v1.5"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    @property
    def tool_name(self) -> str:
        return "nomic_japanese_v1"

    @property
    def tool_version(self) -> str:
        return "1.0.0"

    @property
    def output_dim(self) -> int:
        return 768

    @property
    def supported_mime_types(self) -> list[str]:
        return [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

    async def embed_image(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ImageEmbeddingResult:
        if mime_type not in self.supported_mime_types:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        payload = {
            "model": self.model_name,
            "input": {
                "images": [
                    f"data:{mime_type};base64,{image_b64}",
                ],
            },
        }

        endpoint = f"{self.base_url}/api/embed"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama embedding API failed: "
                f"{exc.response.status_code} {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama embedding API: {endpoint}"
            ) from exc

        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings, list):
            raise ValueError("Invalid embedding response: embeddings is empty")

        vector = embeddings[0]
        if not isinstance(vector, list) or not vector:
            raise ValueError("Invalid embedding response: vector is empty")

        vector = [float(value) for value in vector]

        if len(vector) != self.output_dim:
            raise ValueError(
                f"Embedding dimension mismatch: "
                f"expected {self.output_dim}, got {len(vector)}"
            )

        metadata: dict[str, Any] = {
            "provider": "ollama",
            "model": self.model_name,
            "mime_type": mime_type,
        }

        return ImageEmbeddingResult(
            vector=vector,
            dimension=len(vector),
            metadata=metadata,
        )
