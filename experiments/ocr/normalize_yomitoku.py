
#!/usr/bin/env python3
"""
Normalize YomiToku native JSON into a generic OCR representation.

Input:
    inspect_yomitoku_order.py が出力した candidate_00.json

Output:
    normalized_ocr.json
    normalized_text.md

注意:
    - OCRの読み順補正は行わない
    - 意味的な情報抽出は行わない
    - Nativeの座標情報を保持する
    - paragraphsとwordsを共通形式に変換する
"""

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict:
    """JSONファイルを読み込む。"""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_bbox(box: Any) -> list | None:
    """
    YomiTokuのboxから外接矩形を生成する。

    対応形式:
        [x1, y1, x2, y2]

        [
            [x1, y1],
            [x2, y2],
            [x3, y3],
            [x4, y4]
        ]
    """
    if not isinstance(box, (list, tuple)):
        return None

    # 矩形形式
    if len(box) == 4 and all(
        isinstance(v, (int, float)) for v in box
    ):
        return list(box)

    # ポリゴン形式
    points = []

    for point in box:
        if (
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and all(
                isinstance(v, (int, float))
                for v in point[:2]
            )
        ):
            points.append(point[:2])

    if not points:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    return [
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    ]


def normalize_region(region: dict, index: int) -> dict:
    """YomiToku paragraphを共通region形式に変換する。"""
    return {
        "id": f"region_{index:04d}",
        "type": "paragraph",
        "order": region.get("order"),
        "role": region.get("role"),
        "direction": region.get("direction"),
        "text": region.get("contents"),
        "bbox": get_bbox(region.get("box")),
        "native_box": region.get("box"),
    }


def normalize_word(word: dict, index: int) -> dict:
    """
    YomiToku wordを共通word形式に変換する。

    wordsはboxではなくpointsに座標が格納されている。
    元のpointsを保持し、bboxも生成する。
    """
    points = word.get("points")

    bbox = None

    if isinstance(points, (list, tuple)) and points:
        valid_points = [
            point
            for point in points
            if (
                isinstance(point, (list, tuple))
                and len(point) >= 2
                and all(
                    isinstance(v, (int, float))
                    for v in point[:2]
                )
            )
        ]

        if valid_points:
            xs = [point[0] for point in valid_points]
            ys = [point[1] for point in valid_points]

            bbox = [
                min(xs),
                min(ys),
                max(xs),
                max(ys),
            ]

    return {
        "id": f"word_{index:04d}",
        "text": word.get("content"),
        "direction": word.get("direction"),
        "bbox": bbox,
        "points": points,
        "recognition_score": word.get("rec_score"),
        "detection_score": word.get("det_score"),
    }


def normalize_collection(
    data: Any,
    collection_type: str,
) -> list:
    """
    tablesやfiguresなどのネイティブ情報を保持する。
    現段階では内部構造の意味付けは行わない。
    """
    if not isinstance(data, list):
        return []

    results = []

    for index, item in enumerate(data):
        results.append({
            "id": f"{collection_type}_{index:04d}",
            "type": collection_type,
            "native": item,
        })

    return results


def normalize(data: dict) -> dict:
    """YomiTokuネイティブ構造を共通OCR形式に変換する。"""
    paragraphs = data.get("paragraphs") or []
    words = data.get("words") or []

    return {
        "schema_version": "0.1",
        "document": {
            "engine": "yomitoku",
            "native_result_type": data.get(
                "native_result_type"
            ),
        },
        "pages": [
            {
                "page_number": 1,
                "regions": [
                    normalize_region(item, i)
                    for i, item in enumerate(paragraphs)
                    if isinstance(item, dict)
                ],
                "words": [
                    normalize_word(item, i)
                    for i, item in enumerate(words)
                    if isinstance(item, dict)
                ],
                "tables": normalize_collection(
                    data.get("tables"),
                    "table",
                ),
                "figures": normalize_collection(
                    data.get("figures"),
                    "figure",
                ),
            }
        ],
        # 元のネイティブ構造を保持する
        "native_source": data,
    }


def render_markdown(normalized: dict) -> str:
    """共通形式の内容を確認用Markdownに出力する。"""
    lines = [
        "# OCR normalized representation",
        "",
    ]

    for page in normalized["pages"]:
        lines.extend([
            f"## Page {page['page_number']}",
            "",
            "### Regions",
            "",
        ])

        for region in page["regions"]:
            lines.extend([
                (
                    f"#### {region['id']} "
                    f"(order={region['order']}, "
                    f"role={region['role']})"
                ),
                "",
                str(region["text"] or ""),
                "",
            ])

        lines.extend([
            "### Words",
            "",
        ])

        for word in page["words"]:
            lines.append(
                f"- {word['id']}: {word['text']} "
                f"(bbox={word['bbox']})"
            )

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Normalize YomiToku native OCR JSON."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Input YomiToku native JSON path",
    )

    parser.add_argument(
        "--output-dir",
        default="normalized",
        help="Output directory",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    native = load_json(input_path)
    normalized = normalize(native)

    json_path = output_dir / "normalized_ocr.json"
    markdown_path = output_dir / "normalized_text.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            normalized,
            f,
            ensure_ascii=False,
            indent=2,
        )

    markdown_path.write_text(
        render_markdown(normalized),
        encoding="utf-8",
    )

    page = normalized["pages"][0]

    valid_region_bbox = sum(
        region["bbox"] is not None
        for region in page["regions"]
    )

    valid_word_bbox = sum(
        word["bbox"] is not None
        for word in page["words"]
    )

    print("=== Normalization complete ===")
    print(f"Input: {input_path}")
    print(f"Regions: {len(page['regions'])}")
    print(
        f"Region bbox: "
        f"{valid_region_bbox}/{len(page['regions'])}"
    )
    print(f"Words: {len(page['words'])}")
    print(
        f"Word bbox: "
        f"{valid_word_bbox}/{len(page['words'])}"
    )
    print(f"Tables: {len(page['tables'])}")
    print(f"Figures: {len(page['figures'])}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()

