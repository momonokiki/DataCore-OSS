# app/webui/webui/pages/receipts.py
"""
レシート確認ページ

- 上部: 未承認レシート一覧 (フィルタ: 未承認 / 承認済み / すべて)
- 選択すると詳細が開く:
  - 左: レシートDBの内容 (ヘッダー + 品目) を直接編集できるフォーム
  - 右: OCR結果テキストと原本画像 (クリックで拡大表示)
  - 「保存」「保存して承認」「承認を取り消す」で運用する
"""

import reflex as rx
from typing import Any, Dict

from ..state import WebUIState
from ..styles import COLOR_THEME, CARD_STYLE
from ..layout import common_layout

# 詳細パネルは一覧より広く使う
WIDE_CARD_STYLE = {
    "padding": "6",
    "background_color": COLOR_THEME["bg_main"],
    "box_shadow": "md",
    "border": f"1px solid {COLOR_THEME['border']}",
    "border_radius": "lg",
    "width": "100%",
    "max_width": "1100px",
}


# ---------------------------------------------------------------------------
# 一覧の各行
# ---------------------------------------------------------------------------


def _status_badges(receipt: rx.Var[Dict[str, Any]]) -> rx.Component:
    """承認状態と要確認フラグのバッジ"""
    return rx.hstack(
        rx.cond(
            receipt["approved_at"],
            rx.badge("承認済み", color_scheme="teal", variant="soft"),
            rx.badge("未承認", color_scheme="orange", variant="soft"),
        ),
        rx.cond(
            receipt["needs_review"],
            rx.badge("要確認", color_scheme="red", variant="soft"),
        ),
        spacing="1",
    )


def receipt_row(receipt: rx.Var[Dict[str, Any]]) -> rx.Component:
    """一覧の1行 (クリックで詳細を開く)"""
    return rx.hstack(
        rx.box(
            width="6px",
            height="48px",
            background_color=rx.cond(
                receipt["approved_at"],
                COLOR_THEME["accent"],
                "#ED8936",
            ),
            border_radius="md",
        ),
        rx.vstack(
            rx.text(
                rx.cond(receipt["store_name"], receipt["store_name"], "(店舗名なし)"),
                font_weight="bold",
                size="3",
                color=COLOR_THEME["text_main"],
            ),
            rx.hstack(
                rx.text(
                    rx.cond(receipt["transaction_date"], receipt["transaction_date"], "日付なし"),
                    size="1",
                    color="gray",
                ),
                rx.text(
                    rx.cond(receipt["payment_method"], receipt["payment_method"], ""),
                    size="1",
                    color="gray",
                ),
                spacing="2",
            ),
            align_items="start",
            spacing="0",
        ),
        rx.spacer(),
        rx.text(
            rx.cond(
                receipt["total_amount"],
                "¥ " + receipt["total_amount"].to(str),
                "¥ ---",
            ),
            font_weight="bold",
            size="3",
            color=COLOR_THEME["text_main"],
        ),
        _status_badges(receipt),
        rx.button(
            "開く",
            size="1",
            variant="surface",
            color_scheme="teal",
            on_click=WebUIState.open_receipt(receipt["id"]),
        ),
        width="max-content",
        min_width="100%",
        border_bottom=f"1px solid {COLOR_THEME['border']}",
        padding_y="2",
        align="center",
        spacing="3",
    )


def receipts_list_content() -> rx.Component:
    """一覧カード (フィルタタブ + 店舗検索 + 一覧 + ページング)"""
    return rx.box(
        rx.vstack(
            # フィルタタブ + 未承認件数バッジ
            rx.hstack(
                rx.button(
                    "未承認",
                    on_click=WebUIState.set_receipt_filter("pending"),
                    variant=rx.cond(
                        WebUIState.receipt_filter == "pending", "solid", "surface"
                    ),
                    color_scheme="orange",
                    size="2",
                ),
                rx.button(
                    "承認済み",
                    on_click=WebUIState.set_receipt_filter("approved"),
                    variant=rx.cond(
                        WebUIState.receipt_filter == "approved", "solid", "surface"
                    ),
                    color_scheme="teal",
                    size="2",
                ),
                rx.button(
                    "すべて",
                    on_click=WebUIState.set_receipt_filter("all"),
                    variant=rx.cond(
                        WebUIState.receipt_filter == "all", "solid", "surface"
                    ),
                    color_scheme="gray",
                    size="2",
                ),
                rx.spacer(),
                rx.badge(
                    f"未承認 {WebUIState.receipts_pending_total} 件",
                    color_scheme="orange",
                    variant="soft",
                ),
                width="100%",
                align="center",
                wrap="wrap",
            ),

            # 店舗名検索
            rx.hstack(
                rx.text("店舗名検索:", size="2", color="gray"),
                rx.input(
                    placeholder="例: セブンイレブン",
                    value=WebUIState.receipt_store_query,
                    on_change=WebUIState.set_receipt_store_query,
                    size="2",
                    width="240px",
                ),
                rx.button(
                    "検索",
                    on_click=WebUIState.load_receipts,
                    size="2",
                    variant="surface",
                ),
                width="100%",
                wrap="wrap",
            ),

            # 読み込み中 / 一覧 / 空メッセージ
            rx.cond(
                WebUIState.is_receipt_list_loading,
                rx.center(rx.spinner(size="2"), padding="4"),
                rx.cond(
                    WebUIState.receipts.length() > 0,
                    # 狭い画面では横スクロールで対応 (折り返しによる潰れを防ぐ)
                    rx.box(
                        rx.vstack(
                            rx.foreach(WebUIState.receipts, receipt_row),
                            width="100%",
                            spacing="0",
                        ),
                        width="100%",
                        overflow_x="auto",
                    ),
                    rx.text(
                        WebUIState.receipt_list_message,
                        color="gray",
                        size="2",
                        padding="4",
                    ),
                ),
            ),

            # ページング
            rx.hstack(
                rx.button(
                    "← 前",
                    on_click=WebUIState.receipt_prev_page,
                    is_disabled=WebUIState.receipts_offset == 0,
                    size="2",
                    variant="surface",
                ),
                rx.text(
                    f"{WebUIState.receipts_offset + 1}〜"
                    f"{WebUIState.receipts_offset + WebUIState.receipts.length()}"
                    f" / 全 {WebUIState.receipts_total} 件",
                    size="2",
                    color="gray",
                ),
                rx.button(
                    "次 →",
                    on_click=WebUIState.receipt_next_page,
                    is_disabled=(
                        WebUIState.receipts_offset + WebUIState.receipts_limit
                    )
                    >= WebUIState.receipts_total,
                    size="2",
                    variant="surface",
                ),
                width="100%",
                justify="center",
                wrap="wrap",
                padding_top="2",
            ),
            spacing="3",
            width="100%",
        ),
        **CARD_STYLE,
    )


# ---------------------------------------------------------------------------
# 詳細: フォーム部品
# ---------------------------------------------------------------------------


def _form_field(
    label: str, input_component: rx.Component, label_width: str = "110px"
) -> rx.Component:
    """ラベル + 入力欄の1行"""
    return rx.hstack(
        rx.text(label, font_weight="bold", size="2", width=label_width),
        input_component,
        width="100%",
        align="center",
    )


def item_row(item: rx.Var[Dict[str, str]], index: rx.Var[int]) -> rx.Component:
    """品目1行 (value で制御し、on_change で state へ反映。
    制御付き入力にすることで、レシート切替時に表示が前の内容で残らないようにしている)"""
    return rx.hstack(
        rx.input(
            value=item["item_name"],
            on_change=WebUIState.set_item_field(index, "item_name"),
            is_disabled=WebUIState.current_readonly,
            size="1",
            width="100%",
            flex="1",
            min_width="160px",
        ),
        rx.input(
            value=item["quantity"],
            on_change=WebUIState.set_item_field(index, "quantity"),
            is_disabled=WebUIState.current_readonly,
            size="1",
            width="70px",
            flex_shrink="0",
        ),
        rx.input(
            value=item["unit_price"],
            on_change=WebUIState.set_item_field(index, "unit_price"),
            is_disabled=WebUIState.current_readonly,
            size="1",
            width="90px",
            flex_shrink="0",
        ),
        rx.input(
            value=item["line_amount"],
            on_change=WebUIState.set_item_field(index, "line_amount"),
            is_disabled=WebUIState.current_readonly,
            size="1",
            width="90px",
            flex_shrink="0",
        ),
        rx.input(
            value=item["tax_rate"],
            on_change=WebUIState.set_item_field(index, "tax_rate"),
            is_disabled=WebUIState.current_readonly,
            size="1",
            width="60px",
            flex_shrink="0",
        ),
        rx.button(
            "✕",
            on_click=WebUIState.remove_item(index),
            is_disabled=WebUIState.current_readonly,
            size="1",
            variant="soft",
            color_scheme="red",
            flex_shrink="0",
        ),
        width="100%",
        spacing="2",
        align="center",
    )


def items_table() -> rx.Component:
    """品目テーブル (ヘッダー + 行 + 行追加)
    狭い画面では横スクロールで対応するため、中身を overflow_x=auto のボックスで包む"""
    return rx.vstack(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "品目名", size="1", font_weight="bold",
                        width="100%", flex="1", min_width="160px",
                    ),
                    rx.text("数量", size="1", font_weight="bold", width="70px", flex_shrink="0"),
                    rx.text("単価", size="1", font_weight="bold", width="90px", flex_shrink="0"),
                    rx.text("金額", size="1", font_weight="bold", width="90px", flex_shrink="0"),
                    rx.text("税%", size="1", font_weight="bold", width="60px", flex_shrink="0"),
                    rx.text("", width="30px", flex_shrink="0"),
                    width="100%",
                    spacing="2",
                    color="gray",
                ),
                rx.foreach(WebUIState.form_items, item_row),
                width="100%",
                spacing="2",
            ),
            width="100%",
            overflow_x="auto",
        ),
        rx.cond(
            WebUIState.current_readonly,
            rx.text("(閲覧のみのため編集できません)", size="1", color="gray"),
            rx.button(
                "+ 行を追加",
                on_click=WebUIState.add_item,
                size="1",
                variant="surface",
                color_scheme="teal",
            ),
        ),
        width="100%",
        spacing="2",
        align_items="start",
    )


def receipt_form() -> rx.Component:
    """レシートDBの内容を編集するフォーム (左側)"""
    disabled = WebUIState.current_readonly
    return rx.vstack(
        # ヘッダー項目
        _form_field(
            "店舗名",
            rx.input(
                value=WebUIState.form_store_name,
                on_change=WebUIState.set_form_store_name,
                is_disabled=disabled,
                flex="1",
                min_width="0",
            ),
        ),
        _form_field(
            "取引日",
            rx.input(
                type="date",
                value=WebUIState.form_transaction_date,
                on_change=WebUIState.set_form_transaction_date,
                is_disabled=disabled,
                flex="1",
                min_width="0",
            ),
        ),
        _form_field(
            "支払方法",
            rx.input(
                value=WebUIState.form_payment_method,
                on_change=WebUIState.set_form_payment_method,
                is_disabled=disabled,
                flex="1",
                min_width="0",
            ),
        ),
        rx.hstack(
            _form_field(
                "通貨",
                rx.input(
                    value=WebUIState.form_currency,
                    on_change=WebUIState.set_form_currency,
                    is_disabled=disabled,
                    width="100px",
                ),
            ),
            _form_field(
                "小計",
                rx.input(
                    value=WebUIState.form_subtotal,
                    on_change=WebUIState.set_form_subtotal,
                    is_disabled=disabled,
                    width="120px",
                ),
                label_width="60px",
            ),
            _form_field(
                "割引",
                rx.input(
                    value=WebUIState.form_discount,
                    on_change=WebUIState.set_form_discount,
                    is_disabled=disabled,
                    width="120px",
                ),
                label_width="60px",
            ),
            width="100%",
            spacing="2",
            wrap="wrap",
        ),
        rx.hstack(
            _form_field(
                "税額",
                rx.input(
                    value=WebUIState.form_tax,
                    on_change=WebUIState.set_form_tax,
                    is_disabled=disabled,
                    width="120px",
                ),
            ),
            _form_field(
                "合計",
                rx.input(
                    value=WebUIState.form_total,
                    on_change=WebUIState.set_form_total,
                    is_disabled=disabled,
                    width="140px",
                ),
                label_width="60px",
            ),
            width="100%",
            spacing="2",
            wrap="wrap",
        ),
        rx.divider(border_color=COLOR_THEME["border"]),
        rx.text("品目 (明細)", font_weight="bold", size="3"),
        items_table(),
        width="100%",
        spacing="3",
        align_items="start",
    )


def action_buttons() -> rx.Component:
    """保存 / 承認ボタン群"""
    disabled = WebUIState.current_readonly | WebUIState.is_receipt_saving
    return rx.vstack(
        rx.hstack(
            rx.button(
                "保存",
                on_click=WebUIState.save_receipt,
                is_disabled=disabled,
                variant="outline",
                color_scheme="teal",
                size="3",
            ),
            rx.button(
                "保存して承認",
                on_click=WebUIState.save_and_approve_receipt,
                is_disabled=disabled,
                background_color=COLOR_THEME["accent"],
                color="white",
                size="3",
                loading=WebUIState.is_receipt_approving,
            ),
            rx.cond(
                WebUIState.current_approved_at != "",
                rx.button(
                    "承認を取り消す",
                    on_click=WebUIState.unapprove_receipt,
                    is_disabled=disabled,
                    variant="soft",
                    color_scheme="red",
                    size="3",
                ),
            ),
            spacing="3",
            wrap="wrap",
        ),
        rx.cond(
            WebUIState.receipt_message,
            rx.text(WebUIState.receipt_message, color="teal", size="2", font_weight="bold"),
        ),
        rx.cond(
            WebUIState.receipt_error,
            rx.text(WebUIState.receipt_error, color="red", size="2"),
        ),
        width="100%",
        spacing="2",
        align_items="start",
    )


# ---------------------------------------------------------------------------
# 詳細: OCR結果・画像パネル
# ---------------------------------------------------------------------------


def receipt_image_panel() -> rx.Component:
    """原本画像サムネイル (クリックで拡大ダイアログ)"""
    return rx.vstack(
        rx.text("原本画像 (クリックで拡大)", font_weight="bold", size="3"),
        rx.cond(
            WebUIState.receipt_image_url != "",
            rx.dialog.root(
                rx.dialog.trigger(
                    rx.image(
                        src=WebUIState.receipt_image_url,
                        height="240px",
                        border=f"1px solid {COLOR_THEME['border']}",
                        border_radius="md",
                        cursor="pointer",
                    ),
                ),
                rx.dialog.content(
                    rx.dialog.title("原本画像"),
                    rx.image(
                        src=WebUIState.receipt_image_url,
                        width="100%",
                        max_height="75vh",
                        object_fit="contain",
                    ),
                    rx.dialog.close(
                        rx.button("閉じる", margin_top="2", width="100%"),
                    ),
                ),
            ),
            rx.cond(
                WebUIState.receipt_image_error != "",
                rx.text(WebUIState.receipt_image_error, color="gray", size="2"),
                rx.text("画像なし", color="gray", size="2"),
            ),
        ),
        align_items="start",
        spacing="2",
        width="100%",
    )


def ocr_text_panel() -> rx.Component:
    """OCR結果テキスト (読み取り専用)"""
    return rx.vstack(
        rx.text("OCR結果", font_weight="bold", size="3"),
        rx.cond(
            WebUIState.receipt_ocr_text != "",
            rx.box(
                rx.text(
                    WebUIState.receipt_ocr_text,
                    font_size="1",
                    font_family="mono",
                    white_space="pre-wrap",
                    color=COLOR_THEME["text_main"],
                ),
                width="100%",
                max_height="420px",
                overflow_y="auto",
                padding="4",
                background_color="#FFFFFF",
                border=f"1px solid {COLOR_THEME['border']}",
                border_radius="md",
            ),
            rx.text("OCRテキストがありません", color="gray", size="1"),
        ),
        width="100%",
        spacing="2",
        align_items="start",
    )


# ---------------------------------------------------------------------------
# 詳細カード全体
# ---------------------------------------------------------------------------


def receipt_detail_content() -> rx.Component:
    """選択されたレシートの詳細 (フォーム + OCR + 画像)"""
    return rx.box(
        rx.vstack(
            # ステータス行
            rx.hstack(
                rx.heading("レシート詳細", size="4", color=COLOR_THEME["text_main"]),
                rx.cond(
                    WebUIState.current_approved_at != "",
                    rx.badge(
                        f"承認済み ({WebUIState.current_approved_at})",
                        color_scheme="teal",
                        variant="soft",
                    ),
                    rx.badge("未承認", color_scheme="orange", variant="soft"),
                ),
                rx.cond(
                    WebUIState.current_needs_review,
                    rx.badge("要確認", color_scheme="red", variant="soft"),
                ),
                rx.spacer(),
                rx.text(
                    WebUIState.current_original_filename,
                    size="1",
                    color="gray",
                ),
                rx.button(
                    "閉じる",
                    on_click=WebUIState.close_receipt,
                    size="2",
                    variant="surface",
                ),
                width="100%",
                align="center",
                spacing="3",
                wrap="wrap",
            ),

            # 要確認理由
            rx.cond(
                WebUIState.current_review_reasons.length() > 0,
                rx.vstack(
                    rx.text(
                        "解析時の要確認理由:",
                        size="1",
                        color="red",
                        font_weight="bold",
                    ),
                    rx.hstack(
                        rx.foreach(
                            WebUIState.current_review_reasons,
                            lambda reason: rx.badge(
                                reason, color_scheme="red", variant="soft"
                            ),
                        ),
                        spacing="1",
                        wrap="wrap",
                    ),
                    align_items="start",
                    spacing="1",
                    width="100%",
                ),
            ),

            # メイン: 左フォーム / 右OCR+画像 (デスクトップでは2カラム、狭い画面では縦積み)
            rx.hstack(
                rx.vstack(
                    receipt_form(),
                    rx.divider(border_color=COLOR_THEME["border"]),
                    action_buttons(),
                    flex="3 1 440px",
                    # min-width:auto だと品目テーブルの最小幅 (約540px) が
                    # カラム全体の最小幅になり画面を押し広げるため、
                    # 縮小を許可して内側の横スクロールに任せる
                    min_width="0",
                    spacing="3",
                ),
                rx.vstack(
                    receipt_image_panel(),
                    ocr_text_panel(),
                    flex="2 1 360px",
                    min_width="0",
                    spacing="3",
                ),
                width="100%",
                spacing="6",
                align_items="start",
                wrap="wrap",
            ),

            width="100%",
            spacing="4",
        ),
        **WIDE_CARD_STYLE,
    )


# ---------------------------------------------------------------------------
# ページ本体
# ---------------------------------------------------------------------------


def receipts_content() -> rx.Component:
    """レシート確認ページのメインコンテンツ"""
    return rx.vstack(
        receipts_list_content(),
        rx.cond(
            WebUIState.current_receipt_id != "",
            receipt_detail_content(),
            rx.box(
                rx.text(
                    "一覧からレシートを選ぶと、OCR結果・DB内容・原本画像を確認して修正・承認できます。",
                    size="2",
                    color="gray",
                ),
                width="100%",
                padding="4",
            ),
        ),
        rx.cond(
            WebUIState.is_receipt_detail_loading,
            rx.center(rx.spinner(size="2"), padding="2"),
        ),
        spacing="4",
        width="100%",
    )


def receipts_page() -> rx.Component:
    """共通レイアウトを外枠に被せて返却"""
    return common_layout(receipts_content(), "🧾 レシート確認")
