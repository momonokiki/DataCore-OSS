import asyncio
import io
from typing import Any

import torch
from PIL import Image
from transformers import CLIPVisionModel

from app.layers.l2_extracted.embedding_img.base import (
    BaseImageEmbeddingPlugin,
    ImageEmbeddingResult,
)

IMAGE_SIZE = 224
IMAGE_MEAN = [0.48145466, 0.4578275, 0.40821073]
IMAGE_STD = [0.26862954, 0.26130258, 0.27577711]


class RinnaJapaneseClipV1Plugin(BaseImageEmbeddingPlugin):
    def __init__(
        self,
        model_name: str = "rinna/japanese-clip-vit-b-16",
        device: str | None = None,
    ):
        self._model_name = model_name
        self._device = device or (
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self._model = None

    @property
    def tool_name(self) -> str:
        return "rinna_japanese_clip_v1"

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

    def _ensure_model(self):
        if self._model is None:
            self._model = CLIPVisionModel.from_pretrained(self._model_name)
            self._model.to(self._device)
            self._model.eval()

    def _preprocess(self, image: Image.Image) -> torch.Tensor:
        image = image.convert("RGB")
        image = image.resize(
            (IMAGE_SIZE, IMAGE_SIZE),
            Image.Resampling.BICUBIC,
        )

        import numpy as np

        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - np.array(IMAGE_MEAN, dtype=np.float32)) / np.array(
            IMAGE_STD, dtype=np.float32
        )
        arr = arr.transpose(2, 0, 1)

        return torch.from_numpy(arr).unsqueeze(0)

    def _embed_sync(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ImageEmbeddingResult:
        self._ensure_model()

        try:
            image = Image.open(io.BytesIO(image_bytes))
        except Exception as exc:
            raise ValueError(f"Failed to decode image: {mime_type}") from exc

        pixel_values = self._preprocess(image).to(self._device)

        with torch.no_grad():
            outputs = self._model.vision_model(pixel_values=pixel_values)
            pooled = outputs.pooler_output
            vector = pooled.squeeze(0).float().cpu().tolist()

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
            "image_size": IMAGE_SIZE,
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
