
"""
家庭記帳系統：登入身分驗證依賴

功能：
1. 取得 HTTP Bearer Token。
2. 驗證 JWT Access Token。
3. 取得登入者 ID。
4. 檢查 Token 是否已撤銷。
5. 查詢資料庫中的使用者。
6. 確認帳號仍然啟用。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.revoked_token import RevokedToken
from app.security import decode_access_token


# =========================================================
# HTTP Bearer Token 設定
# =========================================================

bearer_scheme = HTTPBearer(
    auto_error=False,
)


# =========================================================
# 取得目前登入使用者
# =========================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    """驗證 JWT 並取得目前登入使用者。"""

    unauthorized_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登入已失效，請重新登入",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # -----------------------------------------------------
    # 1. 確認 Bearer Token 存在
    # -----------------------------------------------------

    if credentials is None:
        raise unauthorized_exception

    if credentials.scheme.lower() != "bearer":
        raise unauthorized_exception

    token = credentials.credentials

    # -----------------------------------------------------
    # 2. 驗證 JWT
    # -----------------------------------------------------

    try:
        payload = decode_access_token(token)

        user_id = int(payload["sub"])
        jti = payload["jti"]

        if user_id <= 0:
            raise ValueError("Invalid user ID")

        if not isinstance(jti, str) or not jti.strip():
            raise ValueError("Invalid token ID")

    except Exception:
        raise unauthorized_exception

    # -----------------------------------------------------
    # 3. 檢查 Token 是否已撤銷
    # -----------------------------------------------------

    revoked_token = (
        db.query(RevokedToken)
        .filter(RevokedToken.jti == jti)
        .first()
    )

    if revoked_token is not None:
        raise unauthorized_exception

    # -----------------------------------------------------
    # 4. 查詢使用者
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise unauthorized_exception

    # -----------------------------------------------------
    # 5. 確認帳號啟用狀態
    # -----------------------------------------------------

    if not user.is_active:
        raise unauthorized_exception

    return user
