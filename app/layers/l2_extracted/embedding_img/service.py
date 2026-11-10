# app/layers/l2_extracted/embedding_img/service.py
import logging
import uuid  # 💡 UUID生成のために追加
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.db.models.l2_tools import L2Tool
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l1_raw.models import L1File
from app.layers.l2_extracted.embedding_img.base import (
    BaseImageEmbeddingPlugin,
    ImageEmbeddingResult,
)
from app.layers.l2_extracted.models import L2Artifact
from app.layers.l2_extracted.embedding_img.rinna_japanese_clip_v1 import (
    RinnaJapaneseClipV1Plugin,
)
from app.layers.l2_extracted.embedding_img.openai_clip_vit_base_patch32 import (
    OpenAIClipVitBasePatch32Plugin,
)
logger = logging.getLogger(__name__)

IMAGE_EMBEDDING_ARTIFACT_TYPE = "image_embedding"

IMAGE_EMBEDDING_PLUGINS: dict[str, BaseImageEmbeddingPlugin] = {
    plugin.tool_name: plugin
    for plugin in [
        OpenAIClipVitBasePatch32Plugin(),
    ]
}


async def embed_image_file(
    session: AsyncSession,
    file_hash: str,
    plugin_name: str = "openai_clip_vit_base_patch32",
) -> dict[str, Any]:
    """原本画像のEmbeddingを生成し、L2Artifactとして保存する。"""

    plugin = IMAGE_EMBEDDING_PLUGINS.get(plugin_name)
    if plugin is None:
        raise ValueError(f"Unknown image embedding plugin: {plugin_name}")

    # 1. L1Fileを取得する
    l1_file = (
        await session.execute(
            select(L1File).where(L1File.file_hash == file_hash)
        )
    ).scalar_one_or_none()

    if l1_file is None:
        raise ValueError(f"L1 file not found: {file_hash}")

    # 2. 対応MIMEか確認する
    if l1_file.mime_type not in plugin.supported_mime_types:
        logger.info(
            "Skip image embedding: unsupported MIME type "
            "file_hash=%s mime_type=%s plugin=%s",
            file_hash,
            l1_file.mime_type,
            plugin.tool_name,
        )
        return {
            "file_hash": file_hash,
            "artifact_id": None,
            "status": "skipped",
            "reason": "unsupported_mime_type",
        }

    # 3. 【自動マスタ同期】 l2_tools テーブルから取得、無ければその場で自動生成
    l2_tool = (
        await session.execute(
            select(L2Tool).where(L2Tool.name == plugin.tool_name)
        )
    ).scalar_one_or_none()

    if l2_tool is None:
        # 💡 プラグイン自身が持つ属性からマスタレコードを逆引き自動ビルド
        l2_tool = L2Tool(
            id=uuid.uuid4(),
            name=plugin.tool_name,
            tool_type="embedding",
            description="Auto-registered L2 Image Embedding Plug-in Engine",
            output_dim=plugin.output_dim,
            precision_type="float32",  # プラグインの標準実装に合わせて定義
            model_name=plugin.tool_name,
            model_version=plugin.tool_version,
            config_json={"supported_mimetypes": plugin.supported_mime_types}
        )
        session.add(l2_tool)
        await session.flush()  # IDを確定させて後続のL2Artifactの外部キー(tool_id)として安全にリレーする
        logger.info(f"[Orchestrator] l2_tools master synced for Image Embedding: [{plugin.tool_name}]")

    # 4. 既存の画像Embeddingがあれば再利用する（冪等性の担保）
    existing_artifact = (
        await session.execute(
            select(L2Artifact).where(
                L2Artifact.file_hash == file_hash,
                L2Artifact.tool_id == l2_tool.id,
                L2Artifact.artifact_type == IMAGE_EMBEDDING_ARTIFACT_TYPE,
            )
        )
    ).scalar_one_or_none()

    if existing_artifact is not None and existing_artifact.embedding is not None:
        logger.info(
            "Image embedding already exists: "
            "file_hash=%s artifact_id=%s",
            file_hash,
            existing_artifact.id,
        )
        return {
            "file_hash": file_hash,
            "artifact_id": str(existing_artifact.id),
            "status": "already_exists",
        }

    # 5. CASから原本画像を読む
    storage = LocalStorageAdapter()
    image_bytes = await storage.load(file_hash)

    if image_bytes is None:
        raise FileNotFoundError(
            f"CAS physical binary file missing: {file_hash}"
        )

    # 6. Embeddingを生成する
    result: ImageEmbeddingResult = await plugin.embed_image(
        image_bytes=image_bytes,
        mime_type=l1_file.mime_type,
    )

    # 7. 次元を検証する
    if result.dimension != plugin.output_dim:
        raise ValueError(
            f"Embedding dimension mismatch: "
            f"expected {plugin.output_dim}, got {result.dimension}"
        )

    if l2_tool.output_dim and result.dimension != l2_tool.output_dim:
        raise ValueError(
            f"L2Tool dimension mismatch: "
            f"expected {l2_tool.output_dim}, got {result.dimension}"
        )

    # 8. L2Artifactとして保存する
    artifact = L2Artifact(
        id=uuid.uuid4(),  # 💡 明示的にUUIDを付与（モデルのdefault設定に委ねる場合も、明示しておくと安全です）
        file_hash=file_hash,
        tool_id=l2_tool.id,
        artifact_type=IMAGE_EMBEDDING_ARTIFACT_TYPE,
        embedding=result.vector,
        embedding_dim=result.dimension,
        metadata_json=result.metadata,
        parent_artifact_id=None,
    )

    session.add(artifact)
    await session.commit()

    logger.info(
        "Image embedding completed: "
        "file_hash=%s artifact_id=%s dim=%s",
        file_hash,
        artifact.id,
        result.dimension,
    )

    return {
        "file_hash": file_hash,
        "artifact_id": str(artifact.id),
        "status": "success",
        "dimension": result.dimension,
    }

