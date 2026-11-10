# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Reflexのフロントエンドビルドに必要なNode.jsおよびツールをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    git \
    build-essential \
    && curl -fsSL https://nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt-get/lists/*

# 1. まず依存ライブラリをインストール（キャッシュを効かせるため）
# ★ BuildKit キャッシュマウントで pip ダウンロードを永続化（ROOT Dockerfile と同じ方針）
COPY app/webui/requirements.txt ./app/webui/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r app/webui/requirements.txt

# 2. ソースコード一式をコピー
# （すでにローカルで reflex init 済みの rxconfig.py や webui/ ディレクトリが含まれている前提）
COPY . .

# AI機能・テレメトリの強制無効化
ENV TELEMETRY_ENABLED=false
ENV REFLEX_AI_ENABLED=false

WORKDIR /app/app/webui

# ポートの開放
EXPOSE 3000

# 起動コマンド（docker-compose側で上書きされますが明示）
CMD ["reflex", "run", "--backend-host", "0.0.0.0", "--backend-port", "3000"]
