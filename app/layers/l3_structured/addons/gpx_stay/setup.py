# app/layers/l3_structured/addons/gpx_stay/setup.py
import uuid

import app.db_all_models  # SQLAlchemyマッピングのインポート関係を解決
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.db.models.l3_tools import L3Tool
from app.infrastructure.db.session import get_sync_db_session, sync_engine
from app.layers.l3_structured.addons.gpx_stay.detector import (
    DISTANCE_THRESHOLD_M,
    MAX_GAP_MINUTES,
    MIN_STAY_MINUTES,
)
from app.layers.l3_structured.addons.gpx_stay.models import GpxStay
from app.layers.l3_structured.addons.gpx_stay.service import TOOL_NAME, TOOL_VERSION


def main():
    print("Initializing GPX Stay DB Tables...")
    with sync_engine.begin() as connection:
        GpxStay.__table__.create(connection, checkfirst=True)

    with get_sync_db_session() as session:
        session.execute(
            insert(L3Tool).values(
                id=uuid.uuid4(),
                name=TOOL_NAME,
                model_name="deterministic_stay_detector",
                prompt_version=TOOL_VERSION,
                config={
                    "distance_threshold_m": DISTANCE_THRESHOLD_M,
                    "min_stay_minutes": MIN_STAY_MINUTES,
                    "max_gap_minutes": MAX_GAP_MINUTES,
                },
                is_active=True,
            ).on_conflict_do_nothing(index_elements=[L3Tool.name])
        )

        # 不変履歴（データプロベナンス）に反する上書きが無いか確認
        tool = session.execute(select(L3Tool).where(L3Tool.name == TOOL_NAME)).scalar_one()
        if tool.prompt_version != TOOL_VERSION:
            raise ValueError(f"Provenance mismatch for tool '{TOOL_NAME}'. Code version has been updated without updating tool records.")

        print(f"-> L3 Tool Configured: [ {TOOL_NAME} ] (Internal Version: {TOOL_VERSION})")

    print("GPX stay tables and tools are fully configured.")


if __name__ == "__main__":
    main()
