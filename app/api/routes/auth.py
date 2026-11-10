# app/api/routes/auth.py

import logging
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings  # 👈 settings のインポート漏れを解消
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.models.users import User
from app.infrastructure.security.pass_hash import verify_password
from app.infrastructure.security.jwt import create_access_token

# ロガーの初期化
logger = logging.getLogger("datacore.auth")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    username: str

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    client_ip = request.client.host if request.client else "unknown"
    
    stmt = select(User).where(User.username == body.username, User.is_active == True)
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user or not verify_password(body.password, user.hashed_password):
        logger.warning(
            f"[AUTH FAILURE] Failed login attempt for username='{body.username}' from IP={client_ip}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません。"
        )

    token_data = {
        "sub": str(user.id),
        "username": user.username
    }
    access_token = create_access_token(data=token_data)

    logger.info(
        f"[AUTH SUCCESS] User '{user.username}' (ID: {user.id}) successfully logged in from IP={client_ip}"
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=str(user.id),
        username=user.username
    )

# 💡 完全にインデントのズレを解消し、トップレベル関数として配置
async def get_current_user_id(authorization: str = Header(..., description="Bearer <JWT_TOKEN>")) -> str:
    """
    リクエストヘッダーから Authorization: Bearer <JWT> を受け取り、
    署名と期限を検証して、安全にデコードされたユーザーID(sub)を返却するガードレール。
    """
    try:
        token_type, token = authorization.split(" ")
        if token_type.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Bearer token required."
            )
            
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload invalid: missing sub."
            )
        return user_id

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError) as e:
        logger.warning(f"[SECURITY ALERT] Invalid or expired JWT token submission blocked: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンが無効、または期限切れです。再度ログインしてください。"
        )

