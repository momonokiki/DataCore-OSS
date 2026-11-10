from __future__ import annotations

import re
from collections import Counter
from typing import Any


# ============================================================
# Numeric span extraction (v2)
# ============================================================
#
# 目的:
#   OCR行から「数字と、数値表記に使われる許容記号」が連続する範囲を抽出する。
#
# 処理:
#   1. numeric_span を抽出
#   2. span内部の数字列と記号を判定
#   3. span前後の文脈を取得
#
# 数値の意味（金額・数量・単価など）は判定しない。
# OCR原文の補正・正規化・再分割・再結合は行わない。
#
# 抽出時に許容する記号:
#   , ， . ． - － / ／ : ： + ¥ ￥
#
# 円・%・％・@・括弧などはnumeric_spanに含めず、
# span前後のcontextとして保持する。
# ============================================================

NUMERIC_SPAN_METHOD = "numeric_span_extraction_v2"

# 数字列。Unicodeの数字にも対応する。
DIGIT_PATTERN = re.compile(r"\d+")

# 数値表記範囲:
# - 任意の符号 (+/-)
# - 任意の通貨記号 (¥/￥)
# - 1桁以上の数字
# - 数字の後ろに、許容区切り記号 + 数字が続く構造
#
# 例:
#   1,234
#   4.43
#   2026/10/24
#   16:43:01
#   -5
#   ¥1,234
#
# 許容記号を無制限に連結しないよう、記号の後ろには必ず数字を要求する。
NUMERIC_SPAN_PATTERN = re.compile(
    r"(?<!\d)"
    r"[+-]?"
    r"(?:[¥￥])?"
    r"\d+"
    r"(?:[,，.．/／:：\-－]\d+)*"
    r"(?!\d)"
)

INTERNAL_SYMBOLS = {
    ",": "COMMA",
    "，": "COMMA",
    ".": "DOT",
    "．": "DOT",
    "-": "HYPHEN",
    "－": "HYPHEN",
    "/": "SLASH",
    "／": "SLASH",
    ":": "COLON",
    "：": "COLON",
    "+": "PLUS",
    "¥": "YEN_SYMBOL",
    "￥": "YEN_SYMBOL",
}


def _digit_tokens(span_text: str, span_start: int) -> list[dict[str, Any]]:
    """numeric_span内の数字列を、元の行に対する位置付きで返す。"""
    return [
        {
            "text": match.group(0),
            "start": span_start + match.start(),
            "end": span_start + match.end(),
        }
        for match in DIGIT_PATTERN.finditer(span_text)
    ]


def _internal_symbols(span_text: str, span_start: int) -> list[dict[str, Any]]:
    """numeric_span内部に含まれる許容記号を位置付きで返す。"""
    symbols: list[dict[str, Any]] = []
    for offset, char in enumerate(span_text):
        symbol_type = INTERNAL_SYMBOLS.get(char)
        if symbol_type is not None:
            symbols.append(
                {
                    "text": char,
                    "type": symbol_type,
                    "start": span_start + offset,
                    "end": span_start + offset + 1,
                }
            )
    return symbols


def _context_before(text: str, start: int) -> str:
    """span直前から、直前の空白までを文脈として取得する。"""
    prefix = text[:start]
    return prefix.split()[-1] if prefix.split() else ""


def _context_after(text: str, end: int) -> str:
    """span直後から、次の空白までを文脈として取得する。"""
    suffix = text[end:]
    return suffix.split()[0] if suffix.split() else ""


def extract_numeric_spans(text: str) -> dict[str, Any]:
    """
    1行のOCR文字列からnumeric_spanを抽出する。

    start/endは元の行文字列に対するPython文字列インデックス。
    span前後の文脈は空白区切りの直近トークンとして保持する。
    """
    spans: list[dict[str, Any]] = []

    for match in NUMERIC_SPAN_PATTERN.finditer(text):
        span_text = match.group(0)
        start = match.start()
        end = match.end()

        spans.append(
            {
                "text": span_text,
                "start": start,
                "end": end,
                "digit_tokens": _digit_tokens(span_text, start),
                "internal_symbols": _internal_symbols(span_text, start),
                "context_before": _context_before(text, start),
                "context_after": _context_after(text, end),
            }
        )

    return {
        "has_numeric_span": bool(spans),
        "numeric_span_count": len(spans),
        "digit_count": sum(
            len(token["text"])
            for span in spans
            for token in span["digit_tokens"]
        ),
        "numeric_spans": spans,
    }


def build_numeric_features(structure: dict[str, Any]) -> dict[str, Any]:
    """
    structure.jsonのrowsを利用する。
    行の分割・結合・並べ替えは行わず、line_indexと行順を維持する。
    """
    source_rows = structure.get("rows")
    if not isinstance(source_rows, list):
        raise ValueError("structure['rows'] must be a list")

    output_rows: list[dict[str, Any]] = []
    for source_row in source_rows:
        text = str(source_row.get("text", ""))
        output_rows.append(
            {
                "line_index": source_row.get("line_index"),
                "row_type": source_row.get("row_type"),
                "text": text,
                "numeric_features": extract_numeric_spans(text),
            }
        )

    span_count = sum(
        row["numeric_features"]["numeric_span_count"]
        for row in output_rows
    )
    digit_token_count = sum(
        len(span["digit_tokens"])
        for row in output_rows
        for span in row["numeric_features"]["numeric_spans"]
    )
    symbol_counts: Counter[str] = Counter(
        symbol["type"]
        for row in output_rows
        for span in row["numeric_features"]["numeric_spans"]
        for symbol in span["internal_symbols"]
    )

    return {
        "numeric_feature_method": NUMERIC_SPAN_METHOD,
        "extraction_policy": {
            "allowed_internal_symbols": [
                ",", "，", ".", "．", "-", "－", "/", "／",
                ":", "：", "+", "¥", "￥",
            ],
            "context_only_examples": ["円", "%", "％", "@", "(", ")"],
            "context_policy": "nearest whitespace-delimited token",
            "semantic_interpretation": False,
            "ocr_correction": False,
        },
        "source_structure_method": structure.get("structure_method"),
        "source_row_count": len(source_rows),
        "row_count": len(output_rows),
        "numeric_span_count": span_count,
        "digit_token_count": digit_token_count,
        "internal_symbol_counts": dict(sorted(symbol_counts.items())),
        "rows": output_rows,
    }


def _format_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "none"
    return ", ".join(
        f"{item['text']!r}@{item['start']}:{item['end']}"
        for item in items
    )


def build_numeric_features_preview(result: dict[str, Any]) -> str:
    lines = [
        "=== Numeric Span Extraction Preview ===",
        f"Method             : {result.get('numeric_feature_method')}",
        f"Rows               : {result.get('row_count')}",
        f"Numeric spans      : {result.get('numeric_span_count')}",
        f"Digit tokens       : {result.get('digit_token_count')}",
        f"Source             : {result.get('source_structure_method')}",
        "",
        "=== Extraction Policy ===",
        "Allowed symbols    : , ， . ． - － / ／ : ： + ¥ ￥",
        "Context examples   : 円 % ％ @ ( )",
        "Context policy     : nearest whitespace-delimited token",
        "Semantic inference : disabled",
        "OCR correction     : disabled",
        "",
        "=== Internal Symbol Counts ===",
    ]

    symbol_counts = result.get("internal_symbol_counts", {})
    if symbol_counts:
        for name, count in symbol_counts.items():
            lines.append(f"{name:16s}: {count}")
    else:
        lines.append("none")

    lines.extend(["", "=== Row Features ===", ""])
    for row in result.get("rows", []):
        features = row.get("numeric_features", {})
        lines.append(
            f"[LINE {str(row.get('line_index')):>3}] "
            f"[{row.get('row_type', 'UNKNOWN')}]"
        )
        lines.append(f"  TEXT : {row.get('text', '')}")

        spans = features.get("numeric_spans", [])
        if not spans:
            lines.append("  SPANS: none")
        else:
            for index, span in enumerate(spans, start=1):
                lines.append(
                    f"  SPAN {index}: {span['text']!r} "
                    f"@{span['start']}:{span['end']}"
                )
                lines.append(
                    f"    DIGITS   : "
                    f"{_format_items(span.get('digit_tokens', []))}"
                )
                symbols = [
                    {
                        "text": item["text"],
                        "start": item["start"],
                        "end": item["end"],
                    }
                    for item in span.get("internal_symbols", [])
                ]
                lines.append(
                    f"    SYMBOLS  : {_format_items(symbols)}"
                )
                lines.append(
                    f"    BEFORE   : {span.get('context_before', '')!r}"
                )
                lines.append(
                    f"    AFTER    : {span.get('context_after', '')!r}"
                )
        lines.append("")

    return "\n".join(lines)
