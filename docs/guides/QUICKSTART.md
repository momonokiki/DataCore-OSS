# クイックスタート

DataCore を最短で起動する手順です。

## 前提

- Docker 20.10 以上（Docker Compose v2 同梱）
- ネットワーク環境：初回は torch などの大きなライブラリと、OCR・Embedding モデルのダウンロードが発生します

## 初回セットアップ

```bash
git clone <このリポジトリ>
cd datacore
./init.sh setup
```

`setup` は次の順に実行します。

1. **env** — `.env` の作成（ポート競合チェック・JWT秘密鍵の自動生成・L3アドオンの選択）
2. **build** — Docker イメージのビルド（初回は時間がかかります）
3. **db** — DB起動待ち → マイグレーション → テーブル初期化
4. **up** — サービス起動
5. **user** — 初期ユーザー登録（対話入力）

各段階は独立して再実行できます（例: ビルドに失敗したら `./init.sh build` だけやり直す）。`alembic upgrade head` は適用済みマイグレーションを記録するため、同じ環境での再実行は基本的にスキップされます。

完了後のアクセス先:

| サービス | URL |
|---|---|
| Web UI (Reflex) | http://localhost:3000 |
| API (FastAPI) | http://localhost:8000/docs |
| Flower (タスク監視) | http://localhost:5555 |
| Metabase（分析・オプション） | `./init.sh up --analytics` で起動 → http://localhost:3001 |

ポートは `.env` で変更できます（変更後は `./init.sh up` を再実行）。

## 2回目以降の起動

```bash
./init.sh up
```

イメージは作成済みのため、起動自体はビルドを伴いません。DBのマイグレーションだけ更新したい場合は:

```bash
./init.sh db
```

## 更新の反映

コードを変更した場合（詳しくは [開発手順](../DEVELOPMENT.md)）:

```bash
./init.sh update    # 再ビルド → 停止 → DB更新 → 再起動
```

## 全停止・リセット

```bash
./init.sh down      # 停止（データは保持）
./init.sh reset     # 停止＋名前付きボリューム削除（DB・モデルキャッシュ。確認あり）
```

`reset` で削除されるのは Docker の名前付きボリューム（`postgres_data` / `hf_cache` など）です。ホスト側 `./data` に保存されたL1原本ファイルは削除されないため、完全にやり直したい場合は別途手動で削除してください。

## ビルド時間の仕組み（なぜ2回目から速いのか）

速さは3層のキャッシュで構成されています。

| 層 | 対象 | 効き目 |
|---|---|---|
| Docker レイヤーキャッシュ | `pip install -r requirements.txt` | `requirements.txt` が変わらない限り pip install 自体がスキップされる |
| BuildKit pip キャッシュマウント | wheel のダウンロード | `requirements.txt` を更新しても、torch など巨大ライブラリの再ダウンロードを通常は回避できる |
| hf_cache ボリューム | Hugging Face 系モデル | コンテナを作り直しても、`from_pretrained` で取得するモデルの再ダウンロードを通常は回避できる |

注意点:

- キャッシュは Docker 側の操作（`docker builder prune` など）で失われることがあります。その場合は再ダウンロードが発生します。
- `hf_cache` は `transformers` の `from_pretrained` 系（CLIP・Embedding モデル）を対象にしています。YomiToku のモデルは Hugging Face Hub からダウンロードされますが、この構成で永続化されるかは未検証のため、初回起動時にダウンロードが発生する前提で運用してください。
- キャッシュが効かないときは以下を確認してください。
  - `.dockerignore` が存在しない / `requirements.txt` がビルドコンテキストに含まれない
  - Docker の古いビルダーを使っている（`DOCKER_BUILDKIT=1` を明示指定で解決）
  - `docker compose build --no-cache` を使っていないか

## ポートの公開範囲

既定では、外部に公開されるのは **Web UI（3000番）だけ**です。それ以外は `.env` の `*_BIND` 変数で切り替えます:

| サービス | 既定 | LAN内の別端末から使う場合 |
|---|---|---|
| Web UI | 公開（変更不可） | そのまま |
| API (fastapi) | `API_BIND=127.0.0.1` | `API_BIND=0.0.0.0` |
| Flower | `FLOWER_BIND=127.0.0.1` | `FLOWER_BIND=0.0.0.0`（Basic認証が付くので `FLOWER_AUTH_*` を必ず変更） |
| Metabase | `METABASE_BIND=127.0.0.1` | `METABASE_BIND=0.0.0.0`（Metabase自身のログイン認証あり） |
| PostgreSQL | `DB_BIND=127.0.0.1` | `DB_BIND=0.0.0.0`（非推奨。必要な場合のみ） |
| Redis | 非公開 | `docker compose exec redis redis-cli` |

変更後は `./init.sh up` で反映されます。

### WSL2 (Windows) でスマホからアクセスする場合

WSL2 の既定（NATモード）では、`0.0.0.0` でバインドしても**Windowsの外（LAN）からは直接届きません**。次のいずれかが必要です:

1. **mirrored モード（推奨・Windows 11 22H2+ / WSL 2.0.0+）**: `%UserProfile%\.wslconfig` に以下を記述して `wsl --shutdown` 後にWSLを再起動。WSL内のポートがWindowsのLAN IPでそのまま届くようになります。
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
   Windowsファイアウォールで該当ポートの受信許可が必要な場合があります。
2. **NATモードのまま**: Windows側でポート転送を設定（WSLのIPは再起動で変わるためスクリプト化推奨）:
   ```powershell
   netsh interface portproxy add v4tov4 listenport=5555 listenaddress=0.0.0.0 connectport=5555 connectaddress=<WSLのIP>
   ```
3. **SSHトンネル（設定変更なし・最も安全）**: スマホのTermuxから既にSSHしているなら、
   ```bash
   ssh -L 5555:localhost:5555 -L 3001:localhost:3001 user@<PCのアドレス>
   ```
   でスマホのブラウザから `localhost:5555` / `localhost:3001` として見られます。`*_BIND` を `0.0.0.0` にする必要はありません。

## よくある質問

**Q. ビルドにやたら時間がかかる**
A. 初回は torch・transformers などのダウンロードが支配的です。2回目以降は上記キャッシュで短縮されます。それでも遅い場合は `docker system df` でキャッシュが消えていないか確認してください。

**Q. モデルのダウンロードを毎回やりたくない**
A. `hf_cache` ボリュームで永続化されています。`./init.sh reset` を実行すると消える点に注意してください。

**Q. ポートが競合する**
A. `.env` 作成時（`./init.sh setup` のenv段階）に競合を検出して別ポートを提案します。あとから変える場合は `.env` を編集して `./init.sh up` を再実行してください。
