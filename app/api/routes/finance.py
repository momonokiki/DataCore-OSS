# app/api/routes/finance.py

import uuid
import logging
from typing import List
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import get_db_session
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l1_raw.service import L1FileIngestionService
from app.api.routes.auth import get_current_user_id

# ロガーの初期化
logger = logging.getLogger("datacore.finance")

# 金融機関CSV専用のCeleryタスクをインポート
from app.tasks import parse_finance_csv_task

router = APIRouter(prefix="/api/v1", tags=["finance"])

class FinanceFileResponse(BaseModel):
    filename: str
    file_hash: str
    storage_path: str | None
    status: str

class FinanceBatchResponse(BaseModel):
    user_id: str
    files: List[FinanceFileResponse]
    message: str


@router.post("/finance", response_model=FinanceBatchResponse)
async def ingest_finance_csv(
    files: List[UploadFile] = File(..., description="複数のアップロード金融CSVファイル"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> FinanceBatchResponse:
    """
    金融機関明細CSVを受け付け、L1 CASに保存（重複排除）し、
    確定的な金融CSVパースパイプライン（Celery）を直接非同期キックする。
    """
    try:
        user_uuid = uuid.UUID(user_id)

        # ファイルストリームの読み込み
        file_list = []
        for upload_file in files:
            content = await upload_file.read()
            file_list.append((upload_file.filename or "unknown", content))

        # 1. L1 物理層保存 (CASによる重複排除を実行)
        storage_adapter = LocalStorageAdapter()
        ingest_service = L1FileIngestionService(storage_adapter)
        ingest_results = await ingest_service.ingest_files(session, user_uuid, file_list)

        # 2. レレスポンスの組み立てと、起動用ハッシュの回収
        response_files = []
        file_hashes = []

        for filename, file_hash, storage_path in ingest_results:
            response_files.append(
                FinanceFileResponse(
                    filename=filename,
                    file_hash=file_hash,
                    storage_path=storage_path,
                    status="success" if file_hash else "failed"
                )
            )
            if file_hash:
                file_hashes.append(file_hash)

        # 3. ハッシュ駆動で金融CSVパースタスクをダイレクトにキック
        if file_hashes:
            for file_hash in file_hashes:
                # 重厚なAIやOCRを経由せず、直接金融CSV専用の確定パースタスクにトス
                parse_finance_csv_task.delay(file_hash)
                logger.info(f"[FastAPI Finance API] Deterministic finance pipeline triggered for user_id={user_id}, file_hash={file_hash}")

        return FinanceBatchResponse(
            user_id=str(user_uuid),
            files=response_files,
            message=f"Ingested {len(file_hashes)} finance file(s). Deterministic parser pipeline triggered on Celery."
        )

    except Exception as e:
        logger.error(f"[FINANCE INGEST ERROR] Critical error in finance file ingestion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

