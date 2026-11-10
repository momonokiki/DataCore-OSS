# app/infrastructure/security/jwt.py
from datetime import datetime, timedelta, timezone
import jwt
from app.core.config import settings

def create_access_token(data: dict) -> str:
    """環境変数から期限を取得し、JWTアクセストークンを生成する"""
    to_encode = data.copy()
    
    # 環境変数から有効期限（分）を取得して設定
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    # 署名してトークン作成
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

