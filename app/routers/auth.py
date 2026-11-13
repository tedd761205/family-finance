
"""
家庭記帳系統：使用者註冊、登入及個人資料 API

功能：
1. 使用者註冊
2. Email 重複檢查
3. Argon2id 密碼雜湊
4. 使用者登入
5. 簽發 JWT Access Token
6. 查詢目前登入者資料
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
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

    access_token = create_access_token(
        subject=user.id,
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
