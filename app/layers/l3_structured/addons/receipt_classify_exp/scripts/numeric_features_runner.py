from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.layers.l3_structured.addons.receipt_classify_exp.numeric_features import (
    build_numeric_features,
    build_numeric_features_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract numeric spans from structure.json")
    parser.add_argument("--structure-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("structure.json must contain a JSON object")
    return data


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.structure_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    result = build_numeric_features(load_json(args.structure_json))
    json_path = output_dir / "numeric_features.json"
    preview_path = output_dir / "numeric_features_preview.txt"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    preview_path.write_text(build_numeric_features_preview(result), encoding="utf-8")
    print(f"Rows: {result['row_count']}")
    print(f"Numeric spans: {result['numeric_span_count']}")
    print(f"Digit tokens: {result['digit_token_count']}")
    print(f"JSON: {json_path}")
    print(f"Preview: {preview_path}")


if __name__ == "__main__":
    main()
