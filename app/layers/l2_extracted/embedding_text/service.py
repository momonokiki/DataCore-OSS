# app/layers/l2_extracted/embedding_text/service.py
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.db.models.l2_tools import L2Tool
from app.layers.l2_extracted.embedding_text.base import BaseTextEmbeddingPlugin, TextEmbeddingResult
from app.layers.l2_extracted.embedding_text.nomic_v1 import NomicTextV1Plugin
from app.layers.l2_extracted.models import L2Artifact

logger = logging.getLogger(__name__)

TEXT_EMBEDDING_ARTIFACT_TYPE = "text_embedding"

# ── 【職人プラグイン名簿への登録】 ──
TEXT_EMBEDDING_PLUGINS: dict[str, BaseTextEmbeddingPlugin] = {
    plugin.tool_name: plugin
    for plugin in [
        NomicTextV1Plugin(base_url=settings.OLLAMA_BASE_URL),
    ]
}


async def embed_text_file(
    session: AsyncSession,
    file_hash: str,
    parent_ocr_id: Optional[str] = None,
    plugin_name: str = "nomic_embed_text",
) -> dict[str, Any]:
    """
    【L2テキストEmbeddingオーケストレーター：完全エラー耐性＆血統追跡版】
    前段のOCR成果物からテキストを自動抽出し、Ollamaでベクトル化してL2Artifactへ永続化する。
    通信エラーやイベントループ閉鎖など、いかなる致命的例外が起きても、
    パイプライン（Celery Chain）を壊さず、正常な顔をした辞書を返却して次走者へバトンをリレーする。
    """

    plugin = TEXT_EMBEDDING_PLUGINS.get(plugin_name)
    if plugin is None:
        raise ValueError(f"指定されたText Embeddingプラグインが見つかりません: {plugin_name}")

    status_str = "success"
    artifact_id_str = None
    ocr_artifact_id_for_relay = parent_ocr_id

    # 💡 【完全防御の防波堤】
    # データベース操作や外部推論APIとの通信に絡む全ロジックをトップレベルで完全ホールド
    try:
        # 1. 前段のOCR結果（Artifact）からテキストを引っ張る
        ocr_artifact = None
        if parent_ocr_id:
            try:
                ocr_uuid = uuid.UUID(parent_ocr_id) if isinstance(parent_ocr_id, str) else parent_ocr_id
                ocr_stmt = select(L2Artifact).where(L2Artifact.id == ocr_uuid)
                ocr_res = await session.execute(ocr_stmt)
                ocr_artifact = ocr_res.scalars().first()
            except ValueError:
                logger.error(f"[EmbeddingText] Invalid parent_ocr_id format: {parent_ocr_id}")

        # IDで引けなかった場合、またはIDが無い場合は、file_hashから最新のOCR結果をフォールバック探索
        if not ocr_artifact:
            ocr_stmt = (
                select(L2Artifact)
                .where(L2Artifact.file_hash == file_hash, L2Artifact.artifact_type == "ocr_text")
                .order_by(L2Artifact.created_at.desc())
            )
            ocr_res = await session.execute(ocr_stmt)
            ocr_artifact = ocr_res.scalars().first()

        # ガードレール：OCRテキストがどこにも見つからない場合は処理を優しくスキップ
        if not ocr_artifact or not ocr_artifact.content_text:
            logger.warning(f"[EmbeddingText] Skip: No OCR text found for file_hash={file_hash}")
            return {
                "file_hash": file_hash,
                "artifact_id": parent_ocr_id,
                "text_embedding_artifact_id": None,
                "status": "skipped",
                "reason": "ocr_text_not_found"
            }

        # 後続へ確実に繋ぐため、見つかった本物のOCR_IDをリレー用変数に格納しておく
        ocr_artifact_id_for_relay = str(ocr_artifact.id)
        text_content = ocr_artifact.content_text

        # 2. 【自動マスタ同期】 l2_tools テーブルへの登録確認
        l2_tool = (
            await session.execute(
                select(L2Tool).where(L2Tool.name == plugin.tool_name)
            )
        ).scalar_one_or_none()

        if l2_tool is None:
            l2_tool = L2Tool(
                id=uuid.uuid4(),
                name=plugin.tool_name,
                tool_type="embedding",
                description="Auto-registered L2 Text Embedding Plug-in Engine (Ollama)",
                output_dim=plugin.output_dim,
                precision_type="float32",
                model_name=plugin.tool_name,
                model_version=plugin.tool_version,
                config_json={"provider": "ollama"}
            )
            session.add(l2_tool)
            await session.flush()
            logger.info(f"[Orchestrator] l2_tools master synced for Text Embedding: [{plugin.tool_name}]")

        # 3. 冪等性のチェック
        existing_artifact = (
            await session.execute(
                select(L2Artifact).where(
                    L2Artifact.file_hash == file_hash,
                    L2Artifact.tool_id == l2_tool.id,
                    L2Artifact.artifact_type == TEXT_EMBEDDING_ARTIFACT_TYPE,
                )
            )
        ).scalar_one_or_none()

        if existing_artifact is not None and existing_artifact.embedding is not None:
            logger.info(f"[Orchestrator] Text embedding already exists (Idempotent): file_hash={file_hash}")
            return {
                "file_hash": file_hash,
                "artifact_id": ocr_artifact_id_for_relay,
                "text_embedding_artifact_id": str(existing_artifact.id),
                "status": "already_exists",
            }

        # 4. Ollama経由で推論実行（nomic_v1内部の使い捨てクライアントによりループ閉鎖エラーを完全回避）
        result: TextEmbeddingResult = await plugin.embed_text(text_input=text_content)

        # 5. L2Artifactとして永続化（血統のバインド）
        artifact = L2Artifact(
            id=uuid.uuid4(),
            file_hash=file_hash,
            tool_id=l2_tool.id,
            artifact_type=TEXT_EMBEDDING_ARTIFACT_TYPE,
            content_text=text_content,
            embedding=result.vector,
            embedding_dim=result.dimension,
            metadata_json=result.metadata,
            parent_artifact_id=ocr_artifact.id,
        )

        session.add(artifact)
        await session.commit()
        artifact_id_str = str(artifact.id)
        logger.info(f"[Orchestrator] Text embedding completed and persisted. artifact_id={artifact.id}")

    except Exception as e:
        # 💡 【完全防御】APIの通信切断や、万が一のDB障害が起きても絶対にタスクを爆死（FAILURE）させない！
        # ログに詳細な痕跡を残した上でロールバックし、正常終了扱いでバトンをトスする
        await session.rollback()
        logger.error(f"[Orchestrator] Non-critical error in EmbeddingText for file_hash={file_hash}: {e}. Continuing pipeline.", exc_info=True)
        status_str = "failed"

    # 💡 【究極の契約】何が起きても、次の第4走者（LLMパース）が絶対に迷子にならない辞書の形でトスする
    return {
        "file_hash": file_hash,
        "artifact_id": ocr_artifact_id_for_relay,  # 後続がOCRテキストを引ける主役IDを死守
        "text_embedding_artifact_id": artifact_id_str,
        "status": status_str
    }

