
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.db.models.l3_tools import L3Tool
from app.infrastructure.db.session import get_sync_db_session

from . import ADDON_NAME, TOOL_NAME
from .setup_db import main as setup_db


MODEL_NAME = "yomitoku_word_geometry_layout"
PROMPT_VERSION = "geometry_v1"

LAYOUT_METHOD = "center_axis_clustering"
LAYOUT_VERSION = "geometry_v1"
LINE_TOLERANCE_RATIO = 0.45


def main() -> None:
    """Initialize addon tables and register the immutable L3 tool."""

    # 1. Create addon-specific tables before registering the tool.
    setup_db()

    config = {
        "addon": ADDON_NAME,
        "provider": "deterministic",
        "pipeline": "yomitoku_word_geometry_layout",
        "layout_method": LAYOUT_METHOD,
        "layout_version": LAYOUT_VERSION,
        "line_tolerance_ratio": LINE_TOLERANCE_RATIO,
    }

    # 2. Register the L3 tool.
    with get_sync_db_session() as session:
        statement = (
            insert(L3Tool)
            .values(
                id=uuid.uuid4(),
                name=TOOL_NAME,
                model_name=MODEL_NAME,
                prompt_version=PROMPT_VERSION,
                config=config,
                is_active=True,
            )
            .on_conflict_do_nothing(
                index_elements=[L3Tool.name]
            )
        )

        session.execute(statement)
        session.commit()

        # 3. Verify that the registered tool matches this implementation.
        result = session.execute(
            select(L3Tool).where(L3Tool.name == TOOL_NAME)
        )
        tool = result.scalar_one_or_none()

        if tool is None:
            raise RuntimeError(
                f"Failed to register L3Tool '{TOOL_NAME}'"
            )

        if (
            tool.model_name != MODEL_NAME
            or tool.prompt_version != PROMPT_VERSION
            or tool.config != config
        ):
            raise ValueError(
                f"L3Tool '{TOOL_NAME}' already exists with a different "
                "configuration. Register a new tool name/version instead."
            )

        print(f"-> L3Tool registered: {TOOL_NAME}")
        print(f"   model_name: {tool.model_name}")
        print(f"   prompt_version: {tool.prompt_version}")
        print(f"   config: {tool.config}")


if __name__ == "__main__":
    main()
