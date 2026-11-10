# === app/webui/webui/layout.py ===
import os

import reflex as rx
from .styles import COLOR_THEME


def common_layout(content: rx.Component, page_title: str) -> rx.Component:
    """すべての画面で共通して使う外枠（左にメニュー、右にコンテンツ）"""
    return rx.hstack(
        # 左側：固定メニュー（サイドバー）
        rx.vstack(
            rx.heading(
                "DataCore",
                size="5",
                color=COLOR_THEME["text_main"],
                padding_bottom="4",
            ),

            # 1. データ管理セクション
            rx.text("データ管理", size="1", color="gray", font_weight="bold"),
            rx.link(
                "📥 データ投入 (Upload)",
                href="/upload",
                color=COLOR_THEME["text_main"],
                size="2",
            ),
            rx.link(
                "🧾 レシート確認 (Receipts)",
                href="/receipts",
                color=COLOR_THEME["accent"],
                size="2",
                font_weight="bold",
            ),
            rx.link(
                "📝 データ修正 (Edit)",
                href="/edit",
                color=COLOR_THEME["text_main"],
                size="2",
            ),
            rx.link(
                "🔍 証跡検索 (Search)",
                href="/search",
                color=COLOR_THEME["text_main"],
                size="2",
            ),

            rx.spacer(),

            # 2. アカウント設定セクション
            rx.text("設定", size="1", color="gray", font_weight="bold"),
            rx.link(
                "👤 アカウント管理",
                href="/account",
                color=COLOR_THEME["text_main"],
                size="2",
            ),

            rx.divider(border_color=COLOR_THEME["border"]),

            # 3. 分析・ダッシュボードセクション（Metabase）
            rx.text("分析・ダッシュボード", size="1", color="gray", font_weight="bold"),
            rx.link(
                "📊 グラフィック確認 (Metabase)",
                href=os.getenv("METABASE_URL", "http://localhost:3001"),
                is_external=True,
                color=COLOR_THEME["accent"],
                size="2",
                font_weight="bold",
            ),

            rx.spacer(),

            # ログアウト
            rx.link("🚪 ログアウト", href="/", color="red", size="2"),

            width="240px",
            height="100vh",
            padding="4",
            background_color=COLOR_THEME["bg_main"],
            border_right=f"1px solid {COLOR_THEME['border']}",
            align_items="start",
            spacing="3",
        ),

        # 右側：メインコンテンツ表示エリア
        rx.vstack(
            rx.hstack(
                rx.heading(page_title, size="5", color=COLOR_THEME["text_main"]),
                width="100%",
                padding_y="3",
                border_bottom=f"1px solid {COLOR_THEME['border']}",
            ),
            rx.box(
                content,
                width="100%",
                padding_y="4",
            ),
            width="100%",
            min_width="0",
            height="100vh",
            padding_x="6",
            background_color=COLOR_THEME["bg_sub"],
            align_items="start",
        ),
        width="100%",
        spacing="0",
    )
