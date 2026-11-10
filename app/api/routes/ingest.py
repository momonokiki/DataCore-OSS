# app/api/routes/ingest.py

import uuid
import logging
from typing import List
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from pydantic import BaseModel
from celery import chain

from sqlalchemy.ext.asyncio import AsyncSession  # 👈 ここが抜けていないか確認・追記


from app.core.config import settings
from app.infrastructure.db.session import get_db_session
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l1_raw.service import L1FileIngestionService
from app.api.routes.auth import get_current_user_id  # 👈 署名ガードレールのインポート

# ロガーの初期化
logger = logging.getLogger("datacore.ingest")

# ── Celery タスク群をインポート ──
from app.tasks import (
    extract_media_info_task,
    embed_image_file_task,
    ocr_file_task,
    embedding_file_task,
    #parse_file_task,
    classify_receipt_numeric_task,
    reconstruct_yomitoku_layout_task
)

router = APIRouter(prefix="/api/v1", tags=["ingest"])

class FileIngestResponse(BaseModel):
    filename: str
    file_hash: str
    storage_path: str | None
    status: str

class IngestBatchResponse(BaseModel):
    user_id: str
    files: List[FileIngestResponse]
    message: str

@router.post("/ingest", response_model=IngestBatchResponse)
async def ingest_files(
    files: List[UploadFile] = File(..., description="複数のアップロードファイル"),
    trigger_pipeline: bool = Query(True, description="Celeryパイプラインを自動起動するか"),
    # 💡 偽装可能なHeaderを完全撤去し、暗号解読に成功したクリーンなユーザーIDをインジェクト！
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> IngestBatchResponse:
    """
    複数ファイルを受け付け、L1 CASに保存（重複排除）し、
    認証されたユーザーのコンテキストに紐づけてCeleryパイプラインを非同期起動する。
    """
    try:
        user_uuid = uuid.UUID(user_id)

        # ファイルストリームの読み込み
        file_list = []
        for upload_file in files:
            content = await upload_file.read()
            file_list.append((upload_file.filename or "unknown", content))

        # L1 物理層保存 (CASによる重複排除を実行)
        storage_adapter = LocalStorageAdapter()
        ingest_service = L1FileIngestionService(storage_adapter)
        ingest_results = await ingest_service.ingest_files(session, user_uuid, file_list)

        # レスポンスの組み立てと、起動用ハッシュの回収
        response_files = []
        file_hashes = []

        for filename, file_hash, storage_path in ingest_results:
            response_files.append(
                FileIngestResponse(
                    filename=filename,
                    file_hash=file_hash,
                    storage_path=storage_path,
                    status="success" if file_hash else "failed"
                )
            )
            if file_hash:
                file_hashes.append(file_hash)

        # ハッシュ駆動の独立した Chain をキック
        if trigger_pipeline and file_hashes:
            for file_hash in file_hashes:
                pipeline = chain(
                    extract_media_info_task.s(file_hash),  # 【第0走者】
                    embed_image_file_task.s(),             # 【第1走者】
                    ocr_file_task.s(),                     # 【第2走者】
                    embedding_file_task.s(),               # 【第3走者】
                    #parse_file_task.s()                    # 【第4走者】
                    reconstruct_yomitoku_layout_task.s(), #OCR boundingbox reconstruct
                    classify_receipt_numeric_task.s()#レシートルールベース解析実験用
                )
                pipeline.delay()
                logger.info(f"[FastAPI API] Secured pipeline triggered for user_id={user_id}, file_hash={file_hash}")

        return IngestBatchResponse(
            user_id=str(user_uuid),
            files=response_files,
            message=f"Ingested {len(file_hashes)} file(s). Fully authenticated context pipeline triggered on Celery."
        )

    except Exception as e:
        logger.error(f"[INGEST ERROR] Critical error in file ingestion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

