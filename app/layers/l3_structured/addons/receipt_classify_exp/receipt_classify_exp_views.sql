-- ============================================================
-- 1. Run Overview
--    1行 = 1回のNumeric Analysis実行
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_overview AS
SELECT
    r.id AS run_id,
    r.file_hash,
    r.source_artifact_id,
    r.tool_id,
    r.extraction_method,
    r.classification_method,
    r.created_at,

    r.row_count AS stored_row_count,
    r.span_count AS stored_span_count,

    COALESCE(l.line_count, 0) AS actual_line_count,
    COALESCE(s.span_count, 0) AS actual_span_count,

    COALESCE(s.reviewed_count, 0) AS reviewed_span_count,
    COALESCE(s.correct_count, 0) AS correct_span_count,
    COALESCE(s.incorrect_count, 0) AS incorrect_span_count,

    CASE
        WHEN COALESCE(s.reviewed_count, 0) = 0 THEN NULL
        ELSE ROUND(
            s.correct_count::numeric
            / s.reviewed_count * 100,
            2
        )
    END AS span_accuracy_percent,

    CASE
        WHEN COALESCE(s.span_count, 0) = 0 THEN NULL
        ELSE ROUND(
            s.reviewed_count::numeric
            / s.span_count * 100,
            2
        )
    END AS span_review_rate_percent

FROM addon_l3_receipt_classify_exp_runs r

LEFT JOIN (
    SELECT
        run_id,
        COUNT(*) AS line_count
    FROM addon_l3_receipt_classify_exp_lines
    GROUP BY run_id
) l ON l.run_id = r.id

LEFT JOIN (
    SELECT
        run_id,
        COUNT(*) AS span_count,
        COUNT(is_correct) AS reviewed_count,
        COUNT(*) FILTER (
            WHERE is_correct IS TRUE
        ) AS correct_count,
        COUNT(*) FILTER (
            WHERE is_correct IS FALSE
        ) AS incorrect_count
    FROM addon_l3_receipt_classify_exp_spans
    GROUP BY run_id
) s ON s.run_id = r.id;


-- ============================================================
-- 2. Receipt / Run Explorer
--    1行 = 1回の分析実行
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_receipts AS
SELECT
    r.id AS run_id,
    r.file_hash,
    r.source_artifact_id,
    r.tool_id,
    r.extraction_method,
    r.classification_method,
    r.created_at,

    r.row_count,
    r.span_count,

    COALESCE(l.line_count, 0) AS actual_line_count,
    COALESCE(s.span_count, 0) AS actual_span_count,
    COALESCE(s.reviewed_count, 0) AS reviewed_span_count,
    COALESCE(s.incorrect_count, 0) AS incorrect_span_count,

    CASE
        WHEN COALESCE(s.span_count, 0) = 0 THEN NULL
        ELSE ROUND(
            s.reviewed_count::numeric
            / s.span_count * 100,
            2
        )
    END AS review_rate_percent

FROM addon_l3_receipt_classify_exp_runs r

LEFT JOIN (
    SELECT
        run_id,
        COUNT(*) AS line_count
    FROM addon_l3_receipt_classify_exp_lines
    GROUP BY run_id
) l ON l.run_id = r.id

LEFT JOIN (
    SELECT
        run_id,
        COUNT(*) AS span_count,
        COUNT(is_correct) AS reviewed_count,
        COUNT(*) FILTER (
            WHERE is_correct IS FALSE
        ) AS incorrect_count
    FROM addon_l3_receipt_classify_exp_spans
    GROUP BY run_id
) s ON s.run_id = r.id;


-- ============================================================
-- 3. Line Explorer
--    1行 = 1つのOCR行
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_lines AS
SELECT
    l.id AS line_id,
    l.run_id,
    r.file_hash,
    r.source_artifact_id,

    l.line_index,
    l.row_type,
    l.line_text,

    l.numeric_features,
    l.numeric_classifications,

    l.evaluation_note,

    COALESCE(s.span_count, 0) AS span_count,
    COALESCE(s.reviewed_count, 0) AS reviewed_span_count,
    COALESCE(s.correct_count, 0) AS correct_span_count,
    COALESCE(s.incorrect_count, 0) AS incorrect_span_count,

    l.created_at

FROM addon_l3_receipt_classify_exp_lines l

JOIN addon_l3_receipt_classify_exp_runs r
    ON r.id = l.run_id

LEFT JOIN (
    SELECT
        line_id,
        COUNT(*) AS span_count,
        COUNT(is_correct) AS reviewed_count,
        COUNT(*) FILTER (
            WHERE is_correct IS TRUE
        ) AS correct_count,
        COUNT(*) FILTER (
            WHERE is_correct IS FALSE
        ) AS incorrect_count
    FROM addon_l3_receipt_classify_exp_spans
    WHERE line_id IS NOT NULL
    GROUP BY line_id
) s ON s.line_id = l.id;


-- ============================================================
-- 4. Span Explorer
--    1行 = 1つの数字Span
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_spans AS
SELECT
    s.id AS span_id,
    s.run_id,
    r.file_hash,
    r.source_artifact_id,

    s.line_id,
    s.line_index,
    l.line_text,

    s.span_index,
    s.span_text,
    s.label,

    s.start_offset,
    s.end_offset,

    s.evidence,
    s.raw_payload,

    s.is_correct,

    CASE
        WHEN s.is_correct IS TRUE THEN 'CORRECT'
        WHEN s.is_correct IS FALSE THEN 'INCORRECT'
        ELSE 'UNREVIEWED'
    END AS review_status,

    s.created_at

FROM addon_l3_receipt_classify_exp_spans s

JOIN addon_l3_receipt_classify_exp_runs r
    ON r.id = s.run_id

LEFT JOIN addon_l3_receipt_classify_exp_lines l
    ON l.id = s.line_id;


-- ============================================================
-- 5. Label Statistics
--    1行 = Run × Classification Label
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_label_stats AS
SELECT
    s.run_id,
    r.file_hash,
    r.source_artifact_id,
    s.label,

    COUNT(*) AS span_count,

    COUNT(s.is_correct) AS reviewed_count,

    COUNT(*) FILTER (
        WHERE s.is_correct IS TRUE
    ) AS correct_count,

    COUNT(*) FILTER (
        WHERE s.is_correct IS FALSE
    ) AS incorrect_count,

    COUNT(*) FILTER (
        WHERE s.is_correct IS NULL
    ) AS unreviewed_count,

    CASE
        WHEN COUNT(s.is_correct) = 0 THEN NULL
        ELSE ROUND(
            COUNT(*) FILTER (
                WHERE s.is_correct IS TRUE
            )::numeric
            / COUNT(s.is_correct) * 100,
            2
        )
    END AS accuracy_percent

FROM addon_l3_receipt_classify_exp_spans s

JOIN addon_l3_receipt_classify_exp_runs r
    ON r.id = s.run_id

GROUP BY
    s.run_id,
    r.file_hash,
    r.source_artifact_id,
    s.label;


-- ============================================================
-- 6. Error Analysis
--    1行 = 誤りと評価されたSpan
-- ============================================================

CREATE OR REPLACE VIEW v_receipt_classify_exp_error_analysis AS
SELECT
    s.id AS span_id,
    s.run_id,
    r.file_hash,
    r.source_artifact_id,

    s.line_id,
    s.line_index,
    l.line_text,

    s.span_index,
    s.span_text,
    s.label,

    s.start_offset,
    s.end_offset,

    s.evidence,
    s.raw_payload,

    s.created_at

FROM addon_l3_receipt_classify_exp_spans s

JOIN addon_l3_receipt_classify_exp_runs r
    ON r.id = s.run_id

LEFT JOIN addon_l3_receipt_classify_exp_lines l
    ON l.id = s.line_id

WHERE s.is_correct IS FALSE;
