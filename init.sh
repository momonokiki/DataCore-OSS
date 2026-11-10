
#!/usr/bin/env bash
# ==============================================================================
# DataCore 初期化・運用スクリプト
#
# 使い方:
#   ./init.sh <サブコマンド>
#
# サブコマンド:
#   setup        初回導入: env → build → db → up → user
#   env          .env の作成・検証
#                --reconfigure でポート・アドオンを再設定
#   build        Docker イメージのビルド
#   up           サービスの起動
#                --analytics で Metabase も起動
#   down         サービスの停止・コンテナ削除（データ保持）
#   stop         サービスの一時停止（コンテナ保持）
#   start        stop で停止したサービスの再開
#   restart      サービスの再起動
#   status       サービスの状態表示
#   logs         ログのフォロー表示
#   db           DB起動待ち → マイグレーション → 初期化
#   addon-setup  有効化された L3 アドオンのセットアップ
#   user         初期ユーザーの作成
#   update       コード更新の反映（build → down → db → up）
#   reset        名前付きボリュームを削除（確認あり）
#   help         ヘルプ表示
# ==============================================================================

set -euo pipefail

ENV_FILE=".env"

# ---------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------

compose() {
    docker compose "$@"
}

# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------

# .env の KEY を VALUE に更新する。存在しなければ追記する。
set_env() {
    local key="$1"
    local value="$2"
    local escaped_value

    escaped_value=$(printf '%s' "$value" | sed 's/[\\&|]/\\&/g')

    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        perl -pi -e "s|^${key}=.*|${key}=${escaped_value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

# .env から KEY の値を取得する。
get_env() {
    local key="$1"
    local default="${2:-}"
    local value

    value=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d '=' -f2-)

    if [ -n "$value" ]; then
        printf '%s' "$value"
    else
        printf '%s' "$default"
    fi
}

# ポートが使用中か確認する。
port_in_use() {
    local port="$1"

    if command -v ss >/dev/null 2>&1; then
        ss -tulpn 2>/dev/null | grep -qE ":${port}\b"
    elif command -v lsof >/dev/null 2>&1; then
        lsof -i :"$port" >/dev/null 2>&1
    elif command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    else
        return 1
    fi
}

# 対話的な端末か確認する。
is_interactive() {
    [ -t 0 ] && [ -t 1 ]
}

# ---------------------------------------------------------------------------
# DB 起動待ち
# ---------------------------------------------------------------------------

wait_for_db() {
    echo "-> データベースの起動を待っています..."

    local waited=0
    local db_user
    local db_name

    db_user=$(get_env POSTGRES_USER postgres)
    db_name=$(get_env POSTGRES_DB datacore_db)

    until compose exec -T db pg_isready \
        -U "$db_user" \
        -d "$db_name" >/dev/null 2>&1
    do
        waited=$((waited + 2))

        if [ "$waited" -ge 60 ]; then
            echo "エラー: データベースが60秒以内に起動しませんでした。" >&2
            echo "'./init.sh logs db' で確認してください。" >&2
            exit 1
        fi

        sleep 2
    done

    echo "-> データベース接続を確認しました。"
}

# ---------------------------------------------------------------------------
# 1. env: .env の作成・検証
# ---------------------------------------------------------------------------

cmd_env() {
    echo "=== [env] 環境変数ファイルの準備 ==="

    local reconfigure=0

    if [ "${1:-}" = "--reconfigure" ]; then
        reconfigure=1
    elif [ $# -gt 0 ]; then
        echo "エラー: 不明な env オプションです: $1" >&2
        exit 1
    fi

    # .env の初回作成
    local created=0

    if [ ! -f "$ENV_FILE" ]; then
        if [ -f env.example ]; then
            cp env.example "$ENV_FILE"
            echo "-> env.example から .env を作成しました。"
            created=1
        else
            echo "エラー: env.example が見つかりません。" >&2
            exit 1
        fi
    else
        echo "-> .env はすでに存在するため、既存の値を保持します。"
    fi

    # JWT_SECRET_KEY の生成
    local jwt

    jwt=$(get_env JWT_SECRET_KEY "")

    if [ -z "$jwt" ] || \
       [ "$jwt" = "change_this_to_a_secure_random_key_for_jwt" ]; then

        if ! command -v openssl >/dev/null 2>&1; then
            echo "エラー: openssl が必要です。" >&2
            exit 1
        fi

        local jwt_secret
        jwt_secret=$(openssl rand -hex 32)

        set_env JWT_SECRET_KEY "$jwt_secret"

        echo "-> JWT_SECRET_KEY を生成しました。"
    else
        echo "-> JWT_SECRET_KEY は設定済みです。"
    fi

    # 既存環境では再設定要求がない限りポートとアドオンを保持
    if [ "$created" -eq 0 ] && [ "$reconfigure" -eq 0 ]; then
        echo "-> ポート・L3 アドオンの設定は変更しません。"
        echo "   再設定: ./init.sh env --reconfigure"
        echo "=== [env] 完了 ==="
        return 0
    fi

    # ホスト側公開ポートの確認
    local port_defs=(
        "POSTGRES_PORT:5432"
        "FLOWER_PORT:5555"
        "WEBUI_PORT:3000"
        "WEB_PORT:8000"
        "METABASE_PORT:3001"
    )

    local def
    local env_key
    local default_port
    local current_port
    local new_port

    for def in "${port_defs[@]}"; do
        env_key="${def%%:*}"
        default_port="${def##*:}"

        current_port=$(get_env "$env_key" "$default_port")

        [ -n "$current_port" ] || current_port="$default_port"

        if ! [[ "$current_port" =~ ^[0-9]+$ ]] || \
           [ "$current_port" -lt 1 ] || \
           [ "$current_port" -gt 65535 ]; then
            echo "エラー: ${env_key} のポート番号が不正です: $current_port" >&2
            exit 1
        fi

        while port_in_use "$current_port"; do
            echo ""
            echo "【警告】ポート $current_port ($env_key) は使用されています。"

            if is_interactive; then
                read -r -p "変更後のポート番号を入力してください: " new_port

                if [[ "$new_port" =~ ^[0-9]+$ ]] && \
                   [ "$new_port" -ge 1 ] && \
                   [ "$new_port" -le 65535 ]; then
                    current_port="$new_port"
                else
                    echo "無効なポート番号です。"
                fi
            else
                echo "-> .env の $env_key を手動で変更してください。" >&2
                exit 1
            fi
        done

        set_env "$env_key" "$current_port"

        echo "-> ポート設定: $env_key = $current_port"
    done

    # L3 アドオンの有効化
    echo "----------------------------------------"
    echo "L3 アドオンの有効化設定"
    echo "----------------------------------------"

    local addons_dir="app/layers/l3_structured/addons"
    local addons_str=""
    local addon_path
    local addon_name
    local choice

    if [ -d "$addons_dir" ]; then
        for addon_path in "$addons_dir"/*/; do
            [ -d "$addon_path" ] || continue

            addon_name=$(basename "$addon_path")

            if ! [[ "$addon_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                continue
            fi

            if is_interactive; then
                read -r -p "L3 アドオン '$addon_name' を有効化しますか？ (y/N): " choice

                if [[ "$choice" =~ ^[Yy]$ ]]; then
                    addons_str="${addons_str:+$addons_str,}$addon_name"
                fi
            else
                echo "エラー: L3 アドオンの有効化には対話端末が必要です。" >&2
                exit 1
            fi
        done
    else
        echo "-> 注意: $addons_dir が見つかりません。"
    fi

    set_env ENABLED_L3_ADDONS "$addons_str"

    echo "-> 設定された L3 アドオン: [ ${addons_str:-なし} ]"
    echo "=== [env] 完了 ==="
}

# ---------------------------------------------------------------------------
# 2. build: Docker イメージのビルド
# ---------------------------------------------------------------------------

cmd_build() {
    echo "=== [build] Docker イメージをビルドします ==="

    compose build

    echo "=== [build] 完了 ==="
}

# ---------------------------------------------------------------------------
# 3. up: サービス起動
# ---------------------------------------------------------------------------

ensure_analytics_db() {
    compose up -d db

    wait_for_db

    local mb_db
    local mb_user

    mb_db=$(get_env METABASE_POSTGRES_DB metabase_db)
    mb_user=$(get_env POSTGRES_USER postgres)

    if ! [[ "$mb_db" =~ ^[A-Za-z0-9_]+$ ]]; then
        echo "エラー: METABASE_POSTGRES_DB の値が不正です。" >&2
        exit 1
    fi

    echo "-> Metabase 用データベース '$mb_db' を確認します..."

    if compose exec -T db psql \
        -U "$mb_user" \
        -d postgres \
        -tAc "SELECT 1 FROM pg_database WHERE datname='$mb_db'" \
        | grep -q 1
    then
        echo "-> '$mb_db' はすでに存在します。"
    else
        compose exec -T db psql \
            -U "$mb_user" \
            -d postgres \
            -c "CREATE DATABASE \"$mb_db\""

        echo "-> '$mb_db' を作成しました。"
    fi
}

cmd_up() {
    local args=(
        "up"
        "-d"
    )

    local arg
    local analytics=0

    for arg in "$@"; do
        case "$arg" in
            --analytics)
                analytics=1
                ;;
            *)
                echo "エラー: 不明な up オプションです: $arg" >&2
                exit 1
                ;;
        esac
    done

    if [ "$analytics" -eq 1 ]; then
        ensure_analytics_db
        args=("--profile" "analytics" "${args[@]}")
    fi

    echo "=== [up] サービスを起動します ==="

    compose "${args[@]}"

    echo "=== [up] 完了 ==="

    cmd_status
}

# ---------------------------------------------------------------------------
# 4. down / stop / start / restart / status / logs
# ---------------------------------------------------------------------------

cmd_down() {
    compose down
}

cmd_stop() {
    compose stop
}

cmd_start() {
    compose start
}

cmd_restart() {
    compose restart "$@"
}

cmd_status() {
    compose ps
}

cmd_logs() {
    if [ $# -gt 0 ]; then
        compose logs -f --tail=100 "$@"
    else
        compose logs -f --tail=100
    fi
}

# ---------------------------------------------------------------------------
# 5. addon-setup: 有効化された L3 アドオンの setup.py を実行
# ---------------------------------------------------------------------------

cmd_addon_setup() {
    echo "=== [addon-setup] L3 アドオンのツール登録 ==="

    local enabled_addons
    enabled_addons=$(get_env ENABLED_L3_ADDONS "")

    if [ -z "$enabled_addons" ]; then
        echo "-> 有効化された L3 アドオンがありません。"
        return 0
    fi

    # アドオンの設定には対話端末が必要
    if ! is_interactive; then
        echo "エラー: アドオンのセットアップには対話端末が必要です。" >&2
        echo "対話端末から './init.sh addon-setup' を実行してください。" >&2
        return 1
    fi

    local addons_dir="app/layers/l3_structured/addons"
    local addon_list=()
    local addon
    local addon_path
    local setup_module

    local IFS=','
    read -r -a addon_list <<< "$enabled_addons"
    unset IFS

    for addon in "${addon_list[@]}"; do
        addon=$(printf '%s' "$addon" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

        [ -n "$addon" ] || continue

        if ! [[ "$addon" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            echo "警告: 不正なアドオン名をスキップします: $addon" >&2
            continue
        fi

        addon_path="$addons_dir/$addon"

        if [ ! -d "$addon_path" ]; then
            echo "エラー: アドオンディレクトリが見つかりません: $addon_path" >&2
            return 1
        fi

        if [ ! -f "$addon_path/setup.py" ]; then
            echo "-> スキップ: $addon には setup.py がありません。"
            continue
        fi

        setup_module="app.layers.l3_structured.addons.$addon.setup"

        echo "----------------------------------------"
        echo "-> L3 アドオン setup を実行します: $addon"
        echo "   module: $setup_module"
        echo "----------------------------------------"

        # -T を付けないことでコンテナにTTYを割り当てる
        compose run --rm --no-deps fastapi \
            python -m "$setup_module"
    done

    echo "=== [addon-setup] 完了 ==="
}

# ---------------------------------------------------------------------------
# 6. db: DB 起動待ち → マイグレーション → 初期化
# ---------------------------------------------------------------------------

cmd_db() {
    echo "=== [db] データベースの構築・更新 ==="

    compose up -d db

    wait_for_db

    # Alembic マイグレーション
    echo "-> Alembic マイグレーションを実行します..."

    compose run --rm -T --no-deps fastapi \
        alembic upgrade head

    # DB 初期化
    echo "-> データベース初期化スクリプトを実行します..."

    compose run --rm -T --no-deps fastapi \
        python -m app.infrastructure.db.initializer

    # 有効化された L3 アドオンのセットアップ
    cmd_addon_setup

    echo "=== [db] 完了 ==="
}

# ---------------------------------------------------------------------------
# 7. user: 初期ユーザー作成
# ---------------------------------------------------------------------------

cmd_user() {
    echo "=== [user] 初期ユーザーの登録 ==="

    compose run --rm fastapi \
        python -m scripts.create_initial_user
}

# ---------------------------------------------------------------------------
# 8. update: コード・設定更新後の反映
# ---------------------------------------------------------------------------

cmd_update() {
    echo "=== [update] 変更を反映して再作成します ==="

    cmd_build
    compose down
    cmd_db
    compose up -d

    echo "=== [update] 完了 ==="

    cmd_status
}

# ---------------------------------------------------------------------------
# 9. reset: 名前付きボリューム削除
# ---------------------------------------------------------------------------

cmd_reset() {
    echo "【危険】この操作は名前付きボリュームを削除します。"
    echo "DB・モデルキャッシュなどのデータが削除されます。"
    echo "ホスト側 ./data の原本ファイルは削除されません。"

    local choice="n"

    if is_interactive; then
        read -r -p "本当に実行しますか？ (y/N): " choice
    fi

    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        compose down -v

        echo "-> 名前付きボリュームを削除しました。"
        echo "-> 次は ./init.sh setup からやり直してください。"
        echo "-> ホスト側 ./data が残っている場合、L1 原本は保持されます。"
    else
        echo "-> キャンセルしました。"
    fi
}

# ---------------------------------------------------------------------------
# 10. setup: 初回導入
# ---------------------------------------------------------------------------

cmd_setup() {
    echo "=== DataCore セットアップを開始します ==="

    cmd_env
    cmd_build
    cmd_db
    cmd_up

    echo ""
    echo "初期ユーザーの登録"

    local do_user=""

    if is_interactive; then
        read -r -p "今すぐ登録しますか？ (Y/n): " do_user

        if [[ "$do_user" =~ ^[Nn]$ ]]; then
            echo "-> スキップしました。"
            echo "-> 後で './init.sh user' で実行できます。"
        else
            cmd_user
        fi
    else
        echo "-> 非対話モードのためスキップしました。"
        echo "-> 後で './init.sh user' で実行してください。"
    fi

    echo ""
    echo "=== すべての初期化が完了しました！ DataCore 稼働中 ==="

    echo "Web UI   : http://localhost:$(get_env WEBUI_PORT 3000)"
    echo "API Docs : http://localhost:$(get_env WEB_PORT 8000)/docs"
    echo "Flower   : http://localhost:$(get_env FLOWER_PORT 5555)"
    echo "Metabase : ./init.sh up --analytics で起動"
    echo "           http://localhost:$(get_env METABASE_PORT 3001)"
}

# ---------------------------------------------------------------------------
# 11. help: ヘルプ表示
# ---------------------------------------------------------------------------

cmd_help() {
    cat <<'EOF'
DataCore 初期化・運用スクリプト

使い方:
  ./init.sh <サブコマンド> [オプション]

初回導入:
  setup                   初回セットアップ
  env                     .env の作成・検証
  env --reconfigure       ポート・L3 アドオンの再設定
  build                   Docker イメージのビルド

サービス運用:
  up                      サービス起動
  up --analytics          Metabase を含めて起動
  down                    サービス停止・コンテナ削除
  stop                    サービス一時停止
  start                   サービス再開
  restart [service]       サービス再起動
  status                  サービス状態表示
  logs [service]          ログ表示

DB・アドオン:
  db                      DB マイグレーション・初期化
  addon-setup             有効化された L3 アドオンの登録
  user                    初期ユーザー作成

更新・リセット:
  update                  コード更新の反映
  reset                   名前付きボリューム削除（確認あり）

その他:
  help                    このヘルプを表示
EOF
}

# ---------------------------------------------------------------------------
# 12. エントリポイント
# ---------------------------------------------------------------------------

main() {
    if [ $# -lt 1 ]; then
        cmd_help
        return 1
    fi

    local sub="$1"
    shift

    case "$sub" in
        env)
            cmd_env "$@"
            ;;
        build)
            [ $# -eq 0 ] || {
                echo "エラー: build に引数は指定できません。" >&2
                return 1
            }
            cmd_build
            ;;
        up)
            cmd_up "$@"
            ;;
        down)
            [ $# -eq 0 ] || return 1
            cmd_down
            ;;
        stop)
            [ $# -eq 0 ] || return 1
            cmd_stop
            ;;
        start)
            [ $# -eq 0 ] || return 1
            cmd_start
            ;;
        restart)
            cmd_restart "$@"
            ;;
        status)
            [ $# -eq 0 ] || return 1
            cmd_status
            ;;
        logs)
            cmd_logs "$@"
            ;;
        db)
            [ $# -eq 0 ] || return 1
            cmd_db
            ;;
        addon-setup)
            [ $# -eq 0 ] || return 1
            cmd_addon_setup
            ;;
        user)
            [ $# -eq 0 ] || return 1
            cmd_user
            ;;
        update)
            [ $# -eq 0 ] || return 1
            cmd_update
            ;;
        reset)
            [ $# -eq 0 ] || return 1
            cmd_reset
            ;;
        setup)
            [ $# -eq 0 ] || return 1
            cmd_setup
            ;;
        help|-h|--help)
            cmd_help
            ;;
        *)
            echo "不明なサブコマンド: $sub" >&2
            cmd_help
            return 1
            ;;
    esac
}

main "$@"

