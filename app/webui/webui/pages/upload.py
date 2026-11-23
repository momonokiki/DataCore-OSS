
# app/webui/webui/pages/upload.py

import os
from typing import Any, Dict

import reflex as rx

from ..state import WebUIState
from ..styles import COLOR_THEME, CARD_STYLE
from ..layout import common_layout


# Docker Compose の .env に設定された FastAPI 公開ポート
API_PUBLIC_PORT = os.getenv("WEB_PORT", "8000")


def result_status_item(file_info: rx.Var[Dict[str, Any]]) -> rx.Component:
    """FastAPIから返されたL1 CAS層への登録結果"""
    return rx.hstack(
        rx.box(
            width="4px",
            height="34px",
            background_color=COLOR_THEME["accent"],
            border_radius="sm",
        ),
        rx.vstack(
            rx.text(
                file_info["filename"],
                font_weight="bold",
                size="2",
                color=COLOR_THEME["text_main"],
            ),
            rx.text(
                file_info["file_hash"].to(str),
                size="1",
                color="gray",
            ),
            align_items="start",
            spacing="0",
        ),
        rx.spacer(),
        rx.badge(
            file_info["status"],
            variant="surface",
            color_scheme="teal",
        ),
        width="100%",
        border_bottom=f"1px solid {COLOR_THEME['border']}",
        padding_y="2",
        align_items="center",
    )


def upload_content() -> rx.Component:
    """ブラウザからFastAPIへ直接ファイルを送信する画面"""

    upload_script = r"""
    (async () => {
        const fileInput = document.getElementById("direct-upload-files");
        const financeInput = document.getElementById("direct-upload-finance");
        const pipelineInput = document.getElementById("direct-upload-pipeline");
        const apiPortInput = document.getElementById("direct-upload-api-port");

        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            return JSON.stringify({
                ok: false,
                status: "未選択",
                body: "ファイルを選択してください。"
            });
        }

        // Reflexの認証CookieからJWTを取得
        const cookie = document.cookie
            .split("; ")
            .find(item => item.startsWith("auth_token="));

        if (!cookie) {
            return JSON.stringify({
                ok: false,
                status: 401,
                body: "認証トークンが見つかりません。再ログインしてください。"
            });
        }

        const token = decodeURIComponent(
            cookie.substring("auth_token=".length)
        );

        // API公開ポートの確認
        if (!apiPortInput || !apiPortInput.value) {
            return JSON.stringify({
                ok: false,
                status: "設定エラー",
                body: "API公開ポートが設定されていません。"
            });
        }

        const apiPort = apiPortInput.value.trim();

        if (!/^\d+$/.test(apiPort)) {
            return JSON.stringify({
                ok: false,
                status: "設定エラー",
                body: "API公開ポートの設定が不正です。"
            });
        }

        const isFinance = financeInput.value === "true";
        const triggerPipeline = pipelineInput.value !== "false";

        // multipart/form-dataを構築
        const formData = new FormData();

        for (const file of fileInput.files) {
            formData.append("files", file, file.name);
        }

        // WEB_PORT は Docker Compose の環境変数から取得
        const apiBase =
            window.location.protocol +
            "//" +
            window.location.hostname +
            ":" +
            apiPort;

        const endpoint = isFinance
            ? "/api/v1/finance"
            : "/api/v1/ingest";

        const url = new URL(apiBase + endpoint);

        if (!isFinance) {
            url.searchParams.set(
                "trigger_pipeline",
                String(triggerPipeline)
            );
        }

        try {
            const response = await fetch(url.toString(), {
                method: "POST",
                headers: {
                    "Authorization": "Bearer " + token
                },
                body: formData
            });

            const body = await response.text();

            return JSON.stringify({
                ok: response.ok,
                status: response.status,
                body: body
            });

        } catch (error) {
            return JSON.stringify({
                ok: false,
                status: "通信エラー",
                body: String(error)
            });
        }
    })()
    """

    return rx.vstack(
        rx.box(
            rx.vstack(
                rx.heading(
                    "ファイルをインジェスト層へ投入",
                    size="4",
                    color=COLOR_THEME["text_main"],
                ),
                rx.text(
                    "原本ファイルをL1 CAS層へ保存し、必要に応じてCeleryパイプラインを起動します。",
                    size="2",
                    color="gray",
                ),

                rx.divider(
                    border_color=COLOR_THEME["border"],
                ),

                # Celeryパイプライン起動設定
                rx.hstack(
                    rx.text(
                        "取り込み後、Celery構造化パイプラインを自動起動する",
                        size="2",
                        font_weight="medium",
                    ),
                    rx.switch(
                        is_checked=WebUIState.trigger_pipeline,
                        on_change=WebUIState.toggle_pipeline,
                    ),
                    justify="between",
                    width="100%",
                    padding_y="1",
                ),

                # 金融CSV処理設定
                rx.hstack(
                    rx.vstack(
                        rx.text(
                            "金融機関のCSV明細として処理する",
                            size="2",
                            font_weight="medium",
                        ),
                        rx.text(
                            "※JCBカード、またはゆうちょ銀行のCSV解析を実行します",
                            size="1",
                            color="teal",
                        ),
                        align_items="start",
                        spacing="0",
                    ),
                    rx.switch(
                        is_checked=WebUIState.is_finance,
                        on_change=WebUIState.toggle_finance,
                        color_scheme="teal",
                    ),
                    justify="between",
                    width="100%",
                    padding_y="2",
                    background_color=rx.cond(
                        WebUIState.is_finance,
                        "#E6FFFA",
                        "transparent",
                    ),
                    padding_x="2",
                    border_radius="md",
                ),

                # ブラウザ側JavaScriptから参照する設定値
                rx.el.input(
                    type="hidden",
                    id="direct-upload-finance",
                    value=WebUIState.is_finance.to(str),
                ),
                rx.el.input(
                    type="hidden",
                    id="direct-upload-pipeline",
                    value=WebUIState.trigger_pipeline.to(str),
                ),
                rx.el.input(
                    type="hidden",
                    id="direct-upload-api-port",
                    value=API_PUBLIC_PORT,
                ),

                # 標準HTMLファイル入力
                rx.el.input(
                    type="file",
                    id="direct-upload-files",
                    multiple=True,
                    accept="image/*,.pdf,.csv",
                    style={
                        "width": "100%",
                        "padding": "18px",
                        "border": f"2px dashed {COLOR_THEME['accent']}",
                        "borderRadius": "10px",
                        "background": COLOR_THEME["bg_sub"],
                    },
                ),

                # ブラウザからAPIへ直接送信
                rx.button(
                    "選択したファイルをアップロード",
                    on_click=rx.call_script(
                        upload_script,
                        callback=WebUIState.handle_browser_upload_result,
                    ),
                    loading=WebUIState.is_loading,
                    background_color=COLOR_THEME["accent"],
                    color="#FFFFFF",
                    width="100%",
                    size="3",
                    cursor="pointer",
                ),

                spacing="4",
                width="100%",
            ),
            **CARD_STYLE,
        ),

        # 処理結果
        rx.cond(
            WebUIState.ingest_message
            | (WebUIState.upload_results.length() > 0),
            rx.box(
                rx.vstack(
                    rx.heading(
                        "パイプライン処理ステータス",
                        size="3",
                        color=COLOR_THEME["text_main"],
                    ),

                    rx.cond(
                        WebUIState.ingest_message,
                        rx.box(
                            rx.text(
                                WebUIState.ingest_message,
                                size="2",
                                font_weight="bold",
                            ),
                            padding="3",
                            background_color=COLOR_THEME["bg_sub"],
                            border_left=f"4px solid {COLOR_THEME['accent']}",
                            width="100%",
                            border_radius="sm",
                        ),
                    ),

                    rx.cond(
                        WebUIState.upload_results.length() > 0,
                        rx.vstack(
                            rx.text(
                                "L1層 CAS物理登録詳細:",
                                size="2",
                                font_weight="bold",
                                color="gray",
                            ),
                            rx.foreach(
                                WebUIState.upload_results,
                                result_status_item,
                            ),
                            width="100%",
                            spacing="2",
                        ),
                    ),

                    spacing="3",
                    width="100%",
                ),
                **CARD_STYLE,
            ),
        ),

        spacing="6",
        width="100%",
    )


def upload_page() -> rx.Component:
    """共通レイアウト内のデータ投入画面"""
    return common_layout(
        upload_content(),
        "📥 データ投入 (Upload)",
    )

