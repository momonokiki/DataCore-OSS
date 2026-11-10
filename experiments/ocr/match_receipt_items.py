
from __future__ import annotations

import argparse
import json
import re
import statistics

from pathlib import Path
from typing import Any


def load_words(path: Path) -> list[dict[str, Any]]:
    """正規化済みYomiToku JSONからOCR文字列を読み込む。"""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    words = data.get("words", [])

    if not isinstance(words, list):
        raise ValueError("入力JSONの words が list ではありません")

    return [word for word in words if isinstance(word, dict)]


def get_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_center(word: dict[str, Any]) -> tuple[float, float] | None:
    """center、またはbbox / pointsから中心座標を取得する。"""

    center = word.get("center")

    if isinstance(center, dict):
        x = get_number(center.get("x"))
        y = get_number(center.get("y"))

        if x is not None and y is not None:
            return x, y

    if isinstance(center, (list, tuple)) and len(center) >= 2:
        x = get_number(center[0])
        y = get_number(center[1])

        if x is not None and y is not None:
            return x, y

    bbox = word.get("bbox")

    if isinstance(bbox, dict):
        x1 = get_number(bbox.get("x1", bbox.get("left")))
        y1 = get_number(bbox.get("y1", bbox.get("top")))
        x2 = get_number(bbox.get("x2", bbox.get("right")))
        y2 = get_number(bbox.get("y2", bbox.get("bottom")))

        if None not in (x1, y1, x2, y2):
            return (x1 + x2) / 2, (y1 + y2) / 2

    points = word.get("points")

    if isinstance(points, list) and points:
        xs = []
        ys = []

        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                x = get_number(point[0])
                y = get_number(point[1])

                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)

        if xs and ys:
            return statistics.mean(xs), statistics.mean(ys)

    return None


def get_height(word: dict[str, Any]) -> float | None:
    size = word.get("size")

    if isinstance(size, dict):
        return get_number(size.get("height"))

    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return get_number(size[1])

    return None


def normalize_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Markdown整形に必要な情報だけを取り出す。"""

    result = []

    for word in words:
        text = str(word.get("text", "")).strip()

        if not text:
            continue

        center = get_center(word)

        if center is None:
            continue

        x, y = center

        result.append({
            "text": text,
            "x": x,
            "y": y,
            "height": get_height(word),
            "score": get_number(word.get("score")),
            "direction": word.get("direction"),
        })

    return result


def calculate_row_tolerance(words: list[dict[str, Any]]) -> float:
    """文字の高さを基準に、同じ行とみなすY方向の許容幅を決める。"""

    heights = [
        word["height"]
        for word in words
        if word["height"] is not None and word["height"] > 0
    ]

    if not heights:
        return 0.006

    median_height = statistics.median(heights)

    return max(0.004, min(0.012, median_height * 0.65))


def group_rows(
    words: list[dict[str, Any]],
    tolerance: float,
) -> list[list[dict[str, Any]]]:
    """Y座標が近いOCR文字列を視覚的な行としてまとめる。"""

    sorted_words = sorted(words, key=lambda w: (w["y"], w["x"]))

    rows: list[list[dict[str, Any]]] = []

    for word in sorted_words:
        if not rows:
            rows.append([word])
            continue

        current_row = rows[-1]
        row_y = statistics.median(item["y"] for item in current_row)

        if abs(word["y"] - row_y) <= tolerance:
            current_row.append(word)
        else:
            rows.append([word])

    for row in rows:
        row.sort(key=lambda w: w["x"])

    return rows


def join_text(row: list[dict[str, Any]]) -> str:
    """日本語の不要な空白を抑えながら、OCR文字列を連結する。"""

    result = ""

    japanese_pattern = re.compile(r"[ぁ-んァ-ヶー一-龠々]")

    for word in row:
        text = word["text"]

        if not result:
            result = text
            continue

        previous = result[-1]
        current = text[0]

        previous_is_japanese = bool(japanese_pattern.search(previous))
        current_is_japanese = bool(japanese_pattern.search(current))

        if previous_is_japanese and current_is_japanese:
            result += text
        else:
            result += " " + text

    return result


def render_markdown(
    rows: list[list[dict[str, Any]]],
    input_path: Path,
    tolerance: float,
) -> str:
    lines = [
        "# レシートOCR結果",
        "",
        f"- 入力ファイル: `{input_path.name}`",
        f"- OCR文字数: {sum(len(row) for row in rows)}",
        f"- 行数: {len(rows)}",
        f"- 行判定許容幅: `{tolerance:.4f}`",
        "",
        "## OCR読み取り結果",
        "",
        "| No. | Y座標 | OCRテキスト |",
        "|---:|---:|---|",
    ]

    for index, row in enumerate(rows, start=1):
        y = statistics.median(word["y"] for word in row)
        text = join_text(row)
        text = text.replace("|", r"\|").replace("\n", " ")

        lines.append(f"| {index:03d} | {y:.4f} | {text} |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YomiToku OCR結果をMarkdownに整形する"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="yomitoku_coordinates_normalized.json",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="出力Markdownファイル",
    )

    parser.add_argument(
        "--row-tolerance",
        type=float,
        default=None,
        help="行判定のY座標許容幅。省略時は文字サイズから自動算出",
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    raw_words = load_words(input_path)
    words = normalize_words(raw_words)

    if not words:
        raise ValueError("有効なOCR文字列がありません")

    tolerance = (
        args.row_tolerance
        if args.row_tolerance is not None
        else calculate_row_tolerance(words)
    )

    rows = group_rows(words, tolerance)

    output_path = (
        Path(args.output)
        if args.output
        else input_path.parent / "receipt_item_matches_preview.md"
    )

    markdown = render_markdown(rows, input_path, tolerance)

    output_path.write_text(markdown, encoding="utf-8")

    print(f"Input words : {len(raw_words)}")
    print(f"Valid words : {len(words)}")
    print(f"Rows        : {len(rows)}")
    print(f"Tolerance   : {tolerance:.4f}")
    print(f"Output      : {output_path}")


if __name__ == "__main__":
    main()

