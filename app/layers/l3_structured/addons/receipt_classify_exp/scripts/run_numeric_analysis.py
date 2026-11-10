from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.layers.l3_structured.addons.receipt_classify_exp.numeric_features import (
    build_numeric_features, build_numeric_features_preview,
)
from app.layers.l3_structured.addons.receipt_classify_exp.numeric_classification import (
    build_numeric_classification, build_numeric_classification_preview,
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Run receipt numeric extraction and classification")
    parser.add_argument("--structure-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    out = args.output_dir or args.structure_json.parent
    out.mkdir(parents=True, exist_ok=True)

    features = build_numeric_features(load_json(args.structure_json))
    features_path = out / "numeric_features.json"
    features_path.write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "numeric_features_preview.txt").write_text(
        build_numeric_features_preview(features), encoding="utf-8"
    )

    classified = build_numeric_classification(features)
    classified_path = out / "numeric_classification.json"
    classified_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "numeric_classification_preview.txt").write_text(
        build_numeric_classification_preview(classified), encoding="utf-8"
    )

    print("=== Receipt Numeric Analysis ===")
    print(f"Extraction method: {features['numeric_feature_method']}")
    print(f"Classification method: {classified['numeric_classification_method']}")
    print(f"Rows: {classified['row_count']}")
    print(f"Spans: {classified['numeric_span_count']}")
    for label, count in classified["classification_counts"].items():
        print(f"{label:16s}: {count}")
    print(f"Output directory: {out}")


if __name__ == "__main__":
    main()
