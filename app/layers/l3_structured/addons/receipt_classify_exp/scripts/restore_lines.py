
from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select

from app.infrastructure.db.session import AsyncSessionLocal

from ..models import (
    ReceiptClassifyExpRun,
    ReceiptClassifyExpLine,
    ReceiptClassifyExpSpan,
)


def build_payload_maps(
    run: ReceiptClassifyExpRun,
) -> dict[int, dict[str, Any]]:
    """Validate and merge extraction/classification rows by line_index."""

    extraction_rows = run.extraction_payload.get("rows")
    classification_rows = run.classification_payload.get("rows")

    if not isinstance(extraction_rows, list):
        raise ValueError("extraction_payload.rows is not a list")

    if not isinstance(classification_rows, list):
        raise ValueError("classification_payload.rows is not a list")

    def to_map(
        rows: list[dict[str, Any]],
        payload_name: str,
    ) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}

        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{payload_name} contains a non-object row")

            if "line_index" not in row:
                raise ValueError(f"{payload_name} row has no line_index")

            index = int(row["line_index"])

            if index in result:
                raise ValueError(
                    f"Duplicate line_index={index} in {payload_name}"
                )

            result[index] = row

        return result

    extraction_map = to_map(extraction_rows, "extraction_payload")
    classification_map = to_map(
        classification_rows,
        "classification_payload",
    )

    if set(extraction_map) != set(classification_map):
        raise ValueError(
            "Extraction and classification line_index sets do not match"
        )

    merged: dict[int, dict[str, Any]] = {}

    for index, extraction_row in extraction_map.items():
        classification_row = classification_map[index]

        extraction_text = str(extraction_row.get("text", ""))
        classification_text = str(classification_row.get("text", ""))

        if extraction_text != classification_text:
            raise ValueError(
                f"text mismatch at line_index={index}: "
                f"extraction={extraction_text!r}, "
                f"classification={classification_text!r}"
            )

        if extraction_row.get("row_type") != classification_row.get("row_type"):
            raise ValueError(f"row_type mismatch at line_index={index}")

        numeric_features = extraction_row.get("numeric_features", {})
        numeric_classifications = classification_row.get(
            "numeric_classifications", []
        )

        if not isinstance(numeric_features, dict):
            raise ValueError(
                f"numeric_features is not an object at line_index={index}"
            )

        if not isinstance(numeric_classifications, list):
            raise ValueError(
                "numeric_classifications is not a list "
                f"at line_index={index}"
            )

        merged[index] = {
            "line_index": index,
            "row_type": str(
                classification_row.get("row_type") or "OCR_LINE"
            ),
            "line_text": classification_text,
            "numeric_features": numeric_features,
            "numeric_classifications": numeric_classifications,
        }

    if len(merged) != run.row_count:
        raise ValueError(
            f"Payload row count mismatch: "
            f"payload={len(merged)}, run.row_count={run.row_count}"
        )

    return merged


async def restore_run(
    run_id: uuid.UUID,
    apply: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            run = await session.get(ReceiptClassifyExpRun, run_id)

            if run is None:
                raise ValueError(f"Run not found: {run_id}")

            payload_map = build_payload_maps(run)

            existing_lines_result = await session.execute(
                select(ReceiptClassifyExpLine).where(
                    ReceiptClassifyExpLine.run_id == run_id
                )
            )
            existing_lines = {
                line.line_index: line
                for line in existing_lines_result.scalars().all()
            }

            existing_spans_result = await session.execute(
                select(ReceiptClassifyExpSpan).where(
                    ReceiptClassifyExpSpan.run_id == run_id
                )
            )
            existing_spans = existing_spans_result.scalars().all()

            if len(existing_spans) != run.span_count:
                raise ValueError(
                    f"Span count mismatch: "
                    f"DB={len(existing_spans)}, "
                    f"run.span_count={run.span_count}"
                )

            # Validate existing Span line indexes before changing anything.
            for span in existing_spans:
                if span.line_index is None:
                    raise ValueError(
                        f"Span {span.id} has NULL line_index; "
                        "cannot safely restore its line relationship"
                    )

                if span.line_index not in payload_map:
                    raise ValueError(
                        f"Span {span.id} references unknown "
                        f"line_index={span.line_index}"
                    )

            missing_indexes = sorted(
                set(payload_map) - set(existing_lines)
            )

            # Existing Line records are never overwritten.
            line_ids: dict[int, uuid.UUID] = {
                index: line.id
                for index, line in existing_lines.items()
            }

            if not apply:
                # Dry-run: calculate planned insertions and relationships.
                planned_links = sum(
                    1
                    for span in existing_spans
                    if span.line_id is None
                )

                print("DRY-RUN: no database changes were made")
                print(f"Run ID: {run_id}")
                print(f"Payload lines: {len(payload_map)}")
                print(f"Existing lines: {len(existing_lines)}")
                print(f"Lines to insert: {len(missing_indexes)}")
                print(f"Existing spans: {len(existing_spans)}")
                print(f"Spans to link: {planned_links}")
                print(
                    "Spans already linked: "
                    f"{len(existing_spans) - planned_links}"
                )

                return

            # Insert only missing Line records.
            for index in missing_indexes:
                data = payload_map[index]

                line = ReceiptClassifyExpLine(
                    run_id=run_id,
                    line_index=index,
                    row_type=data["row_type"],
                    line_text=data["line_text"],
                    numeric_features=data["numeric_features"],
                    numeric_classifications=data[
                        "numeric_classifications"
                    ],
                )
                session.add(line)
                await session.flush()

                line_ids[index] = line.id

            # Link existing Span records without recreating or overwriting them.
            linked_count = 0

            for span in existing_spans:
                expected_line_id = line_ids[span.line_index]

                if span.line_id is None:
                    span.line_id = expected_line_id
                    linked_count += 1
                elif span.line_id != expected_line_id:
                    raise ValueError(
                        f"Span {span.id} is already linked to a different "
                        f"Line: current={span.line_id}, "
                        f"expected={expected_line_id}"
                    )

            await session.flush()

            # Verify final counts inside the transaction.
            line_count_result = await session.execute(
                select(func.count())
                .select_from(ReceiptClassifyExpLine)
                .where(ReceiptClassifyExpLine.run_id == run_id)
            )
            final_line_count = line_count_result.scalar_one()

            span_count_result = await session.execute(
                select(func.count())
                .select_from(ReceiptClassifyExpSpan)
                .where(
                    ReceiptClassifyExpSpan.run_id == run_id,
                    ReceiptClassifyExpSpan.line_id.is_not(None),
                )
            )
            linked_span_count = span_count_result.scalar_one()

            if final_line_count != len(payload_map):
                raise ValueError(
                    f"Final Line count mismatch: "
                    f"expected={len(payload_map)}, actual={final_line_count}"
                )

            if linked_span_count != len(existing_spans):
                raise ValueError(
                    f"Final linked Span count mismatch: "
                    f"expected={len(existing_spans)}, "
                    f"actual={linked_span_count}"
                )

            print("RESTORE COMPLETED")
            print(f"Run ID: {run_id}")
            print(f"Inserted Lines: {len(missing_indexes)}")
            print(f"Total Lines: {final_line_count}")
            print(f"New Span relationships: {linked_count}")
            print(f"Total linked Spans: {linked_span_count}")

    # The transaction is committed when session.begin() exits successfully.


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore missing receipt classification Line records"
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Target ReceiptClassifyExpRun UUID",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this option, runs in dry-run mode.",
    )

    args = parser.parse_args()

    try:
        run_id = uuid.UUID(args.run_id)
    except ValueError as exc:
        parser.error(f"Invalid UUID: {args.run_id}")

    asyncio.run(restore_run(run_id=run_id, apply=args.apply))


if __name__ == "__main__":
    main()
