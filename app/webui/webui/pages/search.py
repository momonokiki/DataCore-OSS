
# === app/webui/webui/pages/search.py ===

import os

import httpx
import reflex as rx

from ..layout import common_layout


API_URL = os.getenv("API_URL", "http://fastapi:8000")


def _tool_display_name(tool_name: str) -> str:
    """内部ツール名を画面表示用の名称に変換する"""

    display_names = {
        "yomitoku_ocr": "Yomitoku OCR",
        "nomic_embed_text": "Nomic Embedding",
    }

    return display_names.get(
        tool_name,
        tool_name.replace("_", " ").title(),
    )


class SearchState(rx.State):
    # ================================================================
    # 認証
    # ================================================================

    token: str = rx.Cookie("", name="auth_token")

    def _auth_headers(self) -> dict:
        """FastAPI向けJWT認証ヘッダー"""
        return {
            "Authorization": f"Bearer {self.token}"
        }

    # ================================================================
    # 検索対象
    # ================================================================

    tools: list[dict] = []

    # 内部的にはUUIDまたはl2mediainfoを保持
    selected_tool_id: str = "l2mediainfo"
    selected_tool_name: str = "MediaInfo"

    # ================================================================
    # 検索条件
    # ================================================================

    query: str = ""

    # ================================================================
    # 検索結果
    # ================================================================

    mode: str = ""
    results: list[dict] = []

    # ================================================================
    # 処理状態
    # ================================================================

    loading: bool = False
    error: str = ""

    # ================================================================
    # 画面表示用プロパティ
    # ================================================================

    @rx.var
    def tool_options(self) -> list[str]:
        """検索対象の表示名一覧"""

        return ["MediaInfo"] + [
            _tool_display_name(t["tool_name"])
            for t in self.tools
        ]

    @rx.var
    def mode_label(self) -> str:
        """検索方式の表示名"""

        mode_labels = {
            "mediainfo": "メタデータ検索",
            "text": "OCR文字列検索",
            "embedding": "Embedding意味検索",
        }

        return mode_labels.get(self.mode, self.mode)

    @rx.var
    def result_count(self) -> int:
        """検索結果件数"""

        return len(self.results)

    # ================================================================
    # 検索対象ツール取得
    # ================================================================

    async def load_tools(self):
        """検索可能なL2ツール一覧を取得する"""

        self.loading = True
        self.error = ""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:

                res = await client.get(
                    f"{API_URL}/api/v1/search/tools",
                    headers=self._auth_headers(),
                )

                res.raise_for_status()

                self.tools = res.json()["tools"]

        except Exception as e:
            self.error = str(e)

        finally:
            self.loading = False

    # ================================================================
    # 入力操作
    # ================================================================

    def set_query(self, value: str):
        self.query = value

    def set_tool(self, value: str):
        """画面表示名から内部ツールIDを特定する"""

        self.results = []
        self.mode = ""
        self.error = ""

        if value == "MediaInfo":
            self.selected_tool_id = "l2mediainfo"
            self.selected_tool_name = "MediaInfo"
            return

        tool = next(
            (
                t for t in self.tools
                if _tool_display_name(t["tool_name"]) == value
            ),
            None,
        )

        if tool:
            self.selected_tool_id = tool["tool_id"]
            self.selected_tool_name = _tool_display_name(
                tool["tool_name"]
            )

    # ================================================================
    # 検索処理
    # ================================================================

    async def run_search(self):
        """選択された検索対象に応じて検索する"""

        if not self.query.strip():
            self.error = "検索語を入力してください"
            return

        if not self.selected_tool_id:
            self.error = "検索対象を選択してください"
            return

        self.loading = True
        self.error = ""
        self.results = []
        self.mode = ""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:

                # ----------------------------------------------------
                # MediaInfo検索
                # ----------------------------------------------------

                if self.selected_tool_id == "l2mediainfo":

                    res = await client.get(
                        f"{API_URL}/api/v1/search/mediainfo",
                        params={
                            "q": self.query,
                            "limit": 50,
                        },
                        headers=self._auth_headers(),
                    )

                # ----------------------------------------------------
                # L2 Artifact検索
                # ----------------------------------------------------

                else:

                    res = await client.get(
                        f"{API_URL}/api/v1/search/artifacts",
                        params={
                            "tool_id": self.selected_tool_id,
                            "q": self.query,
                            "limit": 50,
                        },
                        headers=self._auth_headers(),
                    )

                res.raise_for_status()

                data = res.json()

                self.mode = data["mode"]
                self.results = data["results"]

        except Exception as e:
            self.error = str(e)

        finally:
            self.loading = False


# ====================================================================
# L2 Artifact検索結果カード
# ====================================================================

def result_card(item: dict) -> rx.Component:

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(item["tool_name"]),
                rx.badge(item["artifact_type"]),

                rx.cond(
                    item.to(dict).contains("score")
                    & (item["score"] != None),

                    rx.text(
                        f"類似度: {item['score']:.4f}"
                    ),

                    rx.text("文字列一致"),
                ),

                spacing="2",
                wrap="wrap",
            ),

            rx.text(
                item["filehash"],
                size="1",
                color="gray",
            ),

            rx.text(
                item["content_text"].to(str)[:500],
                size="2",
                white_space="pre-wrap",
            ),

            spacing="2",
            width="100%",
        ),

        width="100%",
    )


# ====================================================================
# MediaInfo検索結果カード
# ====================================================================

def mediainfo_card(item: dict) -> rx.Component:

    return rx.card(
        rx.vstack(
            rx.text(
                item["filehash"],
                size="1",
                color="gray",
            ),

            rx.text(
                rx.cond(
                    (item["author_or_device"] != None)
                    & (item["author_or_device"] != ""),

                    f"機器・作者: {item['author_or_device']}",

                    "機器・作者: -",
                )
            ),

            rx.text(
                rx.cond(
                    (item["mimetype"] != None)
                    & (item["mimetype"] != ""),

                    f"MIME: {item['mimetype']}",

                    "MIME: -",
                )
            ),

            rx.text(
                rx.cond(
                    (item["width"] != None)
                    & (item["height"] != None),

                    f"サイズ: {item['width']} x {item['height']}",

                    "サイズ: -",
                )
            ),

            rx.text(
                rx.cond(
                    (item["content_created_at"] != None)
                    & (item["content_created_at"] != ""),

                    f"撮影日時: {item['content_created_at']}",

                    "撮影日時: -",
                )
            ),

            spacing="1",
        ),

        width="100%",
    )


# ====================================================================
# 検索ページ
# ====================================================================

def search_page() -> rx.Component:

    content = rx.vstack(

        # ------------------------------------------------------------
        # ページタイトル
        # ------------------------------------------------------------

        rx.heading(
            "L2 Artifact Search",
            size="6",
        ),

        # ------------------------------------------------------------
        # 検索対象
        # ------------------------------------------------------------

        rx.text(
            "検索対象",
            size="2",
            weight="medium",
        ),

        rx.select(
            SearchState.tool_options,
            placeholder="検索対象を選択",
            value=SearchState.selected_tool_name,
            on_change=SearchState.set_tool,
            width="100%",
        ),

        # ------------------------------------------------------------
        # 検索語
        # ------------------------------------------------------------

        rx.text(
            "検索キーワード",
            size="2",
            weight="medium",
        ),

        rx.input(
            placeholder="検索語を入力",
            value=SearchState.query,
            on_change=SearchState.set_query,
            width="100%",
        ),

        # ------------------------------------------------------------
        # 検索ボタン
        # ------------------------------------------------------------

        rx.button(
            "検索",
            on_click=SearchState.run_search,
            disabled=SearchState.loading,
        ),

        # ------------------------------------------------------------
        # ローディング表示
        # ------------------------------------------------------------

        rx.cond(
            SearchState.loading,
            rx.text(
                "検索中...",
                color="gray",
            ),
        ),

        # ------------------------------------------------------------
        # エラー表示
        # ------------------------------------------------------------

        rx.cond(
            SearchState.error != "",

            rx.callout(
                SearchState.error,
                color="red",
            ),
        ),

        # ------------------------------------------------------------
        # 検索方式・検索結果件数
        # ------------------------------------------------------------

        rx.cond(
            SearchState.mode != "",

            rx.hstack(
                rx.badge(
                    SearchState.selected_tool_name,
                    color_scheme="blue",
                ),

                rx.badge(
                    SearchState.mode_label,
                    color_scheme="green",
                ),

                rx.text(
                    SearchState.result_count.to(str) + " 件",
                    size="2",
                    color="gray",
                ),

                spacing="2",
                wrap="wrap",
                width="100%",
            ),
        ),

        # ------------------------------------------------------------
        # 検索結果
        # ------------------------------------------------------------

        rx.cond(
            SearchState.selected_tool_id == "l2mediainfo",

            rx.vstack(
                rx.foreach(
                    SearchState.results,
                    mediainfo_card,
                ),

                spacing="3",
                width="100%",
            ),

            rx.vstack(
                rx.foreach(
                    SearchState.results,
                    result_card,
                ),

                spacing="3",
                width="100%",
            ),
        ),

        spacing="4",
        width="100%",
        padding="2rem",
    )

    return common_layout(
        content,
        page_title="証跡検索",
    )

