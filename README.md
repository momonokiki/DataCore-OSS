$ cat README.md
DataCore

ようこそ、DataCoreへ。

これは僕が、GPUも積んでいないノートパソコンを開けないからTailscaleでスマホから繋いでCUIでLLMの無料版を駆使しながら作っています。

コーディングはお任せだし、基盤作成以降はほとんどコードを 追ったりはせずに動作検証で進んでいます。

クラウドにデータが吸われるのは嫌だけど便利に過ごしたい僕 が作っているものなので、気に入ったらアドオンとか作ってみ てください。

ここから下はAIが書いてくれたやつなのでほどほどに見ながら 、わからないことは質問くれればお答えします。

DataCoreは、個人が保有するファイルを原本から管理し、OCR・メディア情報抽出・Embedding・ドメイン固有の構造化処理を通じて、検索・分析・個人向けAIに利用できるデータへ変換する ための基盤です。
                                                         特定のアプリケーションにデータを閉じ込めず、原本と生成デ ータを分離して蓄積し、用途に応じた処理を追加できることを 目指します。

はじめ方

git clone https://github.com/momonokiki/DataCore-OSS.git cd DataCore-OSS
./init.sh setup
                                                         これで環境変数のセットアップ・イメージビルド・起動・DB初 期化・初期ユーザー登録まで行われます。詳細はクイックスタ ートを参照してください。                                 
起動後のアクセス先:

サービス| URL
Web UI| http://localhost:3000
API (FastAPI)| http://localhost:8000/docs
Flower (タスク監視)| http://localhost:5555               
日常の操作は "./init.sh help" で一覧できます（up / down / logs / db / update など）。
                                                         設計の基本方針

- 原本を保持する：L1に原本を保存し、抽出結果や構造化デー タと区別する。
- コンテンツを識別する：SHA-256の"file_hash"を原本の識別 に利用し、CASによる重複排除を行う。
- 責務を分離する：L1（原本）、L2（抽出・生成結果）、L3（ ドメイン構造化データ）を分ける。
- 非同期処理を行う：FastAPIをAPIの入口とし、Celeryでバッ クグラウンド処理を実行する。
- 用途別に拡張する：L2プラグインやL3アドオンによって、デ ータ種別や処理方式を追加する。
- 処理結果を追跡する：原本、抽出結果、構造化データの関係 を可能な限り保持する。

技術構成

領域| 技術・コンポーネント
Web UI| Reflex
API| FastAPI
非同期処理| Celery
メッセージブローカー| Redis
データベース| PostgreSQL 16 + pgvector
原本ストレージ| CASを利用したファイルストレージ
抽出処理| YomiTokuなどのOCR、メディア情報抽出
ベクトル・構造化処理| Embeddingモデル、必要に応じたLLMや 決定的パーサー
タスク監視| Flower
データ分析| Metabase（オプション: "./init.sh up --analytics"）
実行環境| Docker Compose

具体的なサービス名、ポート、環境変数、モデル名、タスク名 はコードと設定を正本とします。

データレイヤー

- L1 — Raw: 原本ファイルと、その識別・保存に必要な情報。
- L2 — Extracted: OCRテキスト、メディア情報、Embeddingな どの抽出・生成結果。
- L3 — Structured: レシートや金融取引など、ドメイン固有の構造化データ。
                                                         L2・L3はL1を置き換えるものではありません。処理方法を変更 した場合にも、原本を再利用できる構成を目指します。
                                                         現在の通常ファイル処理

"app/api/routes/ingest.py" はファイルを受け付け、L1への取り込み後、"trigger_pipeline" が有効であれば、ファイルごとに次のCeleryチェーンを起動します。

1. "tasks.extract_media_info"
2. "tasks.embed_image_file"
3. "tasks.ocr_file"
4. "tasks.embedding_file"
5. "tasks.parse_file"

実装上は固定順序のチェーンです。各タスクの戻り値は後続タ スクへ渡されます。タスクが例外で失敗した場合、通常は後続 タスクも実行されないため、失敗時の扱いを確認する必要があ ります。

最後の "tasks.parse_file" は、"ENABLED_L3_ADDONS" の設定 を確認し、"receipt" が有効な場合にレシートの構造化処理を 呼び出します。                                           
金融機関CSVなどの専用入力                                
形式が定まった金融機関CSVには、画像OCRや画像Embeddingを必須としない専用経路が適しています。

入力API、L1保存、専用Celeryタスク、L3アドオンを接続し、入力種別に応じた処理を選択できるようにします。専用CSV経路の具体的なAPIやタスクの実装状況は、現行コードを確認して判断します。

ドキュメント
                                                         - システム概要
- アーキテクチャ
- クイックスタート                                       - 開発手順
- OSS公開前チェックリスト
- 入力契約 ("docs/development/INPUT_CONTRACT.md")
- Celeryパイプライン ("docs/development/PIPELINE.md")
- L2プラグイン ("docs/development/L2_PLUGINS.md")
- L3アドオン ("docs/development/L3_ADDONS.md")

未作成のリンク先は、今後順次整備します。

開発方針

新しい入力経路、L2プラグイン、L3アドオンを追加する場合は 、共通契約、既存のタスク構成、DB管理方式を確認します。

API・DB・Celeryタスクの具体的な仕様はコードと設定を正本とし、設計方針や拡張ルールはドキュメントに記載します。コー ド変更時には関連するテストとドキュメントも更新します。
