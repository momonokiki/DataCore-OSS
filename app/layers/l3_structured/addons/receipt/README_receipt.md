# L3 Receipt Addon

添付 repository.txt の構成に合わせた追加実装。既存の test_reciept モデルは変更しません。
新規テーブル: addon_receipt_totals / addon_receipt_items。

## 導入
1. ZIP 内 app/ と tests/ のファイルをリポジトリに追加。
2. integration/tasks.py.patch を確認し `git apply integration/tasks.py.patch`。
   tasks.py の既存 parse_file_task の置換だけです。ingest の既存 chain は変更不要。
3. .env の ENABLED_L3_ADDONS に receipt を追加 (例 ENABLED_L3_ADDONS=receipt)。
4. PostgreSQL の既存コアテーブルがある環境で、実際に導入済みの Ollama モデル名を指定:
   `python -m app.layers.l3_structured.addons.receipt.setup_db --model <MODEL_NAME>`
5. parse_tasks キューを購読する Celery worker を再起動。

OLLAMA_BASE_URL は既存 settings のものを使用。Ollama モデルの取得は自動実行しません。
httpx / Pydantic / SQLAlchemy は既存 requirements に記載されており依存の追加は不要です。
サービス呼出し時には全コアモデルを app.db_all_models で登録します。

## 実行
`python -m app.layers.l3_structured.addons.receipt.run_parse --file-hash <SHA256> --artifact-id <OCR_UUID>`
`python -m app.layers.l3_structured.addons.receipt.inspect_receipt <RECEIPT_UUID>`
`python -m unittest discover -s tests -p test_receipt_schemas.py -v`

setup_db は2テーブルのみ checkfirst で作成。既存テーブルを ALTER しません。
現在の Alembic include_object は addon_ を除外するため、通常の autogenerate では管理されません。
既存 initializer の ENABLED_L3_ADDONS 動的ロードにも対応していますが、安全な初回作成には setup_db を使用。
本アドオンの将来の型・制約変更は明示的なDDL/専用マイグレーションで管理してください。

## データ契約
- 1 OCR成果物 = 1 レシート。複数枚をまとめた OCR やページ分割成果物は上流で整理が必要。
- source_artifact_id + parser_tool_id が一意。再実行は既存IDを返し品目を増やしません。
- 同じ原本で別OCRや別パーサーの結果は別レコード。集計時は採用結果を1つに選ぶ必要があります。
- L1 / L2 の削除は派生レシートも削除。合計の削除は品目も削除。
- 金額は Decimal / NUMERIC。未知はNULL。返品の負数を許容。
- 日付だけ判明した場合 transaction_date に保存し、transaction_at はNULL。
- 品目合計と支払総額が異なる場合は要確認。外税、全体値引き、端数処理を推測して修正しません。
- raw_payload は検証済みJSON。未加工のLLM応答文字列は保存しません。
- 1回目のDB読取を終了してからLLMを呼出し、保存時にOCR行をロックして再確認。
  同時推論は重複する場合がありますが、同じ成果物の二重保存は防止します。
- 保存は合計と品目を同じトランザクションで実施。API/検証/DB例外は握りつぶさずCelery FAILUREへ。
  自動retryは設定していません。原因解決後に再実行してください。
- 再解析による上書きやユーザー手修正の管理、API、採用結果選択、UIは今回の対象外。
- 所有権カラムは作らず、既存L1FileUpload等に基づいてAPI側で閲覧権限を判定してください。
  run_parse / inspect_receipt は管理者向けCLIであり、ユーザー用APIとして公開しないでください。
- tool 設定は同名で上書きせず、モデル変更時は新 --tool-name。
  パイプラインは既定 receipt_ollama_v1 を使うため、別名を使う場合はtaskのplugin_name指定を変更。
- settings.ENABLED_L3_ADDONS はtaskからの起動を制御。CLIの直接実行は明示操作として制御対象外。
- JSON Schema対応のOllamaとモデルが必要。実際の推論精度はレシート実物で評価してください。

## 検証範囲
Python構文検証とschemasの7件のテストを実施。実DB、Ollama、Celeryの結合試験は未実施。
本番投入前に初回保存、再実行、並行実行、誤ったOCR ID、通信失敗、削除連鎖を検証してください。
