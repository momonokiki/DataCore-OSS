import reflex as rx

# 白をメインに水色(accent)をあしらった配色
COLOR_THEME = {
    "bg_main": "#FFFFFF",          # 白
    "bg_sub": "#F7FAFC",           # 薄グレー
    "text_main": "#2D3748",        # 濃グレー
    "accent": "#4FD1C5",           # 水色
    "border": "#E2E8F0"            # ライトグレー
}

# 共通の四角いカードデザインの定義
CARD_STYLE = {
    "padding": "6",
    "background_color": COLOR_THEME["bg_main"],
    "box_shadow": "md",
    "border": f"1px solid {COLOR_THEME['border']}",
    "border_radius": "lg",
    "width": "100%",
    "max_width": "600px",
}

