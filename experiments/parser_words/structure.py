from __future__ import annotations

import re
from typing import Any


# ============================================================
# Character feature extraction
# ============================================================

# 全角数字を含む数字トークンを抽出する。
NUMBER_TOKEN_PATTERN = re.compile(r"\d+")


def extract_features(text: str) -> dict[str, Any]:
    """
    行テキストから文字・数字の有無を抽出する。

    数字: Unicode decimal digit (str.isdecimal)
    文字: Unicode alphabetic character (str.isalpha)
    記号・空白はどちらにも含めない。
    """
    number_tokens = NUMBER_TOKEN_PATTERN.findall(text)
    has_digit = any(char.isdecimal() for char in text)
    has_letter = any(char.isalpha() for char in text)

    return {
        "has_digit": has_digit,
        "has_letter": has_letter,
        "has_number": has_digit,  # 既存利用箇所との互換性
        "number_tokens": number_tokens,
        "digit_count": sum(char.isdecimal() for char in text),
        "letter_count": sum(char.isalpha() for char in text),
        "symbol_count": sum(
            not char.isdecimal() and not char.isalpha() and not char.isspace()
            for char in text
        ),
    }


def classify_row(features: dict[str, Any]) -> dict[str, Any]:
    """
    NUMERIC_ONLY: 数字あり、文字なし
    MIXED:        数字あり、文字あり
    TEXT_ONLY:    数字なし、文字あり
    SYMBOL_ONLY:  数字なし、文字なし（記号のみ・空白のみ・空文字）
    """
    has_digit = bool(features["has_digit"])
    has_letter = bool(features["has_letter"])

    if has_digit and has_letter:
        return {
            "row_type": "MIXED",
            "rules": ["contains_digit", "contains_letter"],
        }
    if has_digit:
        return {
            "row_type": "NUMERIC_ONLY",
            "rules": ["contains_digit", "no_letter"],
        }
    if has_letter:
        return {
            "row_type": "TEXT_ONLY",
            "rules": ["no_digit", "contains_letter"],
        }
    return {
        "row_type": "SYMBOL_ONLY",
        "rules": ["no_digit", "no_letter"],
    }


# ============================================================
# Structure builder
# ============================================================

def _copy_layout_word(word: dict[str, Any]) -> dict[str, Any]:
    """layout.pyが付与した単語情報を保持する。"""
    return {
        "source_index": word.get("_source_index"),
        "content": word.get("content"),
        "geometry": word.get("_layout"),
    }


def build_structure(layout: dict[str, Any]) -> dict[str, Any]:
    """
    layout.jsonのrowsを入力として、文字・数字の構成で分類する。

    行の生成・分割・結合・並び替えは行わない。
    rowsとline_indexはlayout.pyの出力順・値をそのまま尊重する。
    """
    source_rows = layout.get("rows")
    if not isinstance(source_rows, list):
        raise ValueError("layout['rows'] must be a list")

    output_rows: list[dict[str, Any]] = []

    for row in source_rows:
        text = str(row.get("text", ""))
        features = extract_features(text)
        classification = classify_row(features)

        words = [
            _copy_layout_word(word)
            for word in row.get("words", [])
        ]

        output_rows.append(
            {
                "line_index": row.get("line_index"),
                "center_x": row.get("center_x"),
                "center_y": row.get("center_y"),
                "line_center": row.get("line_center"),
                "text": text,
                "region": "UNCLASSIFIED",
                "row_type": classification["row_type"],
                "rules": classification["rules"],
                "features": features,
                "words": words,
            }
        )

    row_type_counts: dict[str, int] = {}
    for row in output_rows:
        row_type = row["row_type"]
        row_type_counts[row_type] = row_type_counts.get(row_type, 0) + 1

    return {
        "structure_method": "character_composition_row_classification_v1",
        "source_layout": {
            "layout_method": layout.get("layout_method"),
            "text_direction": layout.get("text_direction"),
            "direction_inference": layout.get("direction_inference"),
            "line_axis": layout.get("line_axis"),
            "inline_axis": layout.get("inline_axis"),
            "word_count": layout.get("word_count"),
            "line_count": layout.get("line_count"),
        },
        "row_count": len(output_rows),
        # runner.pyの既存manifest出力との互換性を維持する。
        "region_counts": {
            "UNCLASSIFIED": len(output_rows),
        },
        "row_type_counts": row_type_counts,
        "rows": output_rows,
    }


# ============================================================
# Preview
# ============================================================

def build_structure_preview(structure: dict[str, Any]) -> str:
    source_layout = structure.get("source_layout", {})

    lines = [
        "=== Character Composition Preview ===",
        f"Method         : {structure.get('structure_method')}",
        f"Rows           : {structure.get('row_count')}",
        f"Text direction : {source_layout.get('text_direction')}",
        f"Line axis      : {source_layout.get('line_axis')}",
        "",
        "=== Row Type Counts ===",
    ]

    for name, count in structure.get("row_type_counts", {}).items():
        lines.append(f"{name:12s}: {count}")

    lines.extend(["", "=== Row Classification ===", ""])

    for row in structure.get("rows", []):
        features = row.get("features", {})
        number_tokens = features.get("number_tokens", [])

        lines.append(
            f"[LINE {str(row.get('line_index')):>3}] "
            f"[{row.get('row_type', 'UNKNOWN')}]"
        )
        lines.append(f"  TEXT         : {row.get('text', '')}")
        lines.append(
            f"  HAS DIGIT    : {features.get('has_digit', False)}"
        )
        lines.append(
            f"  HAS LETTER   : {features.get('has_letter', False)}"
        )
        lines.append(
            f"  DIGIT COUNT  : {features.get('digit_count', 0)}"
        )
        lines.append(
            f"  LETTER COUNT : {features.get('letter_count', 0)}"
        )
        lines.append(
            f"  SYMBOL COUNT : {features.get('symbol_count', 0)}"
        )
        lines.append(
            "  NUMBER TOKENS: "
            + (", ".join(number_tokens) if number_tokens else "none")
        )
        lines.append("")

    return "\n".join(lines)
