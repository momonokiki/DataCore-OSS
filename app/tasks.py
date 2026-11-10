# app/tasks.py
import asyncio
import os
from celery import Celery
from app.core.config import settings
from app.infrastructure.db.session import AsyncSessionLocal

# ── 💡 現場監督（L2オーケストレーター群）の確実なインポート ──
from app.layers.l2_extracted.media_info.service import media_info_orchestrator
from app.layers.l2_extracted.ocr.service import ocr_file_orchestrator
from app.layers.l2_extracted.embedding_img.service import embed_image_file
from app.layers.l2_extracted.embedding_text.service import embed_text_file  # 👈 【新設】第3走者をインポート

print("=== [Celery Config] Initializing Celery App ===")

# Celery アプリケーションのインスタンス生成
celery_app = Celery("datacore_tasks", broker=settings.CELERY_BROKER_URL)

# 💡 ハッシュ駆動型に最適化した、超軽量・高速設定
RESULT_BACKEND_URL = settings.CELERY_BROKER_URL.replace("sqla+postgresql://", "db+postgresql://")

celery_app.conf.update(
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    result_backend=RESULT_BACKEND_URL,  # 履歴の保存先を celery_db に指定
    worker_send_task_events=True,        # Flowerへの生中継アナウンスを強制ON
    broker_transport_options={}
)

# ============================================================================
# 🚀 ハッシュ駆動パイプライン：タスク（レゴブロック）定義
# ============================================================================

# 📁 0. 原本ファイル メタデータ抽出タスク (パイプラインの真の起点)
@celery_app.task(name="tasks.extract_media_info", queue="ocr_tasks")
def extract_media_info_task(file_hash: str) -> dict:
    """
    【第0走者：メディアメタデータ抽出タスク】
    FastAPIから生文字列の file_hash を一番最初に受け取り、EXIFや物理属性を L2MediaInfo に永続化する。
    """
    print(f"[Celery Worker] Media Metadata Extraction Task triggered for hash: {file_hash}")

    # 重厚なI/O・CPUバウンド処理を考慮し、asyncio.run で現場監督を非同期駆動
    res = asyncio.run(
        media_info_orchestrator(
            file_hash=str(file_hash),
            plugin_name="image_exif_extractor",
        )
    )
    
    # 💡 職人がスキップや失敗をしても、後続のOCRやLLMパースを巻き添えにしないためのフォールバックガード
    # 必ず次のタスクが欲しがる最低限のコンテキスト（file_hash）を保証してリレーする
    return {
        "file_hash": file_hash,
        "media_info_status": res.get("media_info_status", "failed") if res else "failed"
    }


# 🖼️ 1. 原本画像Embeddingタスク（第0走者からのバトンを受け取る）
@celery_app.task(name="tasks.embed_image_file", queue="embed_tasks")
def embed_image_file_task(previous_result: dict | str) -> dict:
    """
    【第1走者：画像Embeddingタスク】
    前段(extract_media_info)の辞書から安全に file_hash を抽出し、画像Embeddingを生成して L2Artifact に保存。
    """
    print(f"[Celery Worker] Image Embedding Task received: {previous_result}")

    if isinstance(previous_result, dict):
        file_hash = previous_result.get("file_hash")
    else:
        file_hash = previous_result

    if not file_hash or str(file_hash).strip() in ("None", ""):
        raise ValueError(f"Invalid file_hash in image embedding context: {previous_result}")

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
        "image_embedding_artifact_id": res.get("artifact_id") if res else None,
        "status": res.get("status") if res else "failed"
    }


# 📝 2. OCRタスク（第1走者からのバトンを受け取る）
@celery_app.task(name="tasks.ocr_file", queue="ocr_tasks")
def ocr_file_task(
    previous_result: dict | str,
    plugin_name: str = "yomitoku_native_ocr",
) -> dict:
    """
    【第2走者：OCRタスク】
    前段の辞書から安全に file_hash を抽出してOCRを実行する。
    """
    print(f"[Celery Worker] OCR Task received: {previous_result}")

    if isinstance(previous_result, dict):
        file_hash = previous_result.get("file_hash")
    else:
        file_hash = previous_result

    if not file_hash or str(file_hash).strip() in ("None", ""):
        raise ValueError(f"Invalid file_hash in OCR pipeline context: {previous_result}")

    context = asyncio.run(
        ocr_file_orchestrator(
            file_hash=str(file_hash),
            plugin_name=plugin_name,
        )
    )

    if not context:
        context = {"file_hash": file_hash, "artifact_id": None}
        
    print(f"[Celery Worker] OCR Task completed. Output context: {context}")
    return context


# 🔢 3. テキストEmbeddingタスク（OCRのコンテキスト辞書を受け取る）
@celery_app.task(name="tasks.embedding_file", queue="embed_tasks")
def embedding_file_task(context: dict) -> dict:
    """
    【第3走者: テキストEmbeddingタスク】
    OCR結果の入った context を受け取り、前段の artifact_id（OCR結果）を親のIDとして引き継ぎ、
    自動同期＆フォールバック付きで Ollama (nomic-embed-text) ベクトルを生成・永続化する。
    """
    if not isinstance(context, dict):
        raise ValueError(f"Expected dict context from OCR, got: {type(context)}")

    file_hash = context.get("file_hash")
    ocr_artifact_id = context.get("artifact_id")  # 前段（第2走者）のOCRがDBに保存した一意なUUID
    
    print(f"[Celery Worker] Text Embedding Task triggered for hash: {file_hash} (parent_ocr_id: {ocr_artifact_id})")
    
    if not file_hash:
        raise ValueError(f"Missing file_hash in pipeline chain context: {context}")

    # 💡 【ホワイトボックス設計の真骨頂】 現場監督（サービス層）を非同期起動
    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await embed_text_file(
                session=session,
                file_hash=str(file_hash),
                parent_ocr_id=ocr_artifact_id,
                plugin_name="nomic_embed_text"
            )

    res = asyncio.run(run())

    # 後続の第4走者（LLMパースタスク）へ、このテキストEmbeddingの結果もマージしてバトンをリレーする
    output_context = {
        "file_hash": file_hash,
        "artifact_id": ocr_artifact_id,  # 後続がOCRテキストを引けるようにOCRのIDをメイン主役に据えておく
        "text_embedding_artifact_id": res.get("artifact_id"),
        "status": res.get("status", "failed")
    }
    print(f"[Celery Worker] Text Embedding Task completed. Output context: {output_context}")
    return output_context

# 4. L3 receipt parsing task
@celery_app.task(name="tasks.parse_file", queue="parse_tasks")
def parse_file_task(context: dict) -> dict:
    """L3レシート構造化タスク"""
    if not isinstance(context, dict) or not context.get("file_hash"):
        raise ValueError("L3 requires a context dict with file_hash")

    enabled = {
        name.strip()
        for name in settings.ENABLED_L3_ADDONS.split(",")
        if name.strip()
    }

    if "receipt" not in enabled:
        return {
            **context,
            "receipt_status": "skipped",
            "reason": "receipt_addon_disabled",
        }

    from app.layers.l3_structured.addons.receipt.service import parse_receipt_file

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await parse_receipt_file(
                session=session,
                file_hash=str(context["file_hash"]),
                parent_ocr_id=context.get("artifact_id"),
            )

    return {
        **context,
        **asyncio.run(run()),
    }

# 5. L3 Receipt Numeric Classification Experiment
@celery_app.task(
    name="tasks.classify_receipt_numeric",
    queue="parse_tasks",
)
def classify_receipt_numeric_task(context: dict) -> dict:
    """
    L3 Receipt Numeric Classification Experiment Task.

    OCR成果物を入力として、
    Numeric Span Extraction v2 と
    Numeric Classification v1 を実行し、
    独立したAddon専用テーブルに保存する。
    """

    print(
        "[Celery Worker] Receipt Numeric Classification Task "
        f"received: {context}"
    )

    # ---------------------------------------------------------
    # 1. 入力コンテキスト検証
    # ---------------------------------------------------------
    if not isinstance(context, dict):
        raise ValueError(
            f"Expected dict context, got: {type(context)}"
        )

    file_hash = context.get("file_hash")
    ocr_artifact_id = context.get("artifact_id")

    if not file_hash:
        raise ValueError(
            f"Missing file_hash in context: {context}"
        )

    if not ocr_artifact_id:
        return {
            **context,
            "receipt_classify_exp_status": "skipped",
            "reason": "ocr_artifact_id_missing",
        }

    # ---------------------------------------------------------
    # 2. Addon有効状態の確認
    # ---------------------------------------------------------
    enabled = {
        name.strip()
        for name in settings.ENABLED_L3_ADDONS.split(",")
        if name.strip()
    }

    if "receipt_classify_exp" not in enabled:
        return {
            **context,
            "receipt_classify_exp_status": "skipped",
            "reason": "addon_disabled",
        }

    # ---------------------------------------------------------
    # 3. Addon Serviceの呼び出し
    # ---------------------------------------------------------
    from app.layers.l3_structured.addons.receipt_classify_exp.service import (
        classify_receipt_file,
    )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await classify_receipt_file(
                session=session,
                file_hash=str(file_hash),
                parent_ocr_id=str(ocr_artifact_id),
            )

    # ---------------------------------------------------------
    # 4. 非同期Service実行
    # ---------------------------------------------------------
    try:
        result = asyncio.run(run())

        output_context = {
            **context,
            **result,
        }

        print(
            "[Celery Worker] Receipt Numeric Classification "
            f"completed: {output_context}"
        )

        return output_context

    except Exception as e:
        print(
            "[Celery Worker] Receipt Numeric Classification "
            f"failed: {str(e)}"
        )
        raise

# 6. L3 YomiToku Layout Reconstruction Task
@celery_app.task(
    name="tasks.reconstruct_yomitoku_layout",
    queue="parse_tasks",
)
def reconstruct_yomitoku_layout_task(context: dict) -> dict:
    """
    L2 YomiToku OCR Artifactからword geometryを読み込み、
    論理行・列を再構成してL3 addon専用テーブルに保存する。
    """

    print(
        "[Celery Worker] YomiToku Layout Task "
        f"received: {context}"
    )

    # ---------------------------------------------------------
    # 1. 入力コンテキスト検証
    # ---------------------------------------------------------
    if not isinstance(context, dict):
        raise ValueError(
            f"Expected dict context, got: {type(context)}"
        )

    file_hash = context.get("file_hash")
    ocr_artifact_id = context.get("artifact_id")

    if not file_hash:
        raise ValueError(
            f"Missing file_hash in context: {context}"
        )

    if not ocr_artifact_id:
        return {
            **context,
            "yomitoku_layout_status": "skipped",
            "reason": "ocr_artifact_id_missing",
        }

    # ---------------------------------------------------------
    # 2. Addon有効状態の確認
    # ---------------------------------------------------------
    enabled = {
        name.strip()
        for name in settings.ENABLED_L3_ADDONS.split(",")
        if name.strip()
    }

    if "yomitoku_layout" not in enabled:
        return {
            **context,
            "yomitoku_layout_status": "skipped",
            "reason": "addon_disabled",
        }

    # ---------------------------------------------------------
    # 3. Addon Serviceの呼び出し
    # ---------------------------------------------------------
    from app.layers.l3_structured.addons.yomitoku_layout.service import (
        build_yomitoku_layout,
    )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await build_yomitoku_layout(
                session=session,
                file_hash=str(file_hash),
                parent_ocr_id=str(ocr_artifact_id),
            )

    # ---------------------------------------------------------
    # 4. 非同期Service実行
    # ---------------------------------------------------------
    try:
        result = asyncio.run(run())

        output_context = {
            **context,
            **result,
        }

        print(
            "[Celery Worker] YomiToku Layout "
            f"completed: {output_context}"
        )

        return output_context

    except Exception as e:
        print(
            "[Celery Worker] YomiToku Layout "
            f"failed: {str(e)}"
        )
        raise


@celery_app.task(name="tasks.parse_finance_csv", queue="parse_tasks")
def parse_finance_csv_task(file_hash: str) -> dict:
    """
    【金融明細専用ルート：第0走者】
    L1ストレージから金融機関CSVファイルを直接ロードし、
    確定的パーサ群（JCB / ゆうちょ銀行）に投入してL3ドメインテーブルへ保存する。
    """
    print(f"[Celery Worker] Finance CSV Parsing Task triggered for hash: {file_hash}")
    
    import asyncio
    from app.infrastructure.storage import LocalStorageAdapter
    from app.infrastructure.db.session import AsyncSessionLocal
    from app.layers.l3_structured.addons.finunce_parser.service import parse_financial_csv

    # 1. CASから物理バイナリデータを取得
    storage = LocalStorageAdapter()
    
    # asyncio.runで非同期処理をカプセル化実行
    async def fetch_and_parse():
        file_bytes = await storage.load(str(file_hash))
        if not file_bytes:
            return {"file_hash": file_hash, "status": "skipped", "reason": "l1_binary_not_found"}
            
        async with AsyncSessionLocal() as session:
            return await parse_financial_csv(
                session=session,
                file_hash=str(file_hash),
                file_bytes=file_bytes
            )

    try:
        res = asyncio.run(fetch_and_parse())
        print(f"[Celery Worker] Finance CSV Task completed. Output: {res}")
        return res
    except Exception as e:
        print(f"[Celery Worker] Fatal error in Finance CSV Task: {str(e)}")
        raise
