from __future__ import annotations

import app.db_all_models  # noqa: F401 - load core SQLAlchemy models

from app.infrastructure.db.session import sync_engine

from .models import (
    YomitokuLayoutLine,
    YomitokuLayoutRun,
)


def main() -> None:
    """Create yomitoku_layout addon tables if they do not exist."""

    with sync_engine.begin() as connection:
        # Parent table first because layout_lines references layout_runs.
        YomitokuLayoutRun.__table__.create(
            connection,
            checkfirst=True,
        )

        YomitokuLayoutLine.__table__.create(
            connection,
            checkfirst=True,
        )

    print("yomitoku_layout tables are ready.")


if __name__ == "__main__":
    main()