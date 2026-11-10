# === app/webui/webui/webui.py ===
import reflex as rx
from .state import WebUIState
from .pages.login import login_page
from .pages.upload import upload_page
from .pages.edit import edit_page
from .pages.receipts import receipts_page
from .pages.account import account_page
from .pages.search import search_page,SearchState

# アプリケーションの作成
app = rx.App()

# 画面とURLパスの厳格なマッピング
app.add_page(login_page, route="/")           # 1. ログイン（ルート）
app.add_page(upload_page, route="/upload",on_load=WebUIState.check_authentication)    # 2. アップロード画面
app.add_page(receipts_page, route="/receipts", on_load=[WebUIState.check_authentication, WebUIState.load_receipts])  # 3. レシート確認画面（💡新設）
app.add_page(edit_page, route="/edit",on_load=WebUIState.check_authentication)        # 4. データ修正画面
app.add_page(search_page, route="/search", title="Search",on_load=[WebUIState.check_authentication, SearchState.load_tools])
app.add_page(account_page, route="/account",on_load=WebUIState.check_authentication)  # 5. アカウント管理画面（💡追加）
