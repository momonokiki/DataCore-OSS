
"""
Celery Task Registry

各レイヤー・Addonに定義されたTaskを読み込み、
Celeryへの登録と既存コードとの互換性を維持する。

Taskの実装本体は各tasks.pyに配置する。
"""

# Celeryインスタンス
from app.celery_app import celery_app


# ---------------------------------------------------------
# L2 Extracted Tasks
# ---------------------------------------------------------
from app.layers.l2_extracted.tasks import (
    extract_media_info_task,
    embed_image_file_task,
    ocr_file_task,
    embedding_file_task,
)


# ---------------------------------------------------------
# L3 Addon Tasks
# ---------------------------------------------------------
from app.layers.l3_structured.addons.receipt.tasks import (
    parse_file_task,
)

from app.layers.l3_structured.addons.receipt_classify_exp.tasks import (
    classify_receipt_numeric_task,
)

from app.layers.l3_structured.addons.yomitoku_layout.tasks import (
    reconstruct_yomitoku_layout_task,
)

from app.layers.l3_structured.addons.finunce_parser.tasks import (
    parse_finance_csv_task,
)


# ---------------------------------------------------------
# Public exports
# ---------------------------------------------------------
__all__ = [
    "celery_app",
    "extract_media_info_task",
    "embed_image_file_task",
    "ocr_file_task",
    "embedding_file_task",
    "parse_file_task",
    "classify_receipt_numeric_task",
    "reconstruct_yomitoku_layout_task",
    "parse_finance_csv_task",
]

