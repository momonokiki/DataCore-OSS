# DataCore experiments

DataCore の本番パイプライン・DB登録処理から独立して、OCR出力とレシートParserのプロンプトを比較するための実験用スクリプト群です。

## 方針

- OCR実験は既存の `YomitokuV1Plugin.process_from_memory()` を直接呼び出し、L2Artifactへ登録しません。
- Parser実験は指定したOCRテキストを入力にしてOllamaへ直接問い合わせ、L3テーブルへ保存しません。
- 各実行の入力・設定・出力・エラー・処理時間を `experiments/results/` にJSONで保存します。
- 本番の `app/` の処理を変更せず、実験結果を確認してから本番コードへ反映します。

## 前提

- DataCoreリポジトリのルートで実行すること
- DataCore本体のPython依存関係がインストールされた環境であること
- OCR実験では `yomitoku`、`opencv-python` 等、既存YomiTokuプラグインの依存関係が必要
- Parser実験では `httpx`、`pydantic`、Ollamaへの接続が必要
- DB/CASからファイルを読む場合は、DataCoreのDB・ストレージ設定が利用可能であること

## 1. OCR実験

CASのファイルハッシュを指定する例:

```bash
python -m experiments.ocr.runner \
  --file-hash <SHA256> \
  --output-dir experiments/results
```

ローカル画像を直接指定する例:

```bash
python -m experiments.ocr.runner \
  --image ./sample_receipt.jpg \
  --output-dir experiments/results
```

`--file-hash` の場合は `l1_files` からMIMEタイプを取得し、`LocalStorageAdapter` でCAS原本を読み込みます。
`--image` の場合は画像ファイルからMIMEタイプを推定します。

現時点では既存プラグインの標準処理を再実行するベースライン実験です。YomiTokuの内部パラメータや画像前処理を変更する機能は、プラグイン側のAPIを確認しながら別途追加してください。未知の設定値を無理に渡す設計にはしていません。

## 2. Parser実験

既存L2 OCR成果物を指定:

```bash
python -m experiments.parser.runner \
  --artifact-id <OCR_ARTIFACT_UUID> \
  --stage both \
  --model gemma4:e2b \
  --prompt-dir experiments/parser/prompts \
  --output-dir experiments/results
```

OCRテキストファイルを直接指定:

```bash
python -m experiments.parser.runner \
  --ocr-text-file ./ocr_output.txt \
  --stage both \
  --model gemma4:e2b
```

プロンプトは以下のファイルを読み込みます。

- `experiments/parser/prompts/header_system.txt`
- `experiments/parser/prompts/items_system.txt`

プロンプトファイルを編集して同じ入力・同じモデルで再実行すれば、出力JSONにプロンプト本文とSHA-256が記録されます。実験時は同じ結果ディレクトリを上書きせず、毎回新しい実験IDで保存します。

`--stage header` / `--stage items` で片方だけを実行できます。`both` はヘッダー抽出の後、品目抽出を実行します。

Parserは既存の `ReceiptHeaderData` / `ReceiptItemsData` で検証しますが、DB登録・本番の冪等性チェック・L3Tool登録は行いません。

## 3. OCR成果物の取得

`--artifact-id` は既存の `l2_artifacts.id` を指定します。`artifact_type='ocr_text'` の `content_text` を読み込みます。
`--ocr-text-file` を指定した場合はDB接続不要です。

## 結果

各実行は次のようなフォルダに保存されます。

```text
experiments/results/
└── 20261102T012345Z_a1b2c3d4/
    ├── manifest.json
    ├── input.txt                 # Parser実験時
    ├── ocr_output.json           # OCR実験時
    ├── parser_output.json        # Parser実験時
    └── error.json                # エラー時
```

## 注意点

- 実験結果は本番L2/L3成果物ではありません。
- レシート画像・OCRテキスト・抽出結果には個人情報が含まれる可能性があります。`results/` は原則Git管理対象外にしてください。
- 実験結果を本番DBへ自動反映する機能はありません。
- モデル名・プロンプト・スキーマ・依存ライブラリのバージョンが変わると完全再現できない場合があります。manifestを残して比較してください。
