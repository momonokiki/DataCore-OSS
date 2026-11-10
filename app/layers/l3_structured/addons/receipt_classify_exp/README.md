# receipt_classify_exp

独立したL3実験アドオン。既存の `receipt` アドオンのテーブル・処理には依存しません。

## 保存先

- `addon_l3_receipt_classify_exp_runs`: 実行単位。Extraction/ClassificationのJSON全体をJSONBで保持。
- `addon_l3_receipt_classify_exp_spans`: Span単位の検索・集計用データ。

JSONBが実験出力の正本で、Spanテーブルは検索用の投影です。

## セットアップ

```bash
python -m app.layers.l3_structured.addons.receipt_classify_exp.setup
```

`setup.py` は専用テーブルを `checkfirst=True` で作成した後、`L3Tool` を登録します。既存ツールのprovenanceが異なる場合は上書きせず停止します。

## Service

`classify_receipt_file(session, file_hash, parent_ocr_id)` がL2の `ocr_text` 成果物を読み、Extraction v2とClassification v1を実行してDBに保存します。

現行L2 OCRは `L2Artifact.content_text` に全文文字列を保存しているため、Serviceでは `splitlines()` により行を作ります。行順・行文字列は維持し、行の意味や表構造は推定しません。

同じOCR成果物と同じL3Toolの組み合わせは一度だけ保存します。再実行時は `already_exists` を返します。別バージョンのツール名を登録すれば、同じOCR成果物で比較実験できます。

## Celery

`app/tasks.py` に `tasks.classify_receipt_numeric` を `parse_tasks` queueで登録し、OCR context (`file_hash`, `artifact_id`) を渡します。Workerは既に `parse_tasks` を購読している構成です。


### Line-level persistence

Every OCR line is stored in `addon_l3_receipt_classify_exp_lines`, including lines
that contain no numeric spans. `line_text` preserves the complete source line;
`numeric_features` and `numeric_classifications` retain the per-line JSON details.
Span rows reference the corresponding line through `line_id` while retaining
`line_index` for straightforward filtering. The run-level JSONB payloads remain
the complete original outputs.

## Manual evaluation fields

- `addon_l3_receipt_classify_exp_spans.is_correct`: nullable Boolean. `NULL` means
  not reviewed, `TRUE` means correct (○), and `FALSE` means incorrect (×).
- `addon_l3_receipt_classify_exp_lines.evaluation_note`: nullable short text
  (`VARCHAR(500)`) for line-level review notes, observations, or analysis.

The setup script applies these columns additively to existing tables. It does not
recreate tables or delete existing rows. Re-running setup is safe.
