from __future__ import annotations

import re
from collections import Counter
from typing import Any

NUMERIC_CLASSIFICATION_METHOD = "numeric_classification_v1"

CLASS_LABELS = (
    "AMOUNT", "DATE", "TIME", "PHONE_NUMBER", "NUMBER",
    "PERCENTAGE", "QUANTITY", "COUNT", "UNCLASSIFIED",
)

DATE_PATTERNS = (
    re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日"),
    re.compile(r"\d{4}[年/／.-]\d{1,2}[月/／.-]\d{1,2}日?"),
    re.compile(r"\d{4}/\d{1,2}/\d{1,2}"),
)
TIME_PATTERNS = (
    re.compile(r"\d{1,2}\s*時\s*\d{1,2}\s*分(?:\s*\d{1,2}\s*秒)?"),
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),
)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:0\d{1,4}[-－]\d{1,4}[-－]\d{3,4}|0\d{9,10})(?!\d)"
)

AMOUNT_SUFFIX = re.compile(r"(?:円|¥|￥)")
AMOUNT_PREFIX = re.compile(r"[¥￥]")
PERCENTAGE_SUFFIX = re.compile(r"[%％]")
COUNT_SUFFIX = re.compile(r"(?:個|点|枚|本|冊|袋|件|回|台|人|着|食|杯|匹|頭|粒|組|セット)")
QUANTITY_SUFFIX = re.compile(
    r"(?:kg|ＫＧ|Kg|g|ｇ|mg|ｍｇ|L|Ｌ|ml|ｍｌ|mL|ＭＬ|km|ｋｍ|cm|ｃｍ|mm|ｍｍ)",
    re.IGNORECASE,
)
NUMBER_KEYWORD = re.compile(
    r"(?:No\.?|№|番号|ID|コード|登録番号|端末|レシート|伝票|承認|会員|カード)",
    re.IGNORECASE,
)


def _overlaps(start: int, end: int, match: re.Match[str]) -> bool:
    return start < match.end() and end > match.start()


def _matches_for_row(text: str, patterns: tuple[re.Pattern[str], ...]):
    return [m for pattern in patterns for m in pattern.finditer(text)]


def _classify_span(text: str, span: dict[str, Any]) -> dict[str, Any]:
    start, end = int(span["start"]), int(span["end"])
    evidence: list[str] = []

    for match in PHONE_PATTERN.finditer(text):
        if _overlaps(start, end, match):
            evidence.append(f"phone_pattern:{match.group(0)}")
            return {"label": "PHONE_NUMBER", "evidence": evidence}

    for match in _matches_for_row(text, DATE_PATTERNS):
        if _overlaps(start, end, match):
            evidence.append(f"date_pattern:{match.group(0)}")
            return {"label": "DATE", "evidence": evidence}

    for match in _matches_for_row(text, TIME_PATTERNS):
        if _overlaps(start, end, match):
            evidence.append(f"time_pattern:{match.group(0)}")
            return {"label": "TIME", "evidence": evidence}

    if any(s.get("type") == "YEN_SYMBOL" for s in span.get("internal_symbols", [])):
        evidence.append("internal_yen_symbol")
        return {"label": "AMOUNT", "evidence": evidence}
    if AMOUNT_PREFIX.search(text[:start][-2:]) or AMOUNT_SUFFIX.match(text[end:]):
        evidence.append("adjacent_currency_marker")
        return {"label": "AMOUNT", "evidence": evidence}

    percentage_match = PERCENTAGE_SUFFIX.match(text[end:])
    if percentage_match:
        evidence.append(f"percentage_symbol:{percentage_match.group(0)}")
        return {"label": "PERCENTAGE", "evidence": evidence}

    quantity_match = QUANTITY_SUFFIX.match(text[end:])
    if quantity_match:
        evidence.append(f"quantity_unit:{quantity_match.group(0)}")
        return {"label": "QUANTITY", "evidence": evidence}

    count_match = COUNT_SUFFIX.match(text[end:])
    if count_match:
        evidence.append(f"count_unit:{count_match.group(0)}")
        return {"label": "COUNT", "evidence": evidence}

    number_keyword = NUMBER_KEYWORD.search(text[:start][-32:])
    if number_keyword:
        evidence.append(f"number_keyword:{number_keyword.group(0)}")
        return {"label": "NUMBER", "evidence": evidence}

    if start > 0 and text[start - 1].isascii() and text[start - 1].isalpha():
        evidence.append(f"adjacent_latin_prefix:{text[start - 1]}")
        return {"label": "NUMBER", "evidence": evidence}

    return {"label": "UNCLASSIFIED", "evidence": ["no_matching_rule"]}


def build_numeric_classification(numeric_features: dict[str, Any]) -> dict[str, Any]:
    rows = numeric_features.get("rows")
    if not isinstance(rows, list):
        raise ValueError("numeric_features['rows'] must be a list")

    output_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in rows:
        row_text = str(row.get("text", ""))
        features = row.get("numeric_features", {})
        spans_out: list[dict[str, Any]] = []

        for span_index, span in enumerate(features.get("numeric_spans", [])):
            decision = _classify_span(row_text, span)
            counts[decision["label"]] += 1
            spans_out.append({
                "span_index": span_index,
                "text": span.get("text"),
                "start": span.get("start"),
                "end": span.get("end"),
                "label": decision["label"],
                "evidence": decision["evidence"],
                "context_before": span.get("context_before", ""),
                "context_after": span.get("context_after", ""),
                "internal_symbols": span.get("internal_symbols", []),
                "digit_tokens": span.get("digit_tokens", []),
            })

        output_rows.append({
            "line_index": row.get("line_index"),
            "row_type": row.get("row_type"),
            "text": row_text,
            "numeric_classifications": spans_out,
        })

    total = sum(counts.values())
    return {
        "numeric_classification_method": NUMERIC_CLASSIFICATION_METHOD,
        "source_numeric_feature_method": numeric_features.get("numeric_feature_method"),
        "classification_labels": list(CLASS_LABELS),
        "row_count": len(output_rows),
        "numeric_span_count": total,
        "classification_counts": {
            label: counts.get(label, 0) for label in CLASS_LABELS
        },
        "rows": output_rows,
    }


def build_numeric_classification_preview(result: dict[str, Any]) -> str:
    lines = [
        "=== Numeric Classification Preview ===",
        f"Method          : {result.get('numeric_classification_method')}",
        f"Rows            : {result.get('row_count')}",
        f"Numeric spans   : {result.get('numeric_span_count')}",
        "",
        "=== Classification Counts ===",
    ]
    for label, count in result.get("classification_counts", {}).items():
        lines.append(f"{label:16s}: {count}")

    lines.extend(["", "=== Row Classifications ===", ""])
    for row in result.get("rows", []):
        lines.append(f"[LINE {row.get('line_index')}] {row.get('text', '')}")
        for item in row.get("numeric_classifications", []):
            lines.append(
                f"  {item['text']!r} @{item['start']}:{item['end']} "
                f"=> {item['label']} | evidence={', '.join(item['evidence'])}"
            )
        lines.append("")
    return "\n".join(lines)
