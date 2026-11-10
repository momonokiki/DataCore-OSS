# app/webui/webui/pages/login.py

import reflex as rx
from ..state import WebUIState
from ..styles import COLOR_THEME, CARD_STYLE

def login_page() -> rx.Component:
    """ログイン画面のUI"""
    return rx.center(
        rx.vstack(
            rx.vstack(
                rx.heading("DataCore WebUI", size="7", color=COLOR_THEME["text_main"]),
                rx.text("パイプライン管理システム", color=COLOR_THEME["accent"], font_weight="bold"),
                align="center",
                spacing="1"
            ),
            rx.box(
                rx.vstack(
                    rx.text("サインイン", size="5", font_weight="bold", color=COLOR_THEME["text_main"]),
                    
                    # 💡 ユーザー名入力：valueを明示的にバインドして同期を強制します
                    rx.input(
                        placeholder="ユーザー名",
                        on_change=WebUIState.change_username,
                        value=WebUIState.input_username,  # 👈 追加
                        size="3",
                        width="100%",
                    ),
                    
                    # 💡 パスワード入力：valueを明示的にバインドして同期を強制します
                    rx.input(
                        placeholder="パスワード",
                        type="password",
                        on_change=WebUIState.change_password,
                        value=WebUIState.input_password,  # 👈 追加
                        size="3",
                        width="100%",
                    ),
                    
                    rx.cond(
                        WebUIState.auth_error,
                        rx.text(WebUIState.auth_error, color="red", size="2")
                    ),
                    rx.button(
                        "ログイン",
                        on_click=WebUIState.handle_login,
                        width="100%",
                        size="3",
                        background_color=COLOR_THEME["accent"],
                        color="white",
                        cursor="pointer"
                    ),
                    spacing="4",
                    width="320px",
                ),
                **CARD_STYLE
            ),
            rx.hstack(
                rx.box(width="12px", height="12px", background_color=COLOR_THEME["accent"], border_radius="full"),
                rx.box(width="12px", height="12px", background_color=COLOR_THEME["border"], border_radius="full"),
                spacing="2"
            ),
            spacing="6",
            align="center"
        ),
        height="100vh",
        background_color=COLOR_THEME["bg_sub"],
        width="100%"
    )

