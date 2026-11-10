
import uuid
import asyncio

from sqlalchemy import select

from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.storage import LocalStorageAdapter

from app.infrastructure.db.models.l2_tools import L2Tool
from app.layers.l2_extracted.models import L2Artifact
from app.layers.l1_raw.models import L1File

from app.layers.l2_extracted.ocr.registry import OCR_PLUGINS


async def ocr_file_orchestrator(
    file_hash: str,
    plugin_name: str = "yomitoku_native_ocr",
) -> dict:
    """
    L2 OCRオーケストレーター。

    1. RegistryからOCRプラグインを取得
    2. L1Fileの存在を確認
    3. MIMEタイプを確認
    4. DB登録済みのL2Toolを取得
    5. 冪等性チェック
    6. CASから原本を取得
    7. OCR実行
    8. L2Artifactを保存

    L2Toolの登録・更新はInitializerが担当する。
    """

    # 1. Registryからプラグインを取得
    plugin = OCR_PLUGINS.get(plugin_name)

    if plugin is None:
        raise ValueError(
            f"指定されたOCRプラグインが見つかりません: {plugin_name}"
        )

    print(
        f"[Orchestrator] Starting OCR pipeline "
        f"for file_hash={file_hash} using [{plugin.tool_name}]",
        flush=True,
    )

    async with AsyncSessionLocal() as session:

        # 2. L1Fileの存在確認
        l1_stmt = select(L1File).where(
            L1File.file_hash == file_hash
        )

        l1_res = await session.execute(l1_stmt)
        l1_file = l1_res.scalars().first()

        if not l1_file:
            raise ValueError(
                f"L1 file not found for hash: {file_hash}"
            )

        # 3. MIMEタイプ確認
        supported = plugin.supported_mimetypes

        if l1_file.mime_type not in supported:
            print(
                f"[Orchestrator] Skip: Plugin [{plugin.tool_name}] "
                f"does not support MIME type: {l1_file.mime_type}",
                flush=True,
            )

            return {
                "file_hash": file_hash,
                "artifact_id": None,
            }

        # 4. DBに登録済みのL2Toolを取得
        tool_stmt = select(L2Tool).where(
            L2Tool.name == plugin.tool_name
        )

        tool_res = await session.execute(tool_stmt)
        l2_tool = tool_res.scalars().first()

        if l2_tool is None:
            raise RuntimeError(
                f"L2Tool '{plugin.tool_name}' is not registered. "
                "Run ./init.sh db before executing OCR."
            )

        # 5. 冪等性チェック
        existing_stmt = select(L2Artifact).where(
            L2Artifact.file_hash == file_hash,
            L2Artifact.tool_id == l2_tool.id,
            L2Artifact.artifact_type == "ocr_text",
        )

        existing_res = await session.execute(existing_stmt)
        existing_artifact = existing_res.scalars().first()

        if existing_artifact:
            print(
                f"[Orchestrator] Already processed "
                f"file_hash={file_hash} "
                f"with [{plugin.tool_name}]",
                flush=True,
            )

            return {
                "file_hash": file_hash,
                "artifact_id": str(existing_artifact.id),
            }

        # 6. CASから原本バイナリをロード
        storage = LocalStorageAdapter()

        file_content = await storage.load(file_hash)

        if file_content is None:
            raise FileNotFoundError(
                f"CAS physical binary file missing in storage: {file_hash}"
            )

        # 7. OCR実行
        ocr_result = await asyncio.to_thread(
            plugin.process_from_memory,
            file_content,
            l1_file.mime_type,
        )

        # 8. L2Artifactを作成
        artifact = L2Artifact(
            id=uuid.uuid4(),
            file_hash=file_hash,
            tool_id=l2_tool.id,
            artifact_type="ocr_text",
            content_text=ocr_result["full_text"],
            bounding_box={
                "words": ocr_result["words"],
            },
            parent_artifact_id=None,
            metadata_json=ocr_result["metadata_json"],
        )

        session.add(artifact)
        await session.commit()

        print(
            f"[Orchestrator] Ingestion Complete "
            f"artifact_id={artifact.id}",
            flush=True,
        )

        return {
            "file_hash": file_hash,
            "artifact_id": str(artifact.id),
        }

