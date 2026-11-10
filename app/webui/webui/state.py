# app/webui/webui/state.py

import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
import reflex as rx

API_URL = os.getenv("API_URL", "http://fastapi:8000")
logger = logging.getLogger("reflex")


def _parse_num(value: str) -> Optional[str]:
    """フォーム入力を数値文字列へ正規化する (空欄はNone、カンマ除去)。"""
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", "")
    return cleaned if cleaned else None


class WebUIState(rx.State):
    """アプリケーションのグローバルステート"""
    # 認証クッキー層
    token: str = rx.Cookie("", name="auth_token")
    is_authenticated: str = rx.Cookie("false", name="is_authenticated")
    user_id: str = rx.Cookie("", name="user_id")
    username: str = rx.Cookie("", name="username")

    # フォーム用一時変数
    input_username: str = ""
    input_password: str = ""
    auth_error: str = ""

    # パイプライン・アップロード制御
    upload_results: List[Dict[str, Any]] = []
    ingest_message: str = ""
    is_loading: bool = False
    trigger_pipeline: bool = True
    is_finance: bool = False

    # ================================================================
    # レシート確認ページ用のステート
    # ================================================================
    # 一覧
    receipts: List[Dict[str, Any]] = []
    receipts_total: int = 0
    receipts_pending_total: int = 0
    receipts_offset: int = 0
    receipts_limit: int = 50
    receipt_filter: str = "pending"  # pending / approved / all
    receipt_store_query: str = ""
    receipt_list_message: str = ""
    is_receipt_list_loading: bool = False

    # 選択中のレシート詳細
    current_receipt_id: str = ""
    current_file_hash: str = ""
    current_original_filename: str = ""
    current_permission: str = "read"
    current_readonly: bool = False
    current_approved_at: str = ""
    current_needs_review: bool = False
    current_review_reasons: List[str] = []
    receipt_ocr_text: str = ""
    receipt_mime_type: str = ""
    receipt_image_url: str = ""  # data URL
    receipt_image_error: str = ""
    is_receipt_detail_loading: bool = False

    # 編集フォーム (ヘッダー)
    form_store_name: str = ""
    form_transaction_date: str = ""
    form_payment_method: str = ""
    form_currency: str = ""
    form_subtotal: str = ""
    form_discount: str = ""
    form_tax: str = ""
    form_total: str = ""

    # 編集フォーム (品目)
    form_items: List[Dict[str, str]] = []

    # 保存・承認結果メッセージ
    receipt_message: str = ""
    receipt_error: str = ""
    is_receipt_saving: bool = False
    is_receipt_approving: bool = False

    # ----------------------------------------------------------------
    # 認証
    # ----------------------------------------------------------------

    def change_username(self, val: str):
        self.input_username = val

    def change_password(self, val: str):
        self.input_password = val

    def toggle_pipeline(self, checked: bool):
        self.trigger_pipeline = checked

    def toggle_finance(self, checked: bool):
        """UI上で金融明細CSVトグルが切り替えられた時のイベントハンドラ"""
        self.is_finance = checked

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def handle_login(self):
        """FastAPIの認証エンドポイントを叩き、JWTトークンを取得して保持する"""
        if not self.input_username.strip() or not self.input_password.strip():
            self.auth_error = "ユーザー名とパスワードを入力してください。"
            return
        self.auth_error = ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{API_URL}/api/v1/auth/login",
                    json={"username": self.input_username, "password": self.input_password}
                )
                if response.status_code == 200:
                    res_data = response.json()
                    self.token = res_data.get("access_token", "")
                    self.user_id = res_data.get("user_id", "")
                    self.username = res_data.get("username", "")
                    self.is_authenticated = "true"
                    return rx.redirect("/upload")
                elif response.status_code == 401:
                    self.auth_error = "ユーザー名またはパスワードが間違っています。"
                else:
                    self.auth_error = f"認証エラー: (Status {response.status_code})"
        except Exception as e:
            self.auth_error = f"バックエンドとの通信に失敗しました: {str(e)}"

    async def check_authentication(self):
        """ページロード時に認証状態を検証し、未認証ならログイン画面へ強制送還する"""
        if self.is_authenticated != "true" or not self.token:
            logger.warning("[SECURITY ALERT] Unauthenticated access blocked. Evicting to root.")
            yield rx.redirect("/")
            return

    def handle_logout(self):
        """ログアウト処理"""
        self.is_authenticated = "false"
        self.token = ""
        self.user_id = ""
        self.username = ""
        self.input_username = ""
        self.input_password = ""
        self.upload_results = []
        self.ingest_message = ""
        return rx.redirect("/")

    async def handle_file_upload(self, files: List[rx.UploadFile]):
        """
        【本番セキュリティ仕様】
        選択されたファイルを読み込み、AuthorizationヘッダーにJWTを添付して
        FastAPIの /api/v1/ingest へマルチパート送信する
        """
        if not files:
            self.ingest_message = "ファイルが選択されていません。"
            return

        self.is_loading = True
        self.upload_results = []
        self.ingest_message = ""

        # マルチパートフォーム用データの組み立て
        form_files = []
        for file in files:
            file_bytes = await file.read()
            form_files.append(("files", (file.filename, file_bytes, file.content_type)))

        # 💡 安全なJWT署名検証をバックエンドに強制させるためのヘッダー契約
        headers = {
            "Authorization": f"Bearer {self.token}"
        }

        if self.is_finance:
            target_url = f"{API_URL}/api/v1/finance"
            params = {}  # 金融CSVは確定処理のため、パイプライン起動スイッチ等は不要（常に起動）
        else:
            target_url = f"{API_URL}/api/v1/ingest"
            params = {"trigger_pipeline": str(self.trigger_pipeline).lower()}

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    target_url,
                    files=form_files,
                    headers=headers,
                    params=params
                )
                if response.status_code == 200:
                    res_data = response.json()
                    self.upload_results = res_data.get("files", [])
                    self.ingest_message = res_data.get("message", "インジェスト処理が正常に受理されました。")
                else:
                    self.ingest_message = f"エラー (Status {response.status_code}): {response.text}"
        except Exception as e:
            self.ingest_message = f"パイプラインへの投入通信に失敗しました: {str(e)}"
        finally:
            self.is_loading = False

    # ----------------------------------------------------------------
    # レシート確認: 一覧
    # ----------------------------------------------------------------

    def set_receipt_filter(self, status: str):
        """一覧フィルタ (pending / approved / all) を切り替えて再読み込みする"""
        self.receipt_filter = status
        self.receipts_offset = 0
        return WebUIState.load_receipts

    def set_receipt_store_query(self, val: str):
        self.receipt_store_query = val

    def receipt_prev_page(self):
        self.receipts_offset = max(0, self.receipts_offset - self.receipts_limit)
        return WebUIState.load_receipts

    def receipt_next_page(self):
        self.receipts_offset = self.receipts_offset + self.receipts_limit
        return WebUIState.load_receipts

    async def load_receipts(self):
        """未承認/承認済みレシート一覧を取得する"""
        if not self.token:
            return

        self.is_receipt_list_loading = True
        self.receipt_list_message = ""

        params: Dict[str, Any] = {
            "status": self.receipt_filter,
            "limit": self.receipts_limit,
            "offset": self.receipts_offset,
        }
        if self.receipt_store_query.strip():
            params["store"] = self.receipt_store_query.strip()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{API_URL}/api/v1/receipts",
                    params=params,
                    headers=self._auth_headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    self.receipts = data.get("items", [])
                    self.receipts_total = data.get("total", 0)
                    self.receipts_pending_total = data.get("pending_total", 0)
                    if not self.receipts and self.receipts_total == 0:
                        self.receipt_list_message = "対象のレシートはありません。"
                else:
                    self.receipt_list_message = f"一覧の取得に失敗しました (Status {response.status_code}): {response.text}"
        except Exception as e:
            self.receipt_list_message = f"バックエンドとの通信に失敗しました: {str(e)}"
        finally:
            self.is_receipt_list_loading = False

    # ----------------------------------------------------------------
    # レシート確認: 詳細表示
    # ----------------------------------------------------------------

    async def open_receipt(self, receipt_id: str):
        """レシート詳細 (OCRテキスト + DB内容 + 原本画像) を読み込む"""
        if not self.token or not receipt_id:
            return

        self.is_receipt_detail_loading = True
        self.current_receipt_id = receipt_id
        self.receipt_message = ""
        self.receipt_error = ""
        self.receipt_image_url = ""
        self.receipt_image_error = ""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{API_URL}/api/v1/receipts/{receipt_id}",
                    headers=self._auth_headers(),
                )
                if response.status_code != 200:
                    self.receipt_error = f"詳細の取得に失敗しました (Status {response.status_code})"
                    self.current_receipt_id = ""
                    return

                detail = response.json()

                self.current_file_hash = detail.get("file_hash", "")
                self.current_original_filename = detail.get("original_filename") or ""
                self.current_permission = detail.get("permission", "read")
                self.current_readonly = self.current_permission not in ("owner", "admin", "write")
                self.current_needs_review = bool(detail.get("needs_review", False))
                self.current_review_reasons = list(detail.get("review_reasons") or [])
                self.receipt_ocr_text = detail.get("ocr_text") or ""
                self.receipt_mime_type = detail.get("mime_type") or ""

                approved_at = detail.get("approved_at")
                if approved_at:
                    # ISO表記を "YYYY-MM-DD HH:MM" に簡略化
                    self.current_approved_at = str(approved_at).replace("T", " ")[:16]
                else:
                    self.current_approved_at = ""

                # フォーム初期値
                self.form_store_name = detail.get("store_name") or ""
                transaction_date = detail.get("transaction_date")
                self.form_transaction_date = str(transaction_date) if transaction_date else ""
                self.form_payment_method = detail.get("payment_method") or ""
                self.form_currency = detail.get("currency") or "JPY"
                self.form_subtotal = detail.get("subtotal_amount") or ""
                self.form_discount = detail.get("discount_amount") or ""
                self.form_tax = detail.get("tax_amount") or ""
                self.form_total = detail.get("total_amount") or ""

                # 品目 (すべて文字列として保持。raw_text は保存時に来歴としてそのまま戻す)
                self.form_items = [
                    {
                        "item_name": str(item.get("item_name") or ""),
                        "quantity": str(item.get("quantity") or ""),
                        "unit_price": str(item.get("unit_price") or ""),
                        "line_amount": str(item.get("line_amount") or ""),
                        "tax_rate": str(item.get("tax_rate") or ""),
                        "raw_text": str(item.get("raw_text") or ""),
                    }
                    for item in detail.get("items", [])
                ]
        except Exception as e:
            self.receipt_error = f"詳細の取得に失敗しました: {str(e)}"
            self.current_receipt_id = ""
        finally:
            self.is_receipt_detail_loading = False

        # 原本画像は別途読み込む (失敗しても詳細表示は続行)
        await self._load_receipt_image()

    async def _load_receipt_image(self):
        self.receipt_image_url = ""
        self.receipt_image_error = ""
        """原本画像をサーバー側で取得し、data URL として保持する (JWTをURLに露出しない)"""
        if not self.current_receipt_id:
            return
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{API_URL}/api/v1/receipts/{self.current_receipt_id}/image",
                    headers=self._auth_headers(),
                )
                if response.status_code != 200:
                    self.receipt_image_error = "原本画像を取得できませんでした。"
                    return

                content: bytes = response.content
                mime_type = response.headers.get("content-type", self.receipt_mime_type or "image/jpeg")

                if mime_type == "application/pdf":
                    self.receipt_image_error = "PDFファイルのためブラウザで画像表示できません。"
                    return

                # Pillow があれば大きな画像を縮小して転送量を抑える
                try:
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(content))
                    if image.width > 1600 or image.height > 1600:
                        image.thumbnail((1600, 1600))
                        buffer = io.BytesIO()
                        image = image.convert("RGB")
                        image.save(buffer, format="JPEG", quality=85)
                        content = buffer.getvalue()
                        mime_type = "image/jpeg"
                except ImportError:
                    # Pillow 未インストール環境では元画像をそのまま使う
                    pass

                if len(content) > 8 * 1024 * 1024:
                    self.receipt_image_error = "画像サイズが大きすぎるため表示をスキップしました。"
                    return

                self.receipt_image_url = (
                    f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
                )
        except Exception as e:
            self.receipt_image_error = f"画像の取得に失敗しました: {str(e)}"

    def close_receipt(self):
        """詳細パネルを閉じて一覧に戻る"""
        self.current_receipt_id = ""
        self.receipt_image_url = ""
        self.receipt_ocr_text = ""
        self.form_items = []
        self.receipt_message = ""
        self.receipt_error = ""
        self.receipt_image_error = ""
        return WebUIState.load_receipts

    # ----------------------------------------------------------------
    # レシート確認: フォーム編集
    # ----------------------------------------------------------------

    def set_form_store_name(self, val: str):
        self.form_store_name = val

    def set_form_transaction_date(self, val: str):
        self.form_transaction_date = val

    def set_form_payment_method(self, val: str):
        self.form_payment_method = val

    def set_form_currency(self, val: str):
        self.form_currency = val

    def set_form_subtotal(self, val: str):
        self.form_subtotal = val

    def set_form_discount(self, val: str):
        self.form_discount = val

    def set_form_tax(self, val: str):
        self.form_tax = val

    def set_form_total(self, val: str):
        self.form_total = val

    def set_item_field(self, index: int, field: str, value: str):
        """品目行の入力を保持する (on_change=State.set_item_field(i, "item_name") として利用)。
        リストは再代入して確実に再描画させる。"""
        if 0 <= index < len(self.form_items):
            updated = list(self.form_items)
            updated[index] = {**updated[index], field: value}
            self.form_items = updated

    def add_item(self):
        self.form_items = self.form_items + [
            {
                "item_name": "",
                "quantity": "",
                "unit_price": "",
                "line_amount": "",
                "tax_rate": "",
                "raw_text": "",
            }
        ]

    def remove_item(self, index: int):
        self.form_items = [
            item
            for i, item in enumerate(self.form_items)
            if i != index
        ]

    # ----------------------------------------------------------------
    # レシート確認: 保存・承認
    # ----------------------------------------------------------------

    def _build_receipt_payload(
        self, items: List[Dict[str, str]], approve: Optional[bool]
    ) -> Dict[str, Any]:
        """フォームの内容をPATCHリクエストボディへ組み立てる。

        items には検証済みの行のみ渡すこと (完全な空行は呼び出し側で除外済み)。
        raw_text は行の来歴としてそのままサーバーへ戻す。
        """
        return {
            "store_name": self.form_store_name.strip() or None,
            "transaction_date": self.form_transaction_date.strip() or None,
            "payment_method": self.form_payment_method.strip() or None,
            "currency": self.form_currency.strip() or None,
            "subtotal_amount": _parse_num(self.form_subtotal),
            "discount_amount": _parse_num(self.form_discount),
            "tax_amount": _parse_num(self.form_tax),
            "total_amount": _parse_num(self.form_total),
            "items": [
                {
                    "item_name": item["item_name"].strip(),
                    "quantity": _parse_num(item["quantity"]),
                    "unit_price": _parse_num(item["unit_price"]),
                    "line_amount": _parse_num(item["line_amount"]),
                    "tax_rate": _parse_num(item["tax_rate"]),
                    "raw_text": item.get("raw_text") or None,
                }
                for item in items
            ],
            "approve": approve,
        }

    def _can_write(self) -> bool:
        return self.current_permission in ("owner", "admin", "write")

    async def _save_receipt(self, approve: Optional[bool], success_message: str):
        """保存 (＋オプションで承認) を実行し、詳細と一覧を更新する"""
        if not self.current_receipt_id:
            return
        if not self._can_write():
            self.receipt_error = "このレシートを編集する権限がありません (閲覧のみ)。"
            return

        self.is_receipt_saving = True
        self.is_receipt_approving = approve is True
        self.receipt_message = ""
        self.receipt_error = ""

        # 品目行の検証: 完全な空行は無視するが、
        # 品目名が空の行が残っている場合は誤削除防止のため保存を中断する
        valid_items: List[Dict[str, str]] = []
        for position, item in enumerate(self.form_items, start=1):
            if not any(str(value).strip() for value in item.values()):
                continue
            if not item["item_name"].strip():
                self.is_receipt_saving = False
                self.is_receipt_approving = False
                self.receipt_error = (
                    f"{position}行目に品目名が入力されていません。"
                    "品目名を入力するか、その行を削除してください。"
                )
                return
            valid_items.append(item)

        payload = self._build_receipt_payload(valid_items, approve)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.patch(
                    f"{API_URL}/api/v1/receipts/{self.current_receipt_id}",
                    json=payload,
                    headers=self._auth_headers(),
                )
                if response.status_code == 200:
                    # 表示を最新化してから完了メッセージを出す (open_receipt がメッセージを初期化するため順序が重要)
                    await self.open_receipt(self.current_receipt_id)
                    await self.load_receipts()
                    self.receipt_message = success_message
                else:
                    detail = response.text
                    try:
                        detail = response.json().get("detail", detail)
                    except Exception:
                        pass
                    self.receipt_error = f"保存に失敗しました (Status {response.status_code}): {detail}"
        except Exception as e:
            self.receipt_error = f"保存の通信に失敗しました: {str(e)}"
        finally:
            self.is_receipt_saving = False
            self.is_receipt_approving = False

    async def save_receipt(self):
        """修正内容を保存する (承認状態は変更しない。承認済みの場合は要再承認へ戻る)"""
        await self._save_receipt(None, "修正内容を保存しました。")

    async def save_and_approve_receipt(self):
        """修正内容を保存して承認する (保存と承認を1トランザクションで実行)"""
        await self._save_receipt(True, "保存して承認しました。")

    async def unapprove_receipt(self):
        """承認を取り消して未承認に戻す"""
        if not self.current_receipt_id:
            return
        if not self._can_write():
            self.receipt_error = "このレシートを編集する権限がありません (閲覧のみ)。"
            return

        self.is_receipt_saving = True
        self.is_receipt_approving = False
        self.receipt_message = ""
        self.receipt_error = ""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{API_URL}/api/v1/receipts/{self.current_receipt_id}/unapprove",
                    headers=self._auth_headers(),
                )
                if response.status_code == 200:
                    await self.open_receipt(self.current_receipt_id)
                    await self.load_receipts()
                    self.receipt_message = "承認を取り消しました。"
                else:
                    self.receipt_error = f"承認取り消しに失敗しました (Status {response.status_code})"
        except Exception as e:
            self.receipt_error = f"通信に失敗しました: {str(e)}"
        finally:
            self.is_receipt_saving = False
            self.is_receipt_approving = False


