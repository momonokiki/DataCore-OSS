from __future__ import annotations

import app.db_all_models  # noqa: F401 - load core SQLAlchemy models
from sqlalchemy import inspect, text

from app.infrastructure.db.session import sync_engine
from .models import (
    ReceiptClassifyExpRun,
    ReceiptClassifyExpLine,
    ReceiptClassifyExpSpan,
)


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"]
        for column in inspect(connection).get_columns(table_name)
    }


def main() -> None:
    """Create addon tables and apply additive, idempotent review-column migrations."""
    with sync_engine.begin() as connection:
        # Parent tables first, so foreign keys can be created safely.
        ReceiptClassifyExpRun.__table__.create(connection, checkfirst=True)
        ReceiptClassifyExpLine.__table__.create(connection, checkfirst=True)
        ReceiptClassifyExpSpan.__table__.create(connection, checkfirst=True)

        # create(checkfirst=True) does not add columns to an existing table.
        # These ALTERs are additive and preserve all existing rows.
        if not _column_exists(
            connection, ReceiptClassifyExpSpan.__tablename__, "is_correct"
        ):
            connection.execute(text(
                f'ALTER TABLE "{ReceiptClassifyExpSpan.__tablename__}" '
                'ADD COLUMN is_correct BOOLEAN NULL'
            ))

        if not _column_exists(
            connection, ReceiptClassifyExpLine.__tablename__, "evaluation_note"
        ):
            connection.execute(text(
                f'ALTER TABLE "{ReceiptClassifyExpLine.__tablename__}" '
                'ADD COLUMN evaluation_note VARCHAR(500) NULL'
            ))

    print("receipt_classify_exp tables and review columns are ready.")
    print("Existing records were preserved; only missing tables/columns were added.")


if __name__ == "__main__":
    main()
