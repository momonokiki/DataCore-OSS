"""
DataCore FastAPI アプリケーション エントリポイント
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.ingest import router as ingest_router
from app.api.routes.auth import router as auth_router
from app.api.routes.finance import router as finance_router
from app.api.routes.receipts import router as receipts_router
from app.infrastructure.db.session import get_sync_db_session
from app.api.routes.search import router as search_router
from app.infrastructure.db.initializer import run_database_initializer
# FastAPI アプリケーション作成

app = FastAPI(
    title=settings.APP_NAME,
    description="DataCore: Personal Data Infrastructure with FastAPI and Celery",
    version="0.1.0",
)

# CORS ミドルウェア
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(ingest_router)
app.include_router(auth_router)
app.include_router(finance_router)
app.include_router(receipts_router)
app.include_router(search_router)

@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {"status": "ok", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
