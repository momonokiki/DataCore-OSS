import getpass
import sys
from sqlalchemy.exc import IntegrityError
from app.infrastructure.db.session import get_sync_db_session
from app.infrastructure.db.models.users import User
from app.infrastructure.security.pass_hash import get_password_hash

def main():
    print("=== 初期ユーザーの対話的作成 ===")
    
    username = input("初期ユーザー名 (username): ").strip()
    if not username:
        print("エラー: ユーザー名は必須です。")
        sys.exit(1)
        
    password = getpass.getpass("初期パスワード (password): ")
    password_confirm = getpass.getpass("初期パスワード (確認用): ")
    
    if password != password_confirm:
        print("エラー: パスワードが一致しません。")
        sys.exit(1)

    # ハッシュ化（必要に応じてパスワード処理を実装）
    hashed_password = get_password_hash(password) 

    # 同期セッションをコンテキストマネージャで安全に利用
    try:
        with get_sync_db_session() as session:
            user = User(
                username=username,
                hashed_password=hashed_password,
                is_active=True
            )
            session.add(user)
            print(f"\n[実行] ユーザー '{username}' を登録中！")
    except IntegrityError:
        print(f"\n[警告] ユーザー '{username}' はすでに存在しています。")
        sys.exit(1)
    except Exception as e:
        print(f"\n[エラー] 予期せぬエラーが発生しました: {e}")
        sys.exit(1)
    print(f"\n[成功]ユーザー'{username}'を登録しました。")
if __name__ == "__main__":
    main()

