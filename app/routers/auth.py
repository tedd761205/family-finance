
"""
家庭記帳系統：使用者註冊、登入、登出及個人資料 API

功能：
1. 使用者註冊
2. Email 重複檢查
3. Argon2id 密碼雜湊
4. 使用者登入
5. 簽發含 Token 版本的 JWT Access Token
6. 查詢目前登入者資料
7. 撤銷目前登入 Token（登出）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user, bearer_scheme
from app.models.user import User
from app.models.revoked_token import RevokedToken
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserPublic,
    TokenResponse,
)
from app.security import (
    normalize_email,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =========================================================
# 使用者註冊
# =========================================================

@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """建立新的使用者帳號。"""

    try:
        email = normalize_email(str(data.email))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="電子郵件格式不正確",
        )

    display_name = data.display_name.strip()

    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="顯示名稱不可為空",
        )

    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此電子郵件已經註冊",
        )

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        display_name=display_name,
        is_active=True,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此電子郵件已經註冊",
        )

    except Exception:
        db.rollback()
        raise

    return user


# =========================================================
# 使用者登入
# =========================================================

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """驗證使用者帳號密碼並簽發 JWT。"""

    try:
        email = normalize_email(str(data.email))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="電子郵件或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="電子郵件或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="電子郵件或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號目前已停用",
        )

    # 使用資料庫目前的 Token 版本簽發 JWT
    access_token = create_access_token(
        subject=user.id,
        token_version=user.token_version,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# =========================================================
# 取得目前登入者資料
# =========================================================

@router.get(
    "/me",
    response_model=UserPublic,
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """取得目前登入使用者的公開資料。"""

    return current_user


# =========================================================
# 使用者登出
# =========================================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
def logout_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤銷目前登入中的 JWT Access Token。"""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已失效，請重新登入",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # 取得已通過驗證的 JWT 資料
        payload = decode_access_token(
            credentials.credentials
        )

        jti = payload["jti"]

        expires_at = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.utc,
        )

        # 建立 Token 撤銷紀錄
        revoked_token = RevokedToken(
            jti=jti,
            user_id=current_user.id,
            expires_at=expires_at,
        )

        db.add(revoked_token)
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已失效，請重新登入",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except Exception:
        db.rollback()
        raise

    return {
        "message": "已成功登出"
    }
