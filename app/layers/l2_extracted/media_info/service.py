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
from app.layers.l2_extracted.media_info.detector import MediaTypeDetector
from app.layers.l2_extracted.media_info.image_exif import ImageExifPlugin

logger = logging.getLogger(__name__)

_IMAGE_EXIF_PLUGIN = ImageExifPlugin()

# format_type -> プラグイン の対応表。
# 形式の追加は「プラグインの追加 + ここに1行」で行う。
MEDIA_INFO_PLUGINS_BY_FORMAT: dict[str, Any] = {
    "jpeg": _IMAGE_EXIF_PLUGIN,
    "png": _IMAGE_EXIF_PLUGIN,
    "webp": _IMAGE_EXIF_PLUGIN,
}


def _sanitize_value(obj: Any) -> Any:
    """service 側の二重防御: bytes / NUL / NaN / Inf を無害化する"""
    NUL = chr(0)  # chr(0) を使う（文字化け防止）

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
    独立トランザクションで L2Tool を確実に登録する。
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
) -> dict[str, Any]:
    """
    L2Tool 登録（Phase 1）と MediaInfo upsert（Phase 2）を
    独立トランザクションに分割し、片方が失敗してももう片方を守る。

    プラグインは、CAS のバイトから検出した format_type で
    MEDIA_INFO_PLUGINS_BY_FORMAT から選択する。
    対応するプラグインがない形式は、例外ではなく
    status="skipped" + reason で返す。
    """
    logger.info(f"[Orchestrator] Starting MediaInfo pipeline for file_hash={file_hash}")
    status_str = "success"
    format_type: Optional[str] = None
    selected_plugin_name: Optional[str] = None
    reason: Optional[str] = None

    try:
        # 準備: L1File の検証
        async with AsyncSessionLocal() as session:
            l1_stmt = select(L1File).where(L1File.file_hash == file_hash)
            l1_res = await session.execute(l1_stmt)
            l1_file = l1_res.scalars().first()
            if not l1_file:
                raise ValueError(f"L1 file not found for hash: {file_hash}")

        # 準備: CAS からバイナリ取得
        storage = LocalStorageAdapter()
        file_content = await storage.load(file_hash)
        if file_content is None:
            raise FileNotFoundError(f"CAS physical binary file missing: {file_hash}")

        # 形式検出とプラグイン選択
        detection = MediaTypeDetector().detect(file_content)
        format_type = detection.format_type

        plugin = MEDIA_INFO_PLUGINS_BY_FORMAT.get(format_type) if format_type else None
        if plugin is None:
            reason = f"unsupported format_type: {format_type}"
            logger.info(
                f"[Orchestrator] Skip: {reason} "
                f"(detected mime_type={detection.mime_type}) file_hash={file_hash}"
            )
            return {
                "file_hash": file_hash,
                "media_info_status": "skipped",
                "format_type": format_type,
                "plugin_name": None,
                "reason": reason,
            }

        selected_plugin_name = plugin.tool_name

        # 検出 MIME がプラグインの対応範囲外なら弾く（ガード）
        if detection.mime_type not in plugin.supported_mimetypes:
            reason = f"unsupported mime_type: {detection.mime_type}"
            logger.info(
                f"[Orchestrator] Skip: {reason} "
                f"format_type={format_type} plugin={selected_plugin_name}"
            )
            return {
                "file_hash": file_hash,
                "media_info_status": "skipped",
                "format_type": format_type,
                "plugin_name": selected_plugin_name,
                "reason": reason,
            }

        logger.info(
            f"[Orchestrator] Detected format_type={format_type} "
            f"mime_type={detection.mime_type} plugin={selected_plugin_name}"
        )

        # Phase 1: L2Tool 登録（独立トランザクション）
        async with AsyncSessionLocal() as tool_session:
            await _ensure_l2_tool_registered(tool_session, plugin)

        # Phase 2: MediaInfo 抽出 & Upsert（独立トランザクション）
        async with AsyncSessionLocal() as session:
            # 1. プラグイン解析
            extracted_info = plugin.extract_from_memory(file_content, detection.mime_type)

            # 2. サニタイズ
            if extracted_info.raw_metadata is not None:
                extracted_info.raw_metadata = _sanitize_value(extracted_info.raw_metadata)
            if extracted_info.latitude is not None and math.isnan(extracted_info.latitude):
                extracted_info.latitude = None
            if extracted_info.longitude is not None and math.isnan(extracted_info.longitude):
                extracted_info.longitude = None

            # 3. Upsert（MediaInfoResult の全フィールドを保存する）
            stmt = insert(L2MediaInfo).values(
                file_hash=file_hash,
                content_created_at=extracted_info.content_created_at,
                author_or_device=extracted_info.author_or_device,
                width=extracted_info.width,
                height=extracted_info.height,
                latitude=extracted_info.latitude,
                longitude=extracted_info.longitude,
                duration_seconds=extracted_info.duration_seconds,
                sample_rate_hz=extracted_info.sample_rate_hz,
                frame_rate=extracted_info.frame_rate,
                page_count=extracted_info.page_count,
                line_count=extracted_info.line_count,
                encoding=extracted_info.encoding,
                raw_metadata=extracted_info.raw_metadata,
            )
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["file_hash"],
                set_={
                    "content_created_at": stmt.excluded.content_created_at,
                    "author_or_device": stmt.excluded.author_or_device,
                    "width": stmt.excluded.width,
                    "height": stmt.excluded.height,
                    "latitude": stmt.excluded.latitude,
                    "longitude": stmt.excluded.longitude,
                    "duration_seconds": stmt.excluded.duration_seconds,
                    "sample_rate_hz": stmt.excluded.sample_rate_hz,
                    "frame_rate": stmt.excluded.frame_rate,
                    "page_count": stmt.excluded.page_count,
                    "line_count": stmt.excluded.line_count,
                    "encoding": stmt.excluded.encoding,
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
        reason = str(e)

    return {
        "file_hash": file_hash,
        "media_info_status": status_str,
        "format_type": format_type,
        "plugin_name": selected_plugin_name,
        "reason": reason,
    }
