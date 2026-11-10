from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.common.io import write_json
from experiments.parser_words.numeric_features import (
    build_numeric_features,
    build_numeric_features_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract numeric spans from structure.json"
    )
    parser.add_argument(
        "--structure-json",
        type=Path,
        required=True,
        help="Path to an existing structure.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: structure.json parent directory)",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("structure.json must contain a JSON object")
    return data


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.structure_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    structure = load_json(args.structure_json)
    result = build_numeric_features(structure)

    json_path = output_dir / "numeric_features.json"
    preview_path = output_dir / "numeric_features_preview.txt"

    write_json(json_path, result)
    preview_path.write_text(
        build_numeric_features_preview(result),
        encoding="utf-8",
    )

    print("========================================")
    print("Numeric span extraction completed")
    print("========================================")
    print(f"Input  : {args.structure_json}")
    print(f"Output : {json_path}")
    print(f"Preview: {preview_path}")
    print(f"Rows   : {result['row_count']}")
    print(f"Spans  : {result['numeric_span_count']}")
    print(f"Digits : {result['digit_token_count']}")
    print("========================================")


if __name__ == "__main__":
    main()
