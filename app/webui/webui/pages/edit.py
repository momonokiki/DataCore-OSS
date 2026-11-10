import reflex as rx
from ..styles import COLOR_THEME, CARD_STYLE
from ..layout import common_layout

def edit_content() -> rx.Component:
    """修正画面の固有の中身（フォームのサンプル）"""
    return rx.box(
        rx.vstack(
            rx.text("パースされた構造化データの確認および人間による手修正を行います。", size="2", color="gray"),
            
            rx.vstack(
                rx.text("店舗名 (Store Name)", size="2", font_weight="bold"),
                rx.input(placeholder="例: セブンイレブン 渋谷店", width="100%"),
                align_items="start",
                width="100%"
            ),
            rx.vstack(
                rx.text("合計金額 (Total Amount)", size="2", font_weight="bold"),
                rx.input(placeholder="例: 1500", type="number", width="100%"),
                align_items="start",
                width="100%"
            ),
            
            rx.button("修正内容を保存（通信コード未接続）", background_color=COLOR_THEME["accent"], color="white", width="100%", size="3"),
            spacing="4"
        ),
        **CARD_STYLE
    )

def edit_page() -> rx.Component:
    """共通レイアウトを外枠に被せて返却"""
    return common_layout(edit_content(), "📝 データ修正 (Edit)")

