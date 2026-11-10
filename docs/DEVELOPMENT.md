# 開発手順

DataCore の開発・変更作業の手順です。**「何を変えたら、どのコマンドが必要か」** を対応表で示します。

## 開発環境の基本構造

```bash
./init.sh setup   # 初回のみ
./init.sh up      # 毎回の起動
./init.sh logs fastapi   # ログを見ながら開発
```

- ソースコードは各コンテナに `.` をバインドマウントしているため、**コード変更のたびにイメージを再ビルドする必要はありません**（`requirements.txt` を変えたときだけビルドが必要）。
- ただし Python プロセスは自動リロードしないため、**変更後は該当サービスの再起動**が必要です。

## 変更種別 × 必要なコマンド対応表

| 何を変えたか | 必要な操作 | コマンド |
|---|---|---|
| Python ソース（API 側: `app/api/`, `app/main.py` など） | fastapi の再起動のみ | `./init.sh restart fastapi` |
| Python ソース（バックグラウンド処理: `app/layers/`, `app/tasks.py`） | celery-worker の再起動のみ | `./init.sh restart celery-worker` |
| WebUI（`app/webui/` 配下） | webui の再起動のみ | `./init.sh restart webui` |
| 環境変数（`.env`） | コンテナの再作成 | `./init.sh up` |
| 依存パッケージ（`requirements.txt`） | 再ビルド＋再作成 | `./init.sh update` |
| DB モデル（`app/infrastructure/db/models/` 配下） | マイグレーション作成→適用 | 下記「DB スキーマ変更」 |
| L3 アドオンの追加・有効化 | `.env` 編集→初期化→コンテナ再作成 | 下記「L3 アドオン変更」 |
| `Dockerfile` / `docker-compose.yml` | 再ビルド＋再作成 | `./init.sh update` |

## 典型的な開発サイクル

```bash
# 別ターミナルでログを監視
./init.sh logs fastapi
./init.sh logs celery-worker

# コードを編集...
vim app/api/routes/ingest.py

# 変更を反映（イメージ再ビルド不要）
./init.sh restart fastapi

# 動作確認
curl http://localhost:8000/docs
```

## DB スキーマ変更

Alembic でマイグレーションを管理します。既存テーブルに影響する変更は必ずマイグレーションを作成してください。

```bash
# 1. モデル (app/infrastructure/db/models/...) を編集

# 2. マイグレーションファイルを生成
docker compose run --rm -T fastapi alembic revision --autogenerate -m "add_xxx_column"

# 3. 内容を確認してから適用（稼働中のアプリ・ワーカーを一旦停止してからDB更新する）
./init.sh update    # 再ビルド不要なら: docker compose down → ./init.sh db → ./init.sh up
```

`./init.sh update` は「再ビルド → 停止 → DB更新 → 再起動」の順で実行するため、スキーマ変更の適用に推奨です。アプリ・ワーカーが稼働したまま `./init.sh db` だけを実行すると、移行途中のスキーマへ接続する時間が発生する点に注意してください。

`./init.sh db` は `alembic upgrade head` + `app.infrastructure.db.initializer` を単発コンテナで実行します（`docker compose run` の詳細は [Docker公式リファレンス](https://docs.docker.com/reference/cli/docker/compose/run/)）。

- `alembic upgrade head` は適用済みマイグレーションをスキップするため、同じ環境での再実行は安全です。
- `initializer` は `CREATE TABLE IF NOT EXISTS` とシード投入（存在しない場合のみINSERT）を行うため、**同一スキーマでの再実行**は基本的に安全です。
- ただし以下の点に注意してください。
  - L3 アドオンのテーブル（`addon_` 接頭辞）は、コード側にあってDBにないカラムを `ALTER TABLE ... ADD COLUMN` で自動追加しますが、**NOT NULL のカラムをデータが入ったテーブルに追加すると失敗**します。その場合はデフォルト値の用意など手動対応が必要です。
  - アドオンの `models.py` 読み込みに失敗しても警告表示して処理を続行するため、ログを確認してください。
  - カラム削除・型変更は対象外のため、Alembic を使うか手動で対応してください。
  - **既存データが入った環境でのスキーマ変更**は、マイグレーションファイルの内容を必ず確認してから適用してください（バックアップ推奨: `docker compose exec db pg_dump ...`）。

## L3 アドオン変更

```bash
# 1. .env の ENABLED_L3_ADDONS を編集（カンマ区切りで追加）
#    例: ENABLED_L3_ADDONS=receipt,finunce_parser

# 2. アドオンのテーブル作成・シード反映
./init.sh db

# 3. コンテナを再作成して新しい環境変数を反映
#    ※ restart では env_file の変更が反映されないため、up -d での再作成が必要
./init.sh up
```

`restart` はプロセスを再起動するだけで、`env_file` の値を読み直しません。`.env` を変更したら必ず `up`（再作成）を使ってください。

## 依存パッケージの追加

```bash
# requirements.txt に追記
echo "somepackage==1.2.3" >> requirements.txt

# 再ビルド（pip キャッシュマウントにより既存ライブラリの再ダウンロードは発生しない）
./init.sh update
```

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| サービスが起動しない | `./init.sh status` → `./init.sh logs <サービス名>` |
| DB に接続できない | `./init.sh db` で起動待ち・マイグレーションを再実行 |
| タスクが滞留している | Flower ( http://localhost:5555 ) でワーカー状態を確認 |
| ビルドが異常に遅い | QUICKSTART の「ビルド時間の仕組み」を参照 |
