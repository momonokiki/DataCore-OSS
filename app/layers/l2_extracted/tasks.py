
import asyncio

from app.celery_app import celery_app
from app.infrastructure.db.session import AsyncSessionLocal

from app.layers.l2_extracted.media_info.service import (
    media_info_orchestrator,
)
from app.layers.l2_extracted.ocr.service import (
    ocr_file_orchestrator,
)
from app.layers.l2_extracted.embedding_img.service import (
    embed_image_file,
)
from app.layers.l2_extracted.embedding_text.service import (
    embed_text_file,
)


@celery_app.task(name="tasks.extract_media_info", queue="ocr_tasks")
def extract_media_info_task(file_hash: str) -> dict:
    """
    メディアメタデータ抽出タスク。
    EXIFや物理属性をL2MediaInfoに永続化する。
    """
    print(
        "[Celery Worker] Media Metadata Extraction Task "
        f"triggered for hash: {file_hash}"
    )

    res = asyncio.run(
        media_info_orchestrator(
            file_hash=str(file_hash),
            plugin_name="image_exif_extractor",
        )
    )

    return {
        "file_hash": file_hash,
        "media_info_status": (
            res.get("media_info_status", "failed")
            if res
            else "failed"
        ),
    }


@celery_app.task(name="tasks.embed_image_file", queue="embed_tasks")
def embed_image_file_task(previous_result: dict | str) -> dict:
    """
    画像Embeddingタスク。
    前段の結果からfile_hashを取得して画像Embeddingを生成する。
    """
    print(
        "[Celery Worker] Image Embedding Task received: "
        f"{previous_result}"
    )

    if isinstance(previous_result, dict):
        file_hash = previous_result.get("file_hash")
    else:
        file_hash = previous_result

    if not file_hash or str(file_hash).strip() in ("None", ""):
        raise ValueError(
            f"Invalid file_hash in image embedding context: "
            f"{previous_result}"
        )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await embed_image_file(
                session=session,
                file_hash=str(file_hash),
                plugin_name="openai_clip_vit_base_patch32",
            )

    res = asyncio.run(run())

    return {
        "file_hash": file_hash,
        "image_embedding_artifact_id": (
            res.get("artifact_id") if res else None
        ),
        "status": res.get("status") if res else "failed",
    }


@celery_app.task(name="tasks.ocr_file", queue="ocr_tasks")
def ocr_file_task(
    previous_result: dict | str,
    plugin_name: str = "yomitoku_native_ocr",
) -> dict:
    """
    OCRタスク。
    前段の結果からfile_hashを取得してOCRを実行する。
    """
    print(
        f"[Celery Worker] OCR Task received: {previous_result}"
    )

    if isinstance(previous_result, dict):
        file_hash = previous_result.get("file_hash")
    else:
        file_hash = previous_result

    if not file_hash or str(file_hash).strip() in ("None", ""):
        raise ValueError(
            f"Invalid file_hash in OCR pipeline context: "
            f"{previous_result}"
        )

    context = asyncio.run(
        ocr_file_orchestrator(
            file_hash=str(file_hash),
            plugin_name=plugin_name,
        )
    )

    if not context:
        context = {
            "file_hash": file_hash,
            "artifact_id": None,
        }

    print(
        "[Celery Worker] OCR Task completed. "
        f"Output context: {context}"
    )

    return context


@celery_app.task(name="tasks.embedding_file", queue="embed_tasks")
def embedding_file_task(context: dict) -> dict:
    """
    テキストEmbeddingタスク。
    OCR成果物を親としてEmbeddingを生成・永続化する。
    """
    if not isinstance(context, dict):
        raise ValueError(
            f"Expected dict context from OCR, got: {type(context)}"
        )

    file_hash = context.get("file_hash")
    ocr_artifact_id = context.get("artifact_id")

    print(
        "[Celery Worker] Text Embedding Task triggered for "
        f"hash: {file_hash} "
        f"(parent_ocr_id: {ocr_artifact_id})"
    )

    if not file_hash:
        raise ValueError(
            f"Missing file_hash in pipeline chain context: {context}"
        )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await embed_text_file(
                session=session,
                file_hash=str(file_hash),
                parent_ocr_id=ocr_artifact_id,
                plugin_name="nomic_embed_text",
            )

    res = asyncio.run(run())

    output_context = {
        "file_hash": file_hash,
        "artifact_id": ocr_artifact_id,
        "text_embedding_artifact_id": res.get("artifact_id"),
        "status": res.get("status", "failed"),
    }

    print(
        "[Celery Worker] Text Embedding Task completed. "
        f"Output context: {output_context}"
    )

    return output_context

