
from __future__ import annotations

import argparse
import asyncio
import copy
import platform
import sys
import time
from pathlib import Path
from typing import Any

from experiments.common.io import (
    base_manifest,
    new_experiment_dir,
    sha256_text,
    write_json,
)

from experiments.parser_words.runner import (
    load_artifact_words,
    build_source_manifest,
    build_layout_manifest,
    build_structure_manifest,
)

from experiments.parser_words.layout import (
    build_layout,
    build_layout_preview,
)

from experiments.parser_words.structure import (
    build_structure,
    build_structure_preview,
)

from experiments.parser_words.numeric_features import (
    build_numeric_features,
    build_numeric_features_preview,
)

from experiments.parser_words.numeric_classification import (
    build_numeric_classification,
    build_numeric_classification_preview,
)


DEFAULT_OUTPUT_DIR = Path(
    "experiments/parser_words/results"
)


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run numeric span extraction and classification "
            "pipeline from L2 OCR artifact"
        )
    )

    parser.add_argument(
        "--file-hash",
        required=True,
        help="L1 file SHA-256 hash",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Experiment output directory",
    )

    parser.add_argument(
        "--line-tolerance-ratio",
        type=float,
        default=0.45,
        help="Row grouping tolerance relative to median word height",
    )

    parser.add_argument(
        "--label",
        default=None,
        help="Optional experiment label",
    )

    return parser.parse_args()


# ============================================================
# Helpers
# ============================================================

def write_preview(
    path: Path,
    content: str,
) -> None:
    path.write_text(
        content,
        encoding="utf-8",
    )


def build_pipeline_manifest(
    *,
    file_hash: str,
    artifact_id: str,
    words: list[dict[str, Any]],
    input_hash: str,
    layout: dict[str, Any],
    layout_hash: str,
    structure: dict[str, Any],
    numeric_features: dict[str, Any],
    numeric_classification: dict[str, Any],
    line_tolerance_ratio: float,
) -> dict[str, Any]:

    return {
        "source": build_source_manifest(
            file_hash=file_hash,
            artifact_id=artifact_id,
            words=words,
            input_hash=input_hash,
        ),
        "layout": build_layout_manifest(
            layout,
            layout_hash,
            line_tolerance_ratio,
        ),
        "structure": build_structure_manifest(
            structure,
        ),
        "numeric_features": {
            "row_count": numeric_features.get("row_count"),
            "span_count": numeric_features.get("span_count"),
        },
        "numeric_classification": {
            "row_count": numeric_classification.get("row_count"),
            "span_count": numeric_classification.get("span_count"),
            "classification_counts": (
                numeric_classification.get(
                    "classification_counts"
                )
            ),
        },
    }


# ============================================================
# Main
# ============================================================

async def main() -> None:

    args = parse_args()

    started = time.perf_counter()

    file_hash = args.file_hash.lower()

    experiment_dir = new_experiment_dir(
        args.output_dir
    )

    manifest = base_manifest(
        "receipt_numeric_pipeline"
    )

    manifest.update(
        {
            "label": args.label,
            "file_hash": file_hash,
            "line_tolerance_ratio": (
                args.line_tolerance_ratio
            ),
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
            },
            "stages": [
                "l2_ocr_loading",
                "coordinate_layout",
                "receipt_structure",
                "numeric_span_extraction",
                "numeric_classification",
            ],
        }
    )

    write_json(
        experiment_dir / "manifest.json",
        manifest,
    )

    try:

        # ----------------------------------------------------
        # 1. Load L2 OCR artifact
        # ----------------------------------------------------

        print("[1/5] Loading L2 OCR artifact...")

        words, artifact_id = await load_artifact_words(
            file_hash
        )

        input_payload = {
            "file_hash": file_hash,
            "artifact_id": artifact_id,
            "words": words,
        }

        input_hash = sha256_text(
            __import__("json").dumps(
                input_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

        write_json(
            experiment_dir / "input.json",
            input_payload,
        )

        print(f"  artifact_id: {artifact_id}")
        print(f"  word_count : {len(words)}")

        # ----------------------------------------------------
        # 2. Coordinate layout
        # ----------------------------------------------------

        print("[2/5] Building coordinate layout...")

        layout_words = copy.deepcopy(words)

        orientation_info = {
            "rotation_degrees": 0,
            "rotation_direction": "none",
            "reason": "original_ocr_coordinates",
            "coordinate_transform_applied": False,
        }

        layout = build_layout(
            layout_words,
            line_tolerance_ratio=args.line_tolerance_ratio,
        )

        write_json(
            experiment_dir / "layout_input_words.json",
            {
                "image": orientation_info,
                "words": layout_words,
            },
        )

        write_json(
            experiment_dir / "layout.json",
            layout,
        )

        write_preview(
            experiment_dir / "layout_preview.txt",
            build_layout_preview(layout),
        )

        layout_text = __import__("json").dumps(
            layout,
            ensure_ascii=False,
            indent=2,
        )

        layout_hash = sha256_text(
            layout_text
        )

        print(
            f"  line_count : {layout['line_count']}"
        )

        # ----------------------------------------------------
        # 3. Receipt structure
        # ----------------------------------------------------

        print("[3/5] Building receipt structure...")

        structure = build_structure(
            layout
        )

        write_json(
            experiment_dir / "structure.json",
            structure,
        )

        write_preview(
            experiment_dir / "structure_preview.txt",
            build_structure_preview(structure),
        )

        print(
            f"  row_count : {structure['row_count']}"
        )

        # ----------------------------------------------------
        # 4. Numeric span extraction
        # ----------------------------------------------------

        print("[4/5] Building numeric features...")

        numeric_features = build_numeric_features(
            structure
        )

        write_json(
            experiment_dir / "numeric_features.json",
            numeric_features,
        )

        write_preview(
            experiment_dir / "numeric_features_preview.txt",
            build_numeric_features_preview(
                numeric_features
            ),
        )

        print(
            f"  rows  : {numeric_features.get('row_count')}"
        )

        print(
            f"  spans : {numeric_features.get('span_count')}"
        )

        # ----------------------------------------------------
        # 5. Numeric classification
        # ----------------------------------------------------

        print("[5/5] Building numeric classification...")

        numeric_classification = (
            build_numeric_classification(
                numeric_features
            )
        )

        write_json(
            experiment_dir / "numeric_classification.json",
            numeric_classification,
        )

        write_preview(
            experiment_dir / "numeric_classification_preview.txt",
            build_numeric_classification_preview(
                numeric_classification
            ),
        )

        print(
            f"  rows  : {numeric_classification.get('row_count')}"
        )

        print(
            f"  spans : {numeric_classification.get('span_count')}"
        )

        # ----------------------------------------------------
        # Manifest
        # ----------------------------------------------------

        pipeline_summary = build_pipeline_manifest(
            file_hash=file_hash,
            artifact_id=artifact_id,
            words=words,
            input_hash=input_hash,
            layout=layout,
            layout_hash=layout_hash,
            structure=structure,
            numeric_features=numeric_features,
            numeric_classification=numeric_classification,
            line_tolerance_ratio=args.line_tolerance_ratio,
        )

        manifest.update(
            {
                "status": "completed",
                **pipeline_summary,
                "execution": {
                    "database_write": False,
                    "llm_executed": False,
                },
                "elapsed_seconds": (
                    time.perf_counter() - started
                ),
            }
        )

        write_json(
            experiment_dir / "manifest.json",
            manifest,
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print()
        print("========================================")
        print("Numeric pipeline completed")
        print("========================================")
        print(f"Output      : {experiment_dir}")
        print(f"File hash   : {file_hash}")
        print(f"Artifact ID : {artifact_id}")
        print(f"Words       : {len(words)}")
        print(f"Lines       : {layout['line_count']}")
        print(f"Rows        : {structure['row_count']}")
        print(
            f"Numeric spans : "
            f"{numeric_features.get('span_count')}"
        )
        print(
            f"Classified spans : "
            f"{numeric_classification.get('span_count')}"
        )
        print(
            f"Elapsed     : "
            f"{manifest['elapsed_seconds']:.2f}s"
        )
        print("========================================")

    except Exception as exc:

        manifest.update(
            {
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": (
                    time.perf_counter() - started
                ),
            }
        )

        write_json(
            experiment_dir / "manifest.json",
            manifest,
        )

        write_json(
            experiment_dir / "error.json",
            {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )

        raise


if __name__ == "__main__":
    asyncio.run(main())
