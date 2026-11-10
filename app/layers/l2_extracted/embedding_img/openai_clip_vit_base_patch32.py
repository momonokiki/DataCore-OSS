# app/layers/l2_extracted/embedding_img/openai_clip_vit_base_patch32.py

import asyncio
import io
from typing import Any

import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from app.layers.l2_extracted.embedding_img.base import (
    BaseImageEmbeddingPlugin,
    ImageEmbeddingResult,
)


class OpenAIClipVitBasePatch32Plugin(BaseImageEmbeddingPlugin):
    def __init__(
        self,
        model_name: str = "openai/clip-vit-base-patch32",
        device: str | None = None,
    ):
        self._model_name = model_name
        self._device = device or (
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self._model = None
        self._processor = None

    @property
    def tool_name(self) -> str:
        return "openai_clip_vit_base_patch32"

    @property
    def tool_version(self) -> str:
        return "1.0.0"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def output_dim(self) -> int:
        return 512

    @property
    def supported_mime_types(self) -> list[str]:
        return ["image/jpeg", "image/png", "image/webp"]

    def _ensure_model(self) -> None:
        if self._model is None:
            self._processor = AutoProcessor.from_pretrained(
                self._model_name
            )
            self._model = AutoModel.from_pretrained(self._model_name)
            self._model.to(self._device)
            self._model.eval()

    def _extract_image_features(self, output: Any) -> torch.Tensor:
        if torch.is_tensor(output):
            return output

        if hasattr(output, "image_embeds"):
            return output.image_embeds

        if hasattr(output, "pooler_output"):
            return output.pooler_output

        raise ValueError(
            f"Unexpected get_image_features output type: {type(output)}"
        )

    def _embed_sync(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ImageEmbeddingResult:
        self._ensure_model()

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise ValueError(
                f"Failed to decode image: {mime_type}"
            ) from exc

        inputs = self._processor(
            images=image,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            output = self._model.get_image_features(**inputs)
            features = self._extract_image_features(output)
            vector = features.squeeze(0).float().cpu().tolist()

        if len(vector) != self.output_dim:
            raise ValueError(
                f"Embedding dimension mismatch: "
                f"expected {self.output_dim}, got {len(vector)}"
            )

        metadata: dict[str, Any] = {
            "provider": "huggingface",
            "model": self._model_name,
            "device": self._device,
            "mime_type": mime_type,
        }

        return ImageEmbeddingResult(
            vector=vector,
            dimension=len(vector),
            metadata=metadata,
        )

    async def embed_image(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ImageEmbeddingResult:
        if mime_type not in self.supported_mime_types:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

        return await asyncio.to_thread(
            self._embed_sync,
            image_bytes,
            mime_type,
        )
