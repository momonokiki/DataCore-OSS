# app/webui/webui/pages/upload.py

import reflex as rx
from typing import Dict, Any
from ..state import WebUIState
from ..styles import COLOR_THEME, CARD_STYLE
from ..layout import common_layout

def selected_file_preview(filename: rx.Var[str]) -> rx.Component:
    """アップロード前に『今何が選ばれているか』を視覚的に確認するためのプレビュー行"""
    return rx.hstack(
        rx.text("📄", size="3"),
        rx.text(filename, font_weight="medium", size="2", color=COLOR_THEME["text_main"]),
        padding="2",
        background_color="#EDF2F7",
        border_radius="md",
        width="100%",
        align_items="center"
    )

def result_status_item(file_info: rx.Var[Dict[str, Any]]) -> rx.Component:
    """FastAPIから帰ってきたL1 CAS層への重複排除登録結果のインジェストステータス"""
    return rx.hstack(
        rx.box(
            width="4px", 
            height="34px", 
            background_color=COLOR_THEME["accent"],
            border_radius="sm"
        ),
        rx.vstack(
            rx.text(file_info["filename"], font_weight="bold", size="2", color=COLOR_THEME["text_main"]),
            rx.text(file_info["file_hash"].to(str), size="1", color="gray"),
            align_items="start",
            spacing="0"
        ),
        rx.spacer(),
        rx.badge(
            file_info["status"], 
            variant="surface",
            color_scheme="teal"
        ),
        width="100%",
        border_bottom=f"1px solid {COLOR_THEME['border']}",
        padding_y="2",
        align_items="center"
    )

def upload_content() -> rx.Component:
    """データ投入画面のコアUIメインブロック"""
    return rx.vstack(
        rx.box(
            rx.vstack(
                rx.heading("ファイルをインジェスト層へ投入", size="4", color=COLOR_THEME["text_main"]),
                rx.text("原本ファイルをL1 CAS層へ重複排除保存し、ハッシュ駆動型のCelery連続バトンリレーパイプラインをキックします。", size="2", color="gray"),
                
                rx.divider(border_color=COLOR_THEME["border"]),
                
                # 自動処理スイッチ
                rx.hstack(
                    rx.text("取り込み後、Celery構造化パイプラインを自動起動する", size="2", font_weight="medium"),
                    rx.switch(
                        is_checked=WebUIState.trigger_pipeline,
                        on_change=WebUIState.toggle_pipeline,
                    ),
                    justify="between",
                    width="100%",
                    padding_y="1"
                ),

                rx.hstack(
                    rx.vstack(
                        rx.text("金融機関のCSV明細として処理する", size="2", font_weight="medium"),
                        rx.text("※JCBカード、またはゆうちょ銀行の確定的なCSV解析を実行します", size="1", color="teal"),
                        align_items="start",
                        spacing="0"
                    ),
                    rx.switch(
                        is_checked=WebUIState.is_finance,
                        on_change=WebUIState.toggle_finance,
                        color_scheme="teal"
                    ),
                    justify="between",
                    width="100%",
                    padding_y="2",
                    background_color=rx.cond(WebUIState.is_finance, "#E6FFFA", "transparent"), # ONの時に背景を薄い緑にして視認性を向上
                    padding_x="2",
                    border_radius="md",
                    transition="background-color 0.2s"
                ),

                
                # ドラッグ＆ドロップ対応ファイル配置エリア
# app/webui/webui/pages/upload.py の修正箇所

                # ドラッグ＆ドロップ対応ファイル配置エリア
                rx.upload(
                    rx.vstack(
                        rx.button(
                            "ファイルを選択、またはここにドラッグ＆ドロップ", 
                            color=COLOR_THEME["text_main"], 
                            background_color="#FFFFFF", 
                            border=f"1px solid {COLOR_THEME['border']}",
                            cursor="pointer"
                        ),
                        rx.text("対応フォーマット: レシート画像(JPEG/PNG)、PDF文書など", size="1", color="gray"),
                        align_items="center",
                        spacing="2"
                    ),
                    id="upload_files",
                    border=f"2px dashed {COLOR_THEME['accent']}",
                    padding="6",
                    background_color=COLOR_THEME["bg_sub"],
                    border_radius="lg",
                    width="100%"
                ),
                
                # 💡 修正：rx.upload.get_files_text ではなく rx.selected_files を使用します
                rx.vstack(
                    rx.text("📌 選択中のファイル（確定前確認）:", font_weight="bold", size="2", color=COLOR_THEME["text_main"]),
                    rx.foreach(
                        rx.selected_files("upload_files"),  # 👈 修正：get_files_text を廃止して適合化
                        selected_file_preview
                    ),
                    align_items="start",
                    spacing="2",
                    width="100%",
                    padding_x="1"
                ),

                rx.button(
                    "安全なパイプラインへ投入実行",
                    on_click=WebUIState.handle_file_upload(rx.upload_files(upload_id="upload_files")),
                    loading=WebUIState.is_loading,
                    background_color=COLOR_THEME["accent"],
                    color="#FFFFFF",
                    width="100%",
                    size="3",
                    cursor="pointer"
                ),
                spacing="4",
                width="100%"
            ),
            **CARD_STYLE
        ),
        
        # 処理結果およびステータスの動的表示セクション
        rx.cond(
            WebUIState.ingest_message | (WebUIState.upload_results.length() > 0),
            rx.box(
                rx.vstack(
                    rx.heading("パイプライン処理ステータス", size="3", color=COLOR_THEME["text_main"]),
                    rx.cond(
                        WebUIState.ingest_message,
                        rx.box(
                            rx.text(WebUIState.ingest_message, size="2", font_weight="bold"),
                            padding="3",
                            background_color=COLOR_THEME["bg_sub"],
                            border_left=f"4px solid {COLOR_THEME['accent']}",
                            width="100%",
                            border_radius="sm"
                        )
                    ),
                    rx.cond(
                        WebUIState.upload_results.length() > 0,
                        rx.vstack(
                            rx.text("L1層 CAS物理登録詳細:", size="2", font_weight="bold", color="gray"),
                            rx.foreach(WebUIState.upload_results, result_status_item),
                            width="100%",
                            spacing="2"
                        )
                    ),
                    spacing="3",
                    width="100%"
                ),
                **CARD_STYLE
            )
        ),
        spacing="6",
        width="100%"
    )

def upload_page() -> rx.Component:
    """共通の堅牢なサイドバー付き共通レイアウトの中にデータ投入層をコンポーズ"""
    return common_layout(upload_content(), "📥 データ投入 (Upload)")

