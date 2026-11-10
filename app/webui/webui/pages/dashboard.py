import reflex as rx
from typing import Dict, Any
from ..state import WebUIState
from ..styles import COLOR_THEME, CARD_STYLE

def result_item(file_info: rx.Var[Dict[str, Any]]) -> rx.Component:
    """取り込み詳細結果の各行のレンダリング (型エラーを完全に防ぐセーフ設計)"""
    
    # 💡 複雑な Var.cond やスライスを排除し、完全にシンプルなテキストとして結合
    return rx.hstack(
        rx.box(
            width="6px", 
            height="40px", 
            background_color=COLOR_THEME["accent"],
            border_radius="md"
        ),
        rx.vstack(
            rx.text(file_info["filename"], font_weight="bold", size="3", color=COLOR_THEME["text_main"]),
            # 💡 エラーの原因だった文字スライス [:20] を排除し、型安全にそのまま文字列キャストして表示
            rx.text(file_info["file_hash"].to(str), size="1", color="gray"),
            align="start",
            spacing="0"
        ),
        rx.spacer(),
        rx.badge(
            file_info["status"], 
            variant="surface"
        ),
        width="100%",
        border_bottom=f"1px solid {COLOR_THEME['border']}",
        padding_y="2",
        align="center"
    )

def dashboard_page() -> rx.Component:
    """メインインジェスト画面のUI"""
    return rx.box(
        # 上部ナビゲーションバー
        rx.hstack(
            rx.hstack(
                rx.heading("DataCore", size="6", color=COLOR_THEME["text_main"]),
                rx.badge("Pipeline Ingest", variant="solid")
            ),
            rx.spacer(),
            rx.hstack(
                rx.text(f"User: {WebUIState.username}", color=COLOR_THEME["text_main"], size="3"),
                rx.button(
                    "ログアウト", 
                    on_click=WebUIState.handle_logout,
                    size="2",
                    variant="outline",
                    cursor="pointer"
                ),
                spacing="3",
                align="center"
            ),
            padding_x="6",
            padding_y="4",
            background_color="#FFFFFF",
            border_bottom=f"2px solid {COLOR_THEME['accent']}",
            align="center",
            width="100%"
        ),
        
        # メインコンテンツ
        rx.center(
            rx.vstack(
                rx.box(
                    rx.vstack(
                        rx.heading("ファイルをインジェスト層へ投入", size="5", color=COLOR_THEME["text_main"]),
                        rx.text("L1 CAS物理層へ重複排除保存し、ハッシュ駆動型Celery順次パイプラインをキックします。", size="2", color="gray"),
                        
                        rx.divider(border_color=COLOR_THEME["border"]),
                        
                        # パイプライン自動起動のスイッチ
                        rx.hstack(
                            rx.text("Celeryパイプラインを自動起動する", size="3", font_weight="medium"),
                            rx.switch(
                                is_checked=WebUIState.trigger_pipeline,
                                on_change=WebUIState.toggle_pipeline,
                            ),
                            justify="between",
                            width="100%",
                            padding_y="2"
                        ),
                        
                        # ファイルアップロードエリア
                        rx.upload(
                            rx.vstack(
                                rx.button(
                                    "ファイルを選択、またはここにドラッグ＆ドロップ", 
                                    color=COLOR_THEME["text_main"], 
                                    background_color="white",
                                    border=f"1px solid {COLOR_THEME['border']}"
                                ),
                                rx.text("レシート画像(JPEG/PNG)、PDF文書など", size="1", color="gray"),
                                align="center",
                                spacing="2"
                            ),
                            id="upload_files",
                            border=f"2px dashed {COLOR_THEME['accent']}",
                            padding="6",
                            border_radius="lg",
                            background_color=COLOR_THEME["bg_sub"],
                            width="100%"
                        ),
                        
                        rx.vstack(
                            rx.text("選択されたファイル:", font_weight="bold", size="2", color=COLOR_THEME["text_main"]),
                            # rx.upload.get_files_text("コンポーネントのid") で選択中のファイル名が自動でテキスト化されます
                            rx.text(rx.upload.get_files_text("upload_files"), size="2", color="gray"),
                            align="start",
                            spacing="1",
                            width="100%",
                            padding_x="2"
                        ),
                        # 送信ボタン
                        rx.button(
                            "パイプラインへ投入実行",
                            on_click=WebUIState.handle_file_upload(rx.upload_files(upload_id="upload_files")),
                            loading=WebUIState.is_loading,
                            background_color=COLOR_THEME["accent"],
                            color="white",
                            width="100%",
                            size="3",
                            cursor="pointer"
                        ),
                        
                        spacing="4",
                        width="500px"
                    ),
                    **CARD_STYLE
                ),
                
                # 結果表示エリア
                rx.cond(
                    WebUIState.ingest_message | (WebUIState.upload_results.length() > 0),
                    rx.box(
                        rx.vstack(
                            rx.heading("処理ステータス", size="4", color=COLOR_THEME["text_main"]),
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
                                    rx.text("ファイル毎の登録詳細:", size="2", font_weight="bold", color="gray"),
                                    rx.foreach(WebUIState.upload_results, result_item),
                                    width="100%",
                                    spacing="2"
                                )
                            ),
                            spacing="3",
                            width="500px"
                        ),
                        **CARD_STYLE
                    )
                ),
                spacing="6",
                padding_y="8"
            )
        ),
        background_color=COLOR_THEME["bg_sub"],
        min_height="100vh",
        width="100%"
    )

