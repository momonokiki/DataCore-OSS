from __future__ import annotations

import uuid

import app.db_all_models  # noqa: F401 - load core SQLAlchemy models
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.db.models.l3_tools import L3Tool
from app.infrastructure.db.session import get_sync_db_session

from . import ADDON_NAME, TOOL_NAME
from .numeric_features import NUMERIC_SPAN_METHOD
from .numeric_classification import NUMERIC_CLASSIFICATION_METHOD
from .setup_db import main as create_addon_tables

MODEL_NAME = "deterministic_receipt_numeric_classifier"
PROMPT_VERSION = "span_v2_class_v1"


def main() -> None:
    # 1. Create this addon's result tables.
    create_addon_tables()

    # 2. Register the immutable processing-tool provenance.
    config = {
        "provider": "deterministic",
        "addon": ADDON_NAME,
        "pipeline": "numeric_span_extraction_and_classification",
        "numeric_span_method": NUMERIC_SPAN_METHOD,
        "numeric_classification_method": NUMERIC_CLASSIFICATION_METHOD,
    }

    with get_sync_db_session() as session:
        session.execute(
            insert(L3Tool)
            .values(
                id=uuid.uuid4(),
                name=TOOL_NAME,
                model_name=MODEL_NAME,
                prompt_version=PROMPT_VERSION,
                config=config,
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=[L3Tool.name])
        )

        tool = session.execute(
            select(L3Tool).where(L3Tool.name == TOOL_NAME)
        ).scalar_one()

        # Do not rewrite a tool record already used as provenance.
        if (
            tool.model_name != MODEL_NAME
            or tool.prompt_version != PROMPT_VERSION
            or tool.config != config
        ):
            raise ValueError(
                f"Provenance mismatch for '{TOOL_NAME}'. "
                "Existing L3Tool was not modified. Use a new tool name/version."
            )

    print(f"L3 addon ready: {TOOL_NAME}")


if __name__ == "__main__":
    main()
