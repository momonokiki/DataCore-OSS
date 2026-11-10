import uuid
import logging
import math
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.storage import LocalStorageAdapter
from app.infrastructure.db.models.l2_tools import L2Tool
from app.layers.l2_extracted.models import L2MediaInfo
from app.layers.l1_raw.models import L1File
from app.layers.l2_extracted.media_info.image_exif import ImageExifPlugin

logger = logging.getLogger(__name__)

MEDIA_INFO_PLUGINS = {
    "image_exif_extractor": ImageExifPlugin(),
}


def _sanitize_value(obj: Any) -> Any:
    """service 側の二重防御: bytes / NUL / NaN / Inf を無害化する"""
    NUL = chr(0)  # 💡  の代わりに chr(0) を使う（文字化け防止）

    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_value(v) for v in obj]
    if isinstance(obj, bytes):
        try:
            decoded = obj.decode("utf-8", errors="replace")
        except Exception:
            decoded = obj.decode("latin-1", errors="replace")
        return decoded.replace(NUL, "")
    if isinstance(obj, str):
        return obj.replace(NUL, "")
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (bool, int)):
        return obj
    try:
        as_float = float(obj)
        if math.isnan(as_float) or math.isinf(as_float):
            return None
        return as_float
    except (TypeError, ValueError):
        pass
    try:
        return str(obj).replace(NUL, "")
    except Exception:
        return None

async def _ensure_l2_tool_registered(session: AsyncSession, plugin) -> L2Tool:
    """
    💡 独立トランザクションで L2Tool を確実に登録する。
    commit するため、後続の MediaInfo upsert が失敗しても消えない。
    """
    tool_stmt = select(L2Tool).where(L2Tool.name == plugin.tool_name)
    tool_res = await session.execute(tool_stmt)
    l2_tool = tool_res.scalars().first()

    if not l2_tool:
        l2_tool = L2Tool(
            id=uuid.uuid4(),
            name=plugin.tool_name,
            tool_type="metadata_extractor",
            description="Auto-registered L2 Media Metadata Extraction Plug-in Engine",
            model_name=plugin.tool_name,
            model_version="1.0.0",
            config_json={"supported_mimetypes": plugin.supported_mimetypes}
        )
        session.add(l2_tool)
        await session.commit()
        logger.info(f"[Orchestrator] L2Tool registered: {plugin.tool_name}")

    return l2_tool


async def media_info_orchestrator(
    file_hash: str,
    plugin_name: str = "image_exif_extractor",
) -> dict[str, Any]:
    """
    💡【鉄壁の防波堤】
    L2Tool 登録（Phase 1）と MediaInfo upsert（Phase 2）を
    独立トランザクションに分割し、片方が失敗してももう片方を守る。
    """
    plugin = MEDIA_INFO_PLUGINS.get(plugin_name)
    if not plugin:
        raise ValueError(f"指定されたMediaInfoプラグインが見つかりません: {plugin_name}")

    logger.info(f"[Orchestrator] Starting MediaInfo pipeline for file_hash={file_hash}")
    status_str = "success"

    try:
        # ── Phase 1: L2Tool 登録（独立トランザクション）──
        async with AsyncSessionLocal() as tool_session:
            await _ensure_l2_tool_registered(tool_session, plugin)

        # ── Phase 2: MediaInfo 抽出 & Upsert（独立トランザクション）──
        async with AsyncSessionLocal() as session:
            # 1. L1File の検証
            l1_stmt = select(L1File).where(L1File.file_hash == file_hash)
            l1_res = await session.execute(l1_stmt)
            l1_file = l1_res.scalars().first()
            if not l1_file:
                raise ValueError(f"L1 file not found for hash: {file_hash}")

            # 2. MIME タイプ検証
            if l1_file.mime_type not in plugin.supported_mimetypes:
                logger.info(f"[Orchestrator] Skip: unsupported MIME type {l1_file.mime_type}")
                return {"file_hash": file_hash, "status": "skipped", "reason": "unsupported_mime_type"}

            # 3. CAS からバイナリ取得
            storage = LocalStorageAdapter()
            file_content = await storage.load(file_hash)
            if file_content is None:
                raise FileNotFoundError(f"CAS physical binary file missing: {file_hash}")

            # 4. プラグイン解析
            extracted_info = plugin.extract_from_memory(file_content, l1_file.mime_type)

            # 5. サニタイズ
            if extracted_info.raw_metadata is not None:
                extracted_info.raw_metadata = _sanitize_value(extracted_info.raw_metadata)
            if extracted_info.latitude is not None and math.isnan(extracted_info.latitude):
                extracted_info.latitude = None
            if extracted_info.longitude is not None and math.isnan(extracted_info.longitude):
                extracted_info.longitude = None

            # 6. Upsert
            stmt = insert(L2MediaInfo).values(
                file_hash=file_hash,
                content_created_at=extracted_info.content_created_at,
                width=extracted_info.width,
                height=extracted_info.height,
                latitude=extracted_info.latitude,
                longitude=extracted_info.longitude,
                raw_metadata=extracted_info.raw_metadata,
            )
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["file_hash"],
                set_={
                    "content_created_at": stmt.excluded.content_created_at,
                    "width": stmt.excluded.width,
                    "height": stmt.excluded.height,
                    "latitude": stmt.excluded.latitude,
                    "longitude": stmt.excluded.longitude,
                    "raw_metadata": stmt.excluded.raw_metadata,
                    "updated_at": func.now(),
                }
            )
            await session.execute(upsert_stmt)
            await session.commit()
            logger.info(f"[Orchestrator] Ingestion Complete to l2_media_info. file_hash={file_hash}")

    except Exception as e:
        logger.error(
            f"[Orchestrator] Non-critical error bypassed for file_hash={file_hash}: {e}. Continuing pipeline.",
            exc_info=True
        )
        status_str = "failed"

    return {"file_hash": file_hash, "media_info_status": status_str}
