from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.common.io import write_json
from experiments.parser_words.numeric_classification import (
    build_numeric_classification,
    build_numeric_classification_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify numeric spans from numeric_features.json"
    )
    parser.add_argument(
        "--numeric-features-json",
        type=Path,
        required=True,
        help="Path to an existing numeric_features.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: input file parent directory)",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("numeric_features.json must contain a JSON object")
    return data


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.numeric_features_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    numeric_features = load_json(args.numeric_features_json)
    result = build_numeric_classification(numeric_features)

    json_path = output_dir / "numeric_classification.json"
    preview_path = output_dir / "numeric_classification_preview.txt"

    write_json(json_path, result)
    preview_path.write_text(
        build_numeric_classification_preview(result),
        encoding="utf-8",
    )

    print("========================================")
    print("Numeric classification completed")
    print("========================================")
    print(f"Input  : {args.numeric_features_json}")
    print(f"Output : {json_path}")
    print(f"Preview: {preview_path}")
    print(f"Rows   : {result['row_count']}")
    print(f"Spans  : {result['numeric_span_count']}")
    for label, count in result["classification_counts"].items():
        print(f"{label:16s}: {count}")
    print("========================================")


if __name__ == "__main__":
    main()
