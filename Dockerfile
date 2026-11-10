# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Hugging Face 系モデル（from_pretrained）の保存先を固定パスにし、
    # docker-compose 側でボリュームとして永続化できるようにする
    HF_HOME=/app/.cache/huggingface

# パッケージビルドに必要な依存ライブラリのインストール
# ★ libxcb、libx11、libgl1 など、OpenCVのバイナリが暗黙に要求するライブラリを網羅
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libpq-dev \
    libglib2.0-0 \
    libgl1 \
    libxcb1 \
    libx11-xcb1 \
    libxrender1 \
    libxext6 \
    unzip \
    && rm -rf /var/lib/apt-get/lists/*

# requirements.txt のコピーとインストール
# ★ ポイント1: requirements.txt が変わらない限り、このレイヤーは再実行されない
#   （ソースコードの変更だけでビルドし直しても pip install はスキップされる）
# ★ ポイント2: BuildKit のキャッシュマウントで pip のダウンロードを永続化。
#   requirements.txt を更新した場合でも、torch など大きな wheel の
#   「再ダウンロード」を通常は回避できる（キャッシュ削除時は除く）。
#     - 使うには BuildKit 有効化が必要: DOCKER_BUILDKIT=1 （Docker 23+ は既定）
#     - キャッシュは docker buildx prune --filter type=regular などで管理
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# アプリケーションコードのコピー
# （.dockerignore により .env / data / __pycache__ / .git などは含まれない）
COPY . .
