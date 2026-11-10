
#!/usr/bin/env python3
"""Normalize YomiToku word polygon coordinates.

Input:
  plugin_words_sorted.json produced by:
    python -m experiments.ocr.inspect_yomitoku_order

Coordinate system:
  Origin: image center
  X: left=-1.0, right=+1.0
  Y: top=-1.0, bottom=+1.0

Size:
  width  = bbox width / image width
  height = bbox height / image height

This script does not run OCR and does not read/write L2/L3 database tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_words(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        if isinstance(data.get("words"), list):
            data = data["words"]
        elif isinstance(data.get("metadata_json"), dict):
            data = data["metadata_json"].get("words", [])

    if not isinstance(data, list):
        raise ValueError(
            "Input JSON must be a word list or an object containing 'words'."
        )

    return [item for item in data if isinstance(item, dict)]


def point_xy(point: Any) -> tuple[float, float] | None:
    try:
        if isinstance(point, dict):
            x = point.get("x", point.get("X"))
            y = point.get("y", point.get("Y"))
        else:
            x, y = point[0], point[1]

        return float(x), float(y)

    except (TypeError, ValueError, IndexError, KeyError):
        return None


def get_points(word: dict[str, Any]) -> list[Any] | None:
    points = word.get("points")

    if points is None:
        points = word.get("box", word.get("bbox"))

    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return None

    return list(points)


def polygon_bounds(
    points: list[Any],
) -> tuple[float, float, float, float] | None:
    xy = [
        parsed
        for parsed in (point_xy(point) for point in points)
        if parsed is not None
    ]

    if len(xy) < 2:
        return None

    xs = [point[0] for point in xy]
    ys = [point[1] for point in xy]

    return min(xs), min(ys), max(xs), max(ys)


def normalize_point(
    point: Any,
    image_width: float,
    image_height: float,
) -> dict[str, float] | None:
    xy = point_xy(point)

    if xy is None:
        return None

    x, y = xy

    return {
        "x": round((x - image_width / 2) / (image_width / 2), 6),
        "y": round((y - image_height / 2) / (image_height / 2), 6),
    }


def normalize_word(
    word: dict[str, Any],
    index: int,
    image_width: float,
    image_height: float,
) -> dict[str, Any] | None:
    text = str(word.get("text") or word.get("content") or "").strip()
    source_points = get_points(word)

    if not text or source_points is None:
        return None

    bounds = polygon_bounds(source_points)

    if bounds is None:
        return None

    x1, y1, x2, y2 = bounds

    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    normalized_points = [
        normalized
        for normalized in (
            normalize_point(point, image_width, image_height)
            for point in source_points
        )
        if normalized is not None
    ]

    if len(normalized_points) < 2:
        return None

    return {
        "index": index,
        "text": text,
        "score": word.get("score", word.get("rec_score")),
        "det_score": word.get("det_score"),
        "direction": word.get("direction"),

        # Original polygon coordinates.
        "original": {
            "points": source_points,
            "bbox": {
                "x_min": round(x1, 2),
                "y_min": round(y1, 2),
                "x_max": round(x2, 2),
                "y_max": round(y2, 2),
            },
            "center": {
                "x": round(cx, 2),
                "y": round(cy, 2),
            },
            "size": {
                "width": round(x2 - x1, 2),
                "height": round(y2 - y1, 2),
            },
        },

        # Center-origin normalized coordinates.
        "points": normalized_points,

        "center": {
            "x": round((cx - image_width / 2) / (image_width / 2), 6),
            "y": round((cy - image_height / 2) / (image_height / 2), 6),
        },

        # Size is a ratio of the full image dimensions.
        "size": {
            "width": round((x2 - x1) / image_width, 6),
            "height": round((y2 - y1) / image_height, 6),
        },

        # Normalized bounding box.
        "bbox": {
            "x_min": round((x1 - image_width / 2) / (image_width / 2), 6),
            "y_min": round((y1 - image_height / 2) / (image_height / 2), 6),
            "x_max": round((x2 - image_width / 2) / (image_width / 2), 6),
            "y_max": round((y2 - image_height / 2) / (image_height / 2), 6),
        },
    }


def normalize_words(
    words: list[dict[str, Any]],
    image_width: float,
    image_height: float,
) -> list[dict[str, Any]]:
    normalized = []
    skipped = 0

    for index, word in enumerate(words):
        result = normalize_word(
            word,
            index,
            image_width,
            image_height,
        )

        if result is None:
            skipped += 1
            continue

        normalized.append(result)

    print(
        f"[INFO] input_words={len(words)} "
        f"usable_words={len(normalized)} "
        f"skipped_words={skipped}"
    )

    return normalized


def write_preview(
    path: Path,
    words: list[dict[str, Any]],
) -> None:
    lines = [
        "index | center_x | center_y | width | height | direction | text",
        "-" * 100,
    ]

    for word in words:
        center = word["center"]
        size = word["size"]

        lines.append(
            f'{word["index"]:03d} | '
            f'{center["x"]:>8.4f} | '
            f'{center["y"]:>8.4f} | '
            f'{size["width"]:>7.4f} | '
            f'{size["height"]:>7.4f} | '
            f'{str(word["direction"]):>10} | '
            f'{word["text"]}'
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize YomiToku word polygon coordinates."
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="plugin_words_sorted.json",
    )

    parser.add_argument(
        "--image-width",
        required=True,
        type=float,
        help="Width of the image used by YomiToku.",
    )

    parser.add_argument(
        "--image-height",
        required=True,
        type=float,
        help="Height of the image used by YomiToku.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    if args.image_width <= 0 or args.image_height <= 0:
        parser.error("Image width and height must be greater than zero.")

    source = args.input.expanduser().resolve()

    if not source.is_file():
        raise FileNotFoundError(source)

    raw_words = load_words(source)

    words = normalize_words(
        raw_words,
        args.image_width,
        args.image_height,
    )

    if not words:
        raise ValueError("No usable OCR words with polygon coordinates found.")

    output_dir = args.output_dir or source.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "source": str(source),
        "coordinate_system": {
            "origin": "image_center",
            "x_range": [-1.0, 1.0],
            "y_range": [-1.0, 1.0],
            "image_width": args.image_width,
            "image_height": args.image_height,
            "size_unit": "ratio_of_full_image",
        },
        "input_word_count": len(raw_words),
        "usable_word_count": len(words),
        "words": words,
    }

    json_path = output_dir / "yomitoku_coordinates_normalized.json"
    preview_path = output_dir / "yomitoku_coordinates_preview.txt"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_preview(preview_path, words)

    print(f"[OK] words={len(words)}")
    print(f"[OK] image_size={args.image_width}x{args.image_height}")
    print(f"[OK] JSON: {json_path}")
    print(f"[OK] Preview: {preview_path}")
    print("[INFO] No L2/L3 database records were changed.")


if __name__ == "__main__":
    main()
