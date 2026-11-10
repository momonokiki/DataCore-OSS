# 変更内容と適用手順

## ファイル一覧

| ファイル | 変更 | 内容 |
|---|---|---|
| `Dockerfile` | 変更 | BuildKit pipキャッシュマウント追加、HF_HOME設定 |
| `app/webui/Dockerfile` | 変更 | pipキャッシュマウント追加 |
| `.dockerignore` | 新規 | ビルドコンテキストから秘匿情報・生成物を除外 |
| `docker-compose.yml` | 変更 | hf_cacheボリューム、env_file、ポート変数修正、Metabaseをプロファイル化、公開ポートの限定（webuiのみ公開、他は127.0.0.1限定/redis非公開） |
| `env.example` | 変更 | `REDIS_PIRT`→`REDIS_PORT` 修正、ENABLED_L3_ADDONS追加 |
| `init.sh` | 変更 | サブコマンド化（env/build/up/db/user/update等）、冪等化、各種バグ修正 |
| `app/infrastructure/db/initializer.py` | 変更 | 全モデルを `Base.metadata` に登録するインポートを追加（空DB初期化の確認用） |
| `README.md` | 変更 | はじめ方セクション追加、ドキュメントリンク整理 |
| `docs/guides/QUICKSTART.md` | 新規 | クイックスタート |
| `docs/DEVELOPMENT.md` | 新規 | 開発手順（変更種別×コマンド対応表） |
| `docs/OSS_CHECKLIST.md` | 新規 | OSS公開前チェックリスト |

## 適用手順

1. リポジトリのルートで、上記のファイルを同じパスに上書き・追加します。
2. `chmod +x init.sh` を実行します。
3. 既存の `.env` がある場合はそのまま使えます（`REDIS_PIRT` を `REDIS_PORT` に手動で書き換えてください）。
4. `docker compose down` → `./init.sh up` で新しい構成で起動します。
   - 既存のDB・ユーザーデータは `postgres_data` ボリュームに保持されたままです。
   - JWT秘密鍵も `.env` を使い回す限り変わりません（既存トークンは失効しません）。

## 修正した既存バグ

- `init.sh` 冒頭の `et -e` → `set -euo pipefail`（タイプミス）
- 再実行のたびに JWT 秘密鍵が再生成され全トークンが失効する問題 → 初回のみ生成
- 再実行のたびにポート競合チェックが自分のコンテナのポートを検出して止まる問題 → ポート確認・アドオン選択は `.env` 新規作成時のみ（`./init.sh env --reconfigure` で再設定可能）
- `env.example` の `REDIS_PIRT` と docker-compose の `REDIS_PORT` の不一致
- ポート変数の対応ズレ（`API_PORT`/`WEB_PORT`/`METABASE_PORT` の役割が混乱していた）
- macOS 標準環境（bash 3.2 / BSD sed / `ss` 未搭載）で動かない問題 → `declare -A` 廃止、`perl -pi` 使用、`ss`/`lsof`/`nc` フォールバック
- `docker compose exec fastapi` 依存（APIコンテナが起動していないとDB初期化できない）→ 単発コンテナ `run --rm -T --no-deps` に変更
- 固定 `sleep 5` → `pg_isready` ポーリング（上限60秒）に変更
- Metabase 用データベース `metabase_db` が作成されない問題 → `./init.sh up --analytics` 時に自動作成
- アプリ起動後にDB初期化する順序だったため、起動直後のスキーマ不一致が起き得た問題 → `setup`/`update` ともDB構築を先に行う順序に変更

## ビルド高速化の仕組み

3層のキャッシュで構成（詳細は QUICKSTART.md）:

1. **Dockerレイヤーキャッシュ**: requirements.txt が変わらない限り pip install がスキップ（元々のレイヤー順序は既に正しかったため、ソース変更だけなら高速化の余地は元から小さい）
2. **BuildKit pipキャッシュマウント**: requirements.txt 更新時も torch などの再ダウンロードを通常は回避（[BuildKitキャッシュマウント](https://docs.docker.com/build/cache/optimize/#use-cache-mounts)）
3. **hf_cacheボリューム**: `transformers` の `from_pretrained` 系モデル（CLIP・Embedding）のダウンロードを1回だけに（[HFキャッシュの仕組み](https://huggingface.co/docs/huggingface_hub/guides/manage-cache)）

## 注意事項・未検証項目

- この変更は実際の Docker ビルド・起動検証を行っていません（検証環境に Docker が無かったため）。適用後は `./init.sh setup` の初回起動と、再実行（既存 `.env` が変更されないこと）を確認してください。
- Metabase は `./init.sh up --analytics` を実行したときのみ起動するように変わりました（デフォルトでは起動しません）。
- YomiToku のモデルは Hugging Face Hub からダウンロードされますが、`hf_cache` ボリュームで永続化されるかは未検証です（transformers 系は HF_HOME 配下に保存されるため永続化対象）。
- macOS の bash 3.2 に対しては、`declare -A` 廃止・`perl -pi` 使用などの互換性対策をしていますが、実際の macOS 環境での動作確認はしていません。
- `initializer` の自動カラム追加は、データが入ったテーブルへの NOT NULL カラム追加では失敗します（詳細は DEVELOPMENT.md）。
