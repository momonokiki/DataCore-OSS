DataCore Data Model

1. 目的と適用範囲

本ドキュメントでは、DataCore のデータ層、テーブル間の関係、識別子、データの来歴（provenance）を説明する。

DataCore は、元ファイルを保持し、ファイルから抽出したデータを蓄積し、用途別の構造化データを生成する個人データ基盤である。

データは概念上、次の3層に分かれる。

- L1 Raw：元ファイル、CAS、アップロード情報
- L2 Extracted：メタデータ、OCR テキスト、Embedding などの抽出結果
- L3 Structured：レシート、金融取引などのドメイン固有データ

このドキュメントでは、実際の SQLAlchemy モデルに定義されている構造と、今後の設計上の方針を区別する。カラム、外部キー、制約についてはコードを正とする。

2. 基本原則

2.1 元ファイルを基準にする

L1 の物理ファイルは、ファイル内容から計算した SHA-256 ハッシュ値 "file_hash" で識別する。

同一内容のファイルは同一のハッシュ値になるため、CAS（Content Addressable Storage）では内容を基準に保存・参照できる。

アップロード時のファイル名やユーザーとの関係は、物理ファイルとは別のレコードで管理する。

2.2 抽出データと構造化データを分離する

L2 は、元ファイルから得られた抽出結果を保持する。

L3 は、L2 の成果物などを入力として、特定の用途に必要な情報を構造化する。

例：

- レシート画像 → OCR テキスト → レシート情報・商品明細
- 金融機関 CSV → CSV パーサ → 明細書・取引明細

金融 CSV の現行実装には、L1 のファイル内容から直接パースし、L2 を経由しない経路がある。したがって、すべての L3 データが必ず L2 成果物を持つわけではない。

2.3 来歴を追跡する

構造化データを検証・再処理できるよう、元ファイル、抽出成果物、使用したツール設定を可能な範囲で関連付ける。

- 元ファイルの識別子："file_hash"
- L2 成果物の識別子："l2_artifacts.id"
- L2 ツールの識別子："l2_artifacts.tool_id"
- L3 ツールの識別子："l3_tools.id"
- L3 レコードの識別子：各アドオンの UUID

ただし、これらすべての関係がすべてのアドオンで同じように外部キー制約によって保証されるわけではない。実際の制約は個別モデルを参照する。

3. 識別子

対象| 識別子| 役割
L1 物理ファイル| SHA-256、64文字の16進表現| ファイル内容の識別
アップロード記録| UUID| アップロード単位の識別
L2 成果物| UUID| 抽出結果の識別
L2 ツール| UUID| 抽出・生成ツールの識別
L3 レシート| UUID| レシートレコードの識別
L3 レシート明細| UUID| 商品明細レコードの識別
L3 ツール| UUID| 構造化処理設定の識別
金融明細書| UUID| CSV 由来の明細書レコードの識別
金融取引| UUID| 取引レコードの識別

"file_hash" は同一内容のファイルを識別し、UUID は個々のレコードを識別する。両者は役割が異なる。

4. L1 Raw

4.1 "l1_files"

物理ファイルの管理テーブル。モデルは "app/layers/l1_raw/models.py" に定義されている。

カラム| 型・意味
"file_hash"| "String(64)"、主キー。SHA-256
"mime_type"| "String(100)"、MIME タイプ
"file_size_bytes"| "BigInteger"、ファイルサイズ
"storage_path"| "String(512)"、CAS 内の相対パス。NULL 可
"created_at"| 作成日時
"updated_at"| 更新日時

ファイル本体はストレージに保存し、データベースには識別子や保存先などの情報を保持する。

現在のローカルストレージ実装では、ハッシュ値の先頭2文字をサブディレクトリとして使用する。

4.2 "l1_file_uploads"

アップロード履歴、所有ユーザー、アップロード時のファイル名を保持する。

カラム| 型・意味
"id"| UUID、主キー
"user_id"| "users.id" への外部キー
"file_hash"| "l1_files.file_hash" への外部キー
"original_filename"| "String(255)"、元ファイル名
"created_at"| 作成日時
"updated_at"| 更新日時

"user_id" と "file_hash" はインデックス付き。ユーザー削除時、および参照先の L1 ファイル削除時の動作は、モデルに設定された外部キー制約に従う。

同一の物理ファイルに複数のアップロード記録を関連付けられるため、物理ファイルの重複排除とアップロード単位の情報管理を分離できる。

4.3 "resource_shares"

アップロード記録に対する共有先と権限を保持する。

主な項目：

- "id"
- "file_upload_id"
- "grantee_type"
- "grantee_id"
- "permission_level"

"file_upload_id" は "l1_file_uploads.id" を参照する。共有先は "grantee_type" と "grantee_id" で表現され、"file_upload_id"・"grantee_type"・"grantee_id" の組み合わせに一意制約がある。

共有先の識別子は、このモデル上では汎用 UUID として保持されている。"grantee_id" に対してユーザーやグループへの個別外部キーが定義されているわけではない。

4.4 CAS と削除

CAS のファイル識別には "file_hash" を使用する。

ただし、データベースの削除とストレージ上のファイル削除は別の処理である。SQLAlchemy のリレーションに cascade が指定されていても、ストレージ内の実ファイルが自動的に削除されるとは限らない。

削除機能を変更する場合は、DB レコード、CAS 実ファイル、アップロード記録、共有情報、L2/L3 の参照をそれぞれ確認する。

5. L2 Extracted

L2 の主要モデルは "app/layers/l2_extracted/models.py" に定義されている。

5.1 "l2_media_info"

元ファイルに対する共通メタデータを保持する。

"file_hash" が主キーであり、"l1_files.file_hash" への外部キーでもある。モデルでは1つの L1 ファイルにつき1件のメディア情報を管理する設計になっている。

カラム| 意味
"file_hash"| 対象 L1 ファイルの SHA-256
"content_created_at"| コンテンツの作成日時・撮影日時
"author_or_device"| 作成者名、撮影機器、カメラモデルなど
"width" / "height"| 画像・動画などの寸法
"latitude" / "longitude"| 位置情報
"duration_seconds"| 音声・動画の再生時間
"sample_rate_hz"| サンプリング周波数
"frame_rate"| フレームレート
"page_count"| 文書などのページ数
"line_count"| テキスト・CSV などの行数
"encoding"| 文字コード
"raw_metadata"| 未加工メタデータの JSONB
"created_at" / "updated_at"| 共通タイムスタンプ

メタデータ項目は NULL を許容し、ファイル形式に応じて取得可能な情報を保存する。

"raw_metadata" は、EXIF や文書メタデータなど、抽出ツールが取得した未加工情報を保持するための項目である。

5.2 "l2_artifacts"

元ファイルから抽出・生成した成果物を1対多で保持する。

カラム| 型・意味
"id"| UUID、主キー
"file_hash"| "l1_files.file_hash" への外部キー
"tool_id"| "l2_tools.id" への外部キー
"artifact_type"| 成果物の種類
"content_text"| OCR テキストやテキストチャンク
"page_number"| ページ番号
"bounding_box"| 座標情報などの JSONB
"embedding_dim"| Embedding の次元数
"embedding"| pgvector のベクトル
"embedding_half"| halfvec 用のベクトル
"embedding_bit"| バイナリ量子化用のビット列
"created_at" / "updated_at"| 共通タイムスタンプ

"artifact_type" の例として "ocr_text"、"layout_bbox"、"chunk"、"embedding" がモデルコメントに記載されている。

Embedding は、標準の "Vector" に加えて、比較・実験用の "HalfVector" と "BIT VARYING" の格納先が用意されている。

L2 成果物には、どのツールを使ったかを示す "tool_id" があり、"l2_tools.id" を参照する。L3 ツールとは別のマスタである。

5.3 L2 の役割と限界

L2 は、元ファイルを後続処理で利用できる形に変換する層である。

例：

- OCR による文字認識
- 文書のレイアウト解析
- テキストの抽出・分割
- Embedding の生成
- ファイル属性・メタデータの抽出

L2 は特定ドメインのデータモデルに依存しない抽出結果を保持することを目指す。ただし、具体的な抽出方式や成果物の種類は各プラグイン・タスクの実装に従う。

6. L3 の共通ツール設定

6.1 "l3_tools"

L3 の構造化処理に使用するツールやパーサの設定を保持する。モデルは "app/infrastructure/db/models/l3_tools.py" に定義されている。

カラム| 型・意味
"id"| UUID、主キー
"name"| "String(100)"、一意な識別名
"model_name"| "String(100)"、モデル名または処理エンジン名
"prompt_version"| "String(50)"、プロンプトまたはパーサルールのバージョン
"config"| JSONB、任意の設定
"is_active"| 有効フラグ
"created_at" / "updated_at"| 共通タイムスタンプ

"config" には、プロバイダー、対象アカウント、プロンプト関連設定などを保持できる。

このテーブルは L3 のツール設定を管理するものであり、L2 の "l2_tools" とは異なる。

6.2 ツール設定と来歴

アドオンは "l3_tools" を参照し、どのパーサ設定で構造化データを生成したかを記録する。

レシートでは、"parser_tool_id" が "l3_tools.id" を参照する。金融 CSV でも同様に "parser_tool_id" を使う。

設定名やバージョンの変更規則は各アドオンのセットアップ処理に依存する。現在のレシートおよび金融 CSV のセットアップ処理では、登録済み設定のバージョンとの不一致を検出する仕組みがある。

7. レシートアドオン

実装場所："app/layers/l3_structured/addons/receipt/"

テーブル：

- "addon_l3_receipt_totals"
- "addon_l3_receipt_items"

7.1 "addon_l3_receipt_totals"

レシート1件分の店舗、取引日時、金額、レビュー情報などを保持する。

カラム| 型・意味
"id"| UUID、主キー
"file_hash"| "l1_files.file_hash" への外部キー
"source_artifact_id"| "l2_artifacts.id" への外部キー
"parser_tool_id"| "l3_tools.id" への外部キー
"store_name"| 店舗名
"transaction_date"| 取引日
"transaction_at"| タイムゾーン付き取引日時
"currency"| "String(3)"、デフォルト "JPY"、NULL 可
"subtotal_amount"| 小計
"discount_amount"| 割引額
"tax_amount"| 税額
"total_amount"| 合計金額
"payment_method"| 支払方法
"needs_review"| 要確認フラグ
"review_reasons"| JSONB の配列
"raw_payload"| JSONB の構造化入力データ
"created_at" / "updated_at"| 共通タイムスタンプ

金額は "Numeric(14, 2)" で保持する。数量などを扱う明細側では別の精度を使う。

"source_artifact_id" と "parser_tool_id" の組み合わせには一意制約がある。これは、同じ L2 成果物と同じパーサ設定の組み合わせによるレシートの重複を防ぐための制約である。

7.2 "addon_l3_receipt_items"

レシートに含まれる商品明細を保持する。

カラム| 型・意味
"id"| UUID、主キー
"receipt_id"| "addon_l3_receipt_totals.id" への外部キー
"line_number"| 明細行番号
"item_name"| 商品名
"quantity"| 数量、"Numeric(12, 3)"
"unit_price"| 単価、"Numeric(14, 2)"
"line_amount"| 明細金額、"Numeric(14, 2)"
"tax_rate"| 税率、"Numeric(5, 2)"
"raw_text"| 元の明細テキスト
"created_at" / "updated_at"| 共通タイムスタンプ

"receipt_id" と "line_number" の組み合わせに一意制約があり、"line_number" は1以上でなければならない。

親レシートの削除に伴い明細も削除するよう、外部キーと SQLAlchemy リレーションに削除連鎖が定義されている。

7.3 レシート処理の来歴

レシートデータは、元ファイル、OCR 成果物、パーサ設定を関連付けて管理する。

レシート処理では、入力となる L2 成果物について、対象ファイルとの対応や OCR テキストなどを検証する処理がある。

"raw_payload" と "review_reasons" は、抽出結果や確認が必要な理由を保持するために利用される。自動抽出結果を無条件に正しいものとして扱わず、レビュー可能な形で蓄積する。

8. 金融 CSV アドオン

実装場所："app/layers/l3_structured/addons/finunce_parser/"

このアドオンは、金融機関ごとの CSV パーサを登録し、明細書と取引明細を構造化する。

現在の実装では、CSV のパーサを選択し、アカウント単位の "l3_tools" 設定と関連付ける。LLM や OCR を必要としない決定的パーサとして動作する。

8.1 "addon_l3_kakeibo_statements"

金融明細書の親テーブル。

カラム| 型・意味
"id"| UUID、主キー
"file_hash"| L1 ファイルを識別するハッシュ値
"parser_tool_id"| "l3_tools.id" への外部キー
"account_id"| 金融機関アカウント識別子
"account_number"| 口座・カード番号など
"total_records"| 明細レコード数
"total_amount"| 合計金額、"Numeric(14, 2)"
"raw_header"| CSV ヘッダーの JSON
"created_at" / "updated_at"| 共通タイムスタンプ

重要： 現在のモデルでは、"file_hash" に "l1_files.file_hash" への外部キー制約は定義されていない。インデックスは定義されているが、レシートテーブルの "file_hash" と同じ参照整合性は保証されない。

8.2 "addon_l3_kakeibo_transactions"

金融取引明細の子テーブル。

カラム| 型・意味
"id"| UUID、主キー
"statement_id"| "addon_l3_kakeibo_statements.id" への外部キー
"row_index"| CSV 内の行番号
"transaction_date"| 取引日
"amount"| 金額、"Numeric(14, 2)"
"description"| 取引内容
"category_raw"| 元のカテゴリ文字列
"raw_row"| CSV の1行分の JSON
"created_at" / "updated_at"| 共通タイムスタンプ

"statement_id" と "row_index" の組み合わせには一意制約がある。

親テーブルと取引明細は1対多の関係で、親の削除に伴って子を削除する外部キーが定義されている。

8.3 パーサ登録

金融 CSV のセットアップ処理は、登録済みパーサを走査し、アカウントごとの "l3_tools" を登録する。

- ツール名："kakeibo_csv_{account_id}"
- "model_name"："deterministic_csv_parser"
- "prompt_version"：各パーサの "parser_id"
- "config"：プロバイダー "kakeisys" と対象アカウント

登録済みツールの "prompt_version" とコード側の "parser_id" が一致しない場合、セットアップ処理はエラーを発生させる。

8.4 金融データに関する注意

金融 CSV のデータモデルは、レシートモデルとは異なる。

- 金融明細書は "source_artifact_id" を持たず、L2 を経由しない入力経路を持つ。
- "file_hash" は現在のモデルでは外部キーではない。
- 取引の一意性は、現状 "statement_id" と "row_index" の組み合わせで定義される。
- 同じ CSV を別の明細書として再取り込みした場合の重複排除は、この制約だけでは保証されない。

これらを変更する場合は、既存データ、取り込み処理、再実行時の動作を合わせて確認する。

9. データ関係の概念図

users
  |
  +--< l1_file_uploads >-- l1_files
                               |
                               +-- l2_media_info
                               |
                               +--< l2_artifacts >-- l2_tools
                                      |
                                      +--< addon_l3_receipt_totals >-- l3_tools
                                                   |
                                                   +--< addon_l3_receipt_items

l1_files (file_hash の値を保持)
  |
  +-- addon_l3_kakeibo_statements -- l3_tools
               |
               +--< addon_l3_kakeibo_transactions

図中の金融 CSV と "l1_files" の関係は、"file_hash" の値を用いた論理的な関連を示している。現在のモデルには、その間の外部キー制約はない。

また、この図は主要なデータ関係を示すもので、全テーブル・全制約を網羅した ER 図ではない。

10. タイムスタンプとドメイン日時

"TimestampMixin" は、"created_at" と "updated_at" を定義する。

- "created_at"：レコードの作成日時
- "updated_at"：レコードの更新日時

レシートの "transaction_date" や金融取引の "transaction_date" は、ドメイン上の取引日であり、レコードの作成日時とは異なる。

日時を扱う場合は、レコードの管理日時、元データに記録された日時、ドメイン上の日時を区別する。

11. テーブル作成とスキーマ変更

テーブルの作成・初期化には、共通の DB 初期化処理とアドオンごとのセットアップ処理が関係する。

アドオンのセットアップ処理では、テーブル作成時に "checkfirst=True" が使われている箇所がある。これは既存テーブルの存在確認を行うためのもので、既存テーブルのカラムや制約をモデル定義に合わせて自動更新するものではない。

DB 初期化処理には、アドオンテーブルへのカラム追加を行う処理も存在する。ただし、これを完全なスキーママイグレーション機構とみなさず、変更内容に応じて既存データと制約を検証する。

スキーマ変更時の基本手順：

1. SQLAlchemy モデルを変更する。
2. DB 初期化処理とアドオンのセットアップ処理を確認する。
3. 外部キー、一意制約、削除制約を確認する。
4. 既存 DB に対して変更を適用できるか検証する。
5. 必要なテストを追加する。
6. 本ドキュメントを更新する。

12. 実装上の正本

本ドキュメントは全体像を説明するものであり、コード上の定義を置き換えるものではない。

対象| 実装ファイル
L1 ファイル・アップロード| "app/layers/l1_raw/models.py"
L2 メタデータ・成果物| "app/layers/l2_extracted/models.py"
L2 ツール設定| "app/infrastructure/db/models/l2_tools.py"
L3 ツール設定| "app/infrastructure/db/models/l3_tools.py"
レシートテーブル| "app/layers/l3_structured/addons/receipt/models.py"
レシートセットアップ| "app/layers/l3_structured/addons/receipt/setup_db.py"
金融 CSV テーブル| "app/layers/l3_structured/addons/finunce_parser/models.py"
金融 CSV セットアップ| "app/layers/l3_structured/addons/finunce_parser/scripts/setup.py"
共通モデル・タイムスタンプ| "app/infrastructure/db/base.py"
DB 初期化| "app/infrastructure/db/initializer.py"
モデル登録| "app/db_all_models.py"

実装変更後は、コード、DB スキーマ、セットアップ処理、テスト、本ドキュメントの整合性を維持する。