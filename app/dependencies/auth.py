
"""
家庭記帳系統：登入身分驗證依賴

功能：
1. 取得 HTTP Bearer Token。
2. 驗證 JWT Access Token。
3. 取得登入者 ID。
4. 查詢資料庫中的使用者。
5. 確認帳號仍然啟用。

注意：
所有需要登入的 API，
都必須使用 Depends(get_current_user)。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.security import decode_access_token


# =========================================================
# OAuth2 Bearer Token 設定
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


# =========================================================
# 取得目前登入使用者
# =========================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    驗證 JWT 並取得目前登入使用者。

    驗證失敗：
    - Token 無效
    - Token 已過期
    - Token 類型錯誤
    - 使用者不存在
    - 使用者帳號已停用
    """

    unauthorized_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登入已失效，請重新登入",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # -----------------------------------------------------
    # 1. 驗證 JWT
    # -----------------------------------------------------

    try:
        payload = decode_access_token(token)

        user_id = int(payload["sub"])

        if user_id <= 0:
            raise ValueError("Invalid user ID")

    except Exception:
        raise unauthorized_exception

    # -----------------------------------------------------
    # 2. 查詢使用者
    # -----------------------------------------------------

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise unauthorized_exception

    # -----------------------------------------------------
    # 3. 確認帳號啟用狀態
    # -----------------------------------------------------

    if not user.is_active:
        raise unauthorized_exception

    return user
