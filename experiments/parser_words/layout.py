from __future__ import annotations

from statistics import median
from typing import Any


def _point_xy(point: Any) -> tuple[float, float]:
    """YomiTokuのpointsを(x, y)座標に変換する。"""
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return float(point[0]), float(point[1])
    raise ValueError(f"Invalid point format: {point!r}")


def calculate_geometry(word: dict[str, Any]) -> dict[str, Any]:
    """word.pointsから外接矩形と中心座標を計算する。"""
    points = word.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("word.points must contain at least 3 points")

    coordinates = [_point_xy(point) for point in points]
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    return {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "center_x": sum(xs) / len(xs),
        "center_y": sum(ys) / len(ys),
        "width": x_max - x_min,
        "height": y_max - y_min,
    }


def _prepare_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """元のwordを保持しながらレイアウト用座標を追加する。"""
    prepared = []
    for index, word in enumerate(words):
        if not isinstance(word, dict):
            raise ValueError(f"words[{index}] must be an object")
        prepared.append({
            **word,
            "_layout": calculate_geometry(word),
            "_source_index": index,
        })
    return prepared


def _infer_text_direction(words: list[dict[str, Any]]) -> dict[str, Any]:
    """word矩形の縦横比を集計して文字列の主方向を推定する。

    画像全体の縦横比やEXIF情報は使わない。正方形に近いwordは
    判定材料から除外し、少数・拮抗時は横方向にフォールバックする。
    """
    horizontal_scores: list[float] = []
    vertical_scores: list[float] = []
    excluded_count = 0

    for word in words:
        geometry = word["_layout"]
        width, height = geometry["width"], geometry["height"]
        if width <= 0 or height <= 0:
            excluded_count += 1
            continue

        ratio = width / height
        if 0.80 <= ratio <= 1.25:
            excluded_count += 1
            continue

        strength = min(abs(ratio - 1.0), 3.0)
        if ratio > 1.25:
            horizontal_scores.append(strength)
        else:
            vertical_scores.append(strength)

    horizontal_score = sum(horizontal_scores)
    vertical_score = sum(vertical_scores)
    total_score = horizontal_score + vertical_score
    usable_count = len(horizontal_scores) + len(vertical_scores)

    if total_score == 0:
        direction, confidence, reason = "horizontal", 0.0, "no_directional_words_fallback"
    else:
        confidence = max(horizontal_score, vertical_score) / total_score
        if usable_count < 3:
            direction, confidence, reason = "horizontal", 0.0, "insufficient_directional_words_fallback"
        elif confidence < 0.65:
            direction, reason = "horizontal", "ambiguous_direction_fallback"
        elif horizontal_score > vertical_score:
            direction, reason = "horizontal", "word_boxes_are_wider"
        else:
            direction, reason = "vertical", "word_boxes_are_taller"

    return {
        "direction": direction,
        "confidence": round(confidence, 4),
        "reason": reason,
        "usable_word_count": usable_count,
        "excluded_word_count": excluded_count,
        "horizontal_word_count": len(horizontal_scores),
        "vertical_word_count": len(vertical_scores),
        "horizontal_score": round(horizontal_score, 4),
        "vertical_score": round(vertical_score, 4),
    }


def _group_by_axis(
    words: list[dict[str, Any]], tolerance: float, line_axis: str
) -> list[list[dict[str, Any]]]:
    """指定軸の中心座標でwordをグルーピングする。"""
    if line_axis == "y":
        center_key, secondary_key = "center_y", "center_x"
    elif line_axis == "x":
        center_key, secondary_key = "center_x", "center_y"
    else:
        raise ValueError(f"Unsupported line_axis: {line_axis}")

    sorted_words = sorted(
        words,
        key=lambda word: (
            word["_layout"][center_key],
            word["_layout"][secondary_key],
        ),
    )
    groups: list[list[dict[str, Any]]] = []

    for word in sorted_words:
        center = word["_layout"][center_key]
        best_group = None
        best_distance = None
        for group in groups:
            group_center = median(item["_layout"][center_key] for item in group)
            distance = abs(center - group_center)
            if distance <= tolerance and (best_distance is None or distance < best_distance):
                best_group, best_distance = group, distance
        if best_group is None:
            groups.append([word])
        else:
            best_group.append(word)
    return groups


def build_layout(
    words: list[dict[str, Any]], line_tolerance_ratio: float = 0.45
) -> dict[str, Any]:
    """OCR wordsを矩形の長辺方向に応じて行または列に再構成する。

    横方向の文字列はYで行をまとめてXで並べる。
    縦方向の文字列はXで列をまとめてYで並べる。
    座標自体の回転・変換は行わない。
    """
    if not 0 < line_tolerance_ratio <= 2:
        raise ValueError("line_tolerance_ratio must be between 0 and 2")
    if not words:
        raise ValueError("OCR words is empty")

    prepared = _prepare_words(words)
    direction_info = _infer_text_direction(prepared)
    direction = direction_info["direction"]

    if direction == "horizontal":
        line_axis, inline_axis = "y", "x"
        cross_sizes = [w["_layout"]["height"] for w in prepared if w["_layout"]["height"] > 0]
        reverse_groups = False
    else:
        line_axis, inline_axis = "x", "y"
        cross_sizes = [w["_layout"]["width"] for w in prepared if w["_layout"]["width"] > 0]
        # 日本語の縦書きを想定した列順。横倒しレシートでは要検証。
        reverse_groups = True

    if not cross_sizes:
        raise ValueError("Could not calculate word cross-axis sizes")
    median_cross_size = median(cross_sizes)
    tolerance = median_cross_size * line_tolerance_ratio
    groups = _group_by_axis(prepared, tolerance, line_axis)

    center_key = "center_y" if line_axis == "y" else "center_x"
    inline_key = "center_x" if inline_axis == "x" else "center_y"
    groups.sort(
        key=lambda group: median(word["_layout"][center_key] for word in group),
        reverse=reverse_groups,
    )

    output_rows = []
    for line_index, group in enumerate(groups):
        group.sort(key=lambda word: (word["_layout"][inline_key], word["_source_index"]))
        center_x = median(word["_layout"]["center_x"] for word in group)
        center_y = median(word["_layout"]["center_y"] for word in group)
        output_rows.append({
            "line_index": line_index,
            # center_yは既存利用側との互換性のため残す。
            "center_y": center_y,
            "center_x": center_x,
            "line_center": median(word["_layout"][center_key] for word in group),
            "text": " ".join(str(word.get("content", "")) for word in group),
            "words": group,
        })

    return {
        "layout_method": (
            "center_y_clustering_then_x_sort"
            if direction == "horizontal"
            else "center_x_clustering_then_y_sort"
        ),
        "text_direction": direction,
        "direction_inference": direction_info,
        "line_axis": line_axis,
        "inline_axis": inline_axis,
        "line_tolerance_ratio": line_tolerance_ratio,
        # 既存ログとの互換性のためキー名を維持。
        "median_word_height": median_cross_size,
        "median_cross_axis_size": median_cross_size,
        "line_tolerance_pixels": tolerance,
        "word_count": len(prepared),
        "line_count": len(output_rows),
        "rows": output_rows,
    }


def build_layout_preview(layout: dict[str, Any]) -> str:
    """人間が確認するための行・列再構成プレビューを作る。"""
    direction_info = layout.get("direction_inference", {})
    direction = layout.get("text_direction", "horizontal")
    line_axis = layout.get("line_axis", "y")

    lines = [
        "=== OCR Layout Preview ===",
        f"Words : {layout['word_count']}",
        f"Lines : {layout['line_count']}",
        f"Text direction : {direction}",
        f"Line axis : {line_axis}",
        f"Direction confidence : {direction_info.get('confidence', 0.0)}",
        f"Direction reason : {direction_info.get('reason', 'legacy_or_unknown')}",
        (
            "Direction words (H/V) : "
            f"{direction_info.get('horizontal_word_count', 0)} / "
            f"{direction_info.get('vertical_word_count', 0)}"
        ),
        (
            "Median cross-axis size : "
            f"{layout.get('median_cross_axis_size', layout['median_word_height']):.2f}"
        ),
        f"Line tolerance : {layout['line_tolerance_pixels']:.2f}",
        "",
    ]

    for row in layout["rows"]:
        position_label = "y" if line_axis == "y" else "x"
        lines.append(
            f"[LINE {row['line_index']:03d}] "
            f"{position_label}={row['line_center']:.1f}"
        )
        for word in row["words"]:
            geometry = word["_layout"]
            content = str(word.get("content", ""))
            det_score = word.get("det_score")
            rec_score = word.get("rec_score")
            lines.append(
                "  "
                f"x={geometry['center_x']:8.1f} "
                f"y={geometry['center_y']:8.1f} "
                f"w={geometry['width']:7.1f} "
                f"h={geometry['height']:7.1f} "
                f"det={det_score!s:>6} "
                f"rec={rec_score!s:>6} "
                f"{content}"
            )
        lines.append("")
    return "\n".join(lines)
