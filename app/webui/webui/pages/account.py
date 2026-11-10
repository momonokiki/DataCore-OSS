# === app/webui/webui/pages/account.py ===
import reflex as rx
from ..styles import COLOR_THEME, CARD_STYLE
from ..layout import common_layout

def account_content() -> rx.Component:
    """アカウント管理画面の固有の中身（ダミー表示）"""
    return rx.box(
        rx.vstack(
            rx.text("現在ログインしているユーザーのアカウントプロファイル情報です。", size="2", color="gray"),
            
            rx.divider(border_color=COLOR_THEME["border"]),
            
            rx.hstack(
                rx.text("ユーザー名:", font_weight="bold", size="3", width="120px"),
                rx.text("altfn (仮)", size="3"),
                width="100%"
            ),
            rx.hstack(
                rx.text("ロール権限:", font_weight="bold", size="3", width="120px"),
                rx.badge("Admin", color_scheme="teal", variant="surface"),
                width="100%"
            ),
            rx.hstack(
                rx.text("システムID:", font_weight="bold", size="3", width="120px"),
                rx.code("1a47ea7a-5518-4758-922a-b289ea71037e", size="1"),
                width="100%"
            ),
            
            rx.divider(border_color=COLOR_THEME["border"]),
            rx.button("パスワード変更（通信コード未接続）", variant="outline", size="2", width="200px"),
            
            spacing="4",
            align_items="start"
        ),
        **CARD_STYLE
    )

def account_page() -> rx.Component:
    """共通レイアウトを外枠に被せて返却"""
    return common_layout(account_content(), "👤 アカウント管理")

