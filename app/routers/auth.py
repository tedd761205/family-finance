
"""
家庭記帳系統：使用者認證 API

功能：
1. 使用者註冊
2. Email 重複檢查
3. Argon2id 密碼雜湊
4. 使用者登入
5. 簽發 JWT Access Token
6. 查詢目前登入者資料
7. 撤銷目前登入 Token（登出）
8. 忘記密碼申請
9. 重設使用者密碼
"""

import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user, bearer_scheme
from app.models import User, RevokedToken, PasswordResetToken
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserPublic,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.security import (
    normalize_email,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.services.password_reset import (
    create_password_reset_token,
    reset_user_password,
    hash_reset_token,
    get_utc_now,
)
from app.services.email import (
    get_smtp_settings,
    send_password_reset_email,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """註冊新使用者。"""

    email = normalize_email(str(data.email))
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
            detail="此 Email 已經註冊",
        )

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        display_name=display_name,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 Email 已經註冊",
        )

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """使用 Email 和密碼登入。"""

    email = normalize_email(str(data.email))

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user is None or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email 或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用",
        )

    access_token = create_access_token(
        subject=user.id,
        token_version=user.token_version,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserPublic,
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """取得目前登入者的個人資料。"""

    return current_user


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤銷目前使用中的 Access Token。"""

    try:
        payload = decode_access_token(
            credentials.credentials
        )

        expires_at = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.utc,
        )

        revoked_token = RevokedToken(
            user_id=current_user.id,
            jti=payload["jti"],
            expires_at=expires_at,
        )

        db.add(revoked_token)
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已失效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except Exception:
        db.rollback()
        raise

    return {
        "message": "已成功登出"
    }


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """申請密碼重設並寄送 Email。"""

    # 先檢查 SMTP 設定，避免帳號是否存在影響回應
    try:
        get_smtp_settings()

    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="密碼重設郵件服務尚未設定，請稍後再試",
        )

    email = normalize_email(str(data.email))

    user = db.execute(
        select(User).where(
            User.email == email,
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()

    # 不存在或已停用的帳號不執行任何動作
    if user is None:
        return {
            "message": "如果此 Email 已註冊且可以使用，系統將寄送密碼重設指示"
        }

    raw_token = None
    token_hash = None

    try:
        raw_token = create_password_reset_token(
            db=db,
            user_id=user.id,
        )

        token_hash = hash_reset_token(raw_token)

        # 先儲存 Token，確保寄出的連結可以被驗證
        db.commit()

    except Exception:
        db.rollback()
        logger.exception("建立密碼重設 Token 失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="目前無法處理密碼重設申請",
        )

    try:
        send_password_reset_email(
            to_email=user.email,
            raw_token=raw_token,
        )

    except Exception:
        logger.exception("密碼重設 Email 寄送失敗")

        # 寄送失敗時，立即讓剛建立的 Token 失效
        try:
            reset_token = db.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.used_at.is_(None),
                )
            ).scalar_one_or_none()

            if reset_token is not None:
                reset_token.used_at = get_utc_now()
                db.commit()

        except Exception:
            db.rollback()
            logger.exception("作廢失敗的密碼重設 Token 時發生錯誤")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="目前無法寄送密碼重設郵件，請稍後再試",
        )

    return {
        "message": "如果此 Email 已註冊且可以使用，系統將寄送密碼重設指示"
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """使用密碼重設 Token 更新密碼。"""

    try:
        success = reset_user_password(
            db=db,
            raw_token=data.token,
            new_password=data.new_password,
        )

        if not success:
            db.rollback()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密碼重設連結無效、已使用或已過期",
            )

        db.commit()

    except HTTPException:
        raise

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except Exception:
        db.rollback()
        raise

    return {
        "message": "密碼已成功重設，請使用新密碼重新登入"
    }
