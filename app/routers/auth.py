
"""
家庭記帳系統：使用者認證 API

功能：
1. 使用者註冊
2. Email 重複檢查
3. Argon2id 密碼雜湊
4. Email + 密碼登入
5. Google 登入
6. 簽發 JWT Access Token
7. 查詢目前登入者資料
8. 撤銷目前登入 Token（登出）
9. 忘記密碼申請
10. 重設使用者密碼
11. 綁定 Google 帳號
12. 查詢已綁定登入方式
13. 解除 Google 帳號綁定

安全原則：
- 不回傳密碼或密碼雜湊。
- 不回傳原始密碼重設 Token。
- 不透露 Email 是否已註冊。
- 密碼重設成功後，使舊登入 Token 失效。
- Google 專用帳號沒有密碼時，不允許使用密碼登入。
- 不因 Email 相同而自動合併不同登入身分。
- Google 使用 sub 作為外部身分唯一識別碼。
- 不允許同一個 Google 身分綁定不同系統使用者。
- 不允許解除帳號最後一種可用登入方式。
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

from app.models import (
    User,
    UserIdentity,
    RevokedToken,
    PasswordResetToken,
)

from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserPublic,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

from app.schemas.google_auth import (
    GoogleLoginRequest,
    GoogleLinkRequest,
    IdentityItem,
    IdentityListResponse,
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

from app.services.google_oauth import (
    verify_google_id_token,
    GoogleOAuthError,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def create_user_token(user: User) -> TokenResponse:
    """
    為指定使用者簽發 JWT Access Token。
    """

    access_token = create_access_token(
        subject=user.id,
        token_version=user.token_version,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def verify_google_token_or_raise(id_token: str) -> dict:
    """
    驗證 Google ID Token。

    此函式只負責呼叫既有 Google OAuth Service，
    不會記錄或回傳原始 ID Token。
    """

    try:
        return verify_google_id_token(id_token)

    except RuntimeError:
        logger.error(
            "Google OAuth 尚未完成環境設定"
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google 登入服務尚未完成設定",
        )

    except GoogleOAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 身分驗證失敗",
            headers={"WWW-Authenticate": "Bearer"},
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

    # Google 專用帳號沒有密碼，
    # 不允許使用 Email + 密碼登入。
    if (
        user is None
        or user.password_hash is None
        or not verify_password(
            data.password,
            user.password_hash,
        )
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

    return create_user_token(user)


@router.post(
    "/google",
    response_model=TokenResponse,
)
def google_login(
    data: GoogleLoginRequest,
    db: Session = Depends(get_db),
):
    """
    使用 Google ID Token 登入。

    流程：
    1. 驗證 Google ID Token。
    2. 使用 Google sub 查詢既有外部身分。
    3. 已綁定者直接登入。
    4. 未綁定且 Email 尚未註冊者，建立新系統帳號。
    5. 若 Email 已有帳號，不自動合併。
    6. 簽發本系統 JWT。
    """

    # 第一步：驗證 Google 身分
    google_user = verify_google_token_or_raise(
        data.id_token
    )

    google_sub = google_user["sub"]
    google_email = normalize_email(
        google_user["email"]
    )

    # 第二步：透過 Google sub 查詢外部身分
    identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == "google",
            UserIdentity.provider_subject == google_sub,
        )
    ).scalar_one_or_none()

    if identity is not None:

        # 已綁定的 Google 身分
        user = db.get(
            User,
            identity.user_id,
        )

        if user is None:
            logger.error(
                "Google 身分資料找不到對應使用者"
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google 登入帳號無效",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此帳號已停用",
            )

        return create_user_token(user)

    # 第三步：Google 身分尚未綁定
    # 檢查 Email 是否已有系統帳號
    existing_user = db.execute(
        select(User).where(
            User.email == google_email
        )
    ).scalar_one_or_none()

    if existing_user is not None:

        # 不可只因 Email 相同就自動合併。
        # 必須先登入既有帳號，再執行 Google 綁定流程。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "此 Email 已有系統帳號。"
                "請先使用原本的登入方式登入，"
                "再進行 Google 帳號綁定。"
            ),
        )

    # 第四步：首次 Google 登入
    # 建立 Google 專用系統帳號
    new_user = User(
        email=google_email,
        password_hash=None,
        display_name=google_user.get("name") or google_email,
        is_active=True,
        token_version=0,
    )

    try:
        db.add(new_user)
        db.flush()

        # 建立 Google 外部身分
        identity = UserIdentity(
            user_id=new_user.id,
            provider="google",
            provider_subject=google_sub,
            email=google_email,
        )

        db.add(identity)

        db.commit()
        db.refresh(new_user)

    except IntegrityError:
        db.rollback()

        logger.warning(
            "Google 帳號建立時發生唯一性衝突"
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google 帳號建立發生衝突，請重新登入",
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Google 使用者建立失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google 登入目前無法完成",
        )

    # 第五步：簽發本系統 JWT
    return create_user_token(new_user)


@router.post(
    "/google/link",
    status_code=status.HTTP_200_OK,
)
def link_google_account(
    data: GoogleLinkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    將 Google 帳號綁定到目前登入的系統帳號。

    安全原則：
    1. 必須先登入目前系統帳號。
    2. 必須重新驗證 Google ID Token。
    3. 使用 Google sub 判斷唯一身分。
    4. 不因 Email 相同而自動合併帳號。
    5. 不允許 Google 身分綁定其他使用者。
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用",
        )

    # 第一步：驗證 Google 身分
    google_user = verify_google_token_or_raise(
        data.id_token
    )

    google_sub = google_user["sub"]
    google_email = normalize_email(
        google_user["email"]
    )

    # 第二步：檢查 Google 身分是否已存在
    existing_identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == "google",
            UserIdentity.provider_subject == google_sub,
        )
    ).scalar_one_or_none()

    if existing_identity is not None:

        # 同一個使用者已經綁定過
        if existing_identity.user_id == current_user.id:
            return {
                "success": True,
                "message": "此 Google 帳號已經綁定",
                "provider": "google",
                "email": existing_identity.email,
            }

        # Google 身分已被其他系統帳號使用
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 Google 帳號已綁定其他系統帳號",
        )

    # 第三步：建立 Google 外部身分
    # 使用 current_user.id，不接受前端傳入 user_id。
    identity = UserIdentity(
        user_id=current_user.id,
        provider="google",
        provider_subject=google_sub,
        email=google_email,
    )

    try:
        db.add(identity)
        db.commit()
        db.refresh(identity)

    except IntegrityError:
        db.rollback()

        logger.warning(
            "Google 帳號綁定發生唯一性衝突"
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 Google 帳號可能已被其他帳號綁定，請重新查詢",
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Google 帳號綁定失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google 帳號綁定目前無法完成",
        )

    return {
        "success": True,
        "message": "Google 帳號綁定成功",
        "provider": "google",
        "email": google_email,
    }



@router.post(
    "/google/recover",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def recover_existing_account_with_google(
    data: GoogleLoginRequest,
    db: Session = Depends(get_db),
):
    """
    使用已由 Google 驗證的相同 Email，恢復既有系統帳號並綁定 Google。

    必須同時符合：
    1. Google ID Token 簽章、audience、issuer、期限均有效。
    2. Google 回報 email_verified=True。
    3. Google 驗證 Email 與既有帳號 Email 正規化後完全相同。
    4. Google sub 尚未綁定其他系統帳號。
    5. 既有系統帳號有效。

    不接受前端提供 user_id 或 email；只使用 Google Token 可信任資料。
    """
    google_user = verify_google_token_or_raise(data.id_token)
    google_sub = google_user["sub"]
    google_email = normalize_email(google_user["email"])

    identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == "google",
            UserIdentity.provider_subject == google_sub,
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此 Google 身分目前無法用於帳號復原",
            )
        # 已經綁定的身分只能登入原本綁定的帳號，不能改綁。
        if normalize_email(user.email) != google_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 Google 帳號已綁定其他系統帳號，無法用於復原目前 Email",
            )
        return create_user_token(user)

    existing_user = db.execute(
        select(User).where(User.email == google_email)
    ).scalar_one_or_none()

    if existing_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到相同 Email 的既有帳號，請使用一般 Google 登入或聯絡管理員",
        )

    if not existing_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此系統帳號已停用，無法復原",
        )

    new_identity = UserIdentity(
        user_id=existing_user.id,
        provider="google",
        provider_subject=google_sub,
        email=google_email,
    )

    try:
        db.add(new_identity)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google 身分已被其他帳號使用，請使用原登入方式或聯絡管理員",
        )
    except Exception:
        db.rollback()
        logger.exception("Google 帳號復原綁定失敗")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="目前無法完成 Google 帳號復原，請稍後再試",
        )

    return create_user_token(existing_user)


@router.get(
    "/identities",
    response_model=IdentityListResponse,
)
def get_my_identities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢目前登入者已綁定的登入方式。

    只回傳目前登入者自己的外部登入身分。
    不回傳 provider_subject 或其他敏感識別資料。
    """

    identities = db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == current_user.id
        ).order_by(UserIdentity.created_at.asc())
    ).scalars().all()

    identity_items = [
        IdentityItem(
            provider=identity.provider,
            email=identity.email,
        )
        for identity in identities
    ]

    return IdentityListResponse(
        success=True,
        total=len(identity_items),
        identities=identity_items,
        has_password=current_user.password_hash is not None,
    )


@router.delete(
    "/google/link",
    status_code=status.HTTP_200_OK,
)
def unlink_google_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    解除目前登入者的 Google 帳號綁定。

    安全原則：
    1. 只能解除自己的 Google 身分。
    2. 如果沒有密碼且 Google 是唯一登入方式，不允許解除。
    3. 不刪除系統使用者帳號。
    """

    # 查詢目前使用者的 Google 身分
    google_identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == current_user.id,
            UserIdentity.provider == "google",
        )
    ).scalar_one_or_none()

    if google_identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目前帳號尚未綁定 Google",
        )

    # 查詢目前使用者所有外部登入身分
    all_identities = db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == current_user.id
        )
    ).scalars().all()

    has_password = current_user.password_hash is not None

    # 如果沒有密碼，而且 Google 是唯一外部登入方式，
    # 就不能解除，避免使用者失去所有登入方式。
    if not has_password and len(all_identities) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "目前帳號沒有設定密碼，"
                "且 Google 是唯一登入方式。"
                "請先建立其他登入方式，再解除 Google 綁定。"
            ),
        )

    try:
        db.delete(google_identity)
        db.commit()

    except Exception:
        db.rollback()

        logger.exception(
            "解除 Google 帳號綁定失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="目前無法解除 Google 帳號綁定",
        )

    return {
        "success": True,
        "message": "Google 帳號已成功解除綁定",
        "provider": "google",
    }


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
    """
    申請密碼重設並寄送 Email。

    安全原則：
    - 不透露 Email 是否已註冊。
    - 不回傳原始重設 Token。
    - 寄送失敗時作廢剛建立的 Token。
    """

    # 確認 SMTP 設定完整
    try:
        get_smtp_settings()

    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="密碼重設郵件服務尚未完成設定，請稍後再試",
        )

    email = normalize_email(str(data.email))

    user = db.execute(
        select(User).where(
            User.email == email,
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if user is None:
        return {
            "message": (
                "如果此 Email 已註冊且可以使用，"
                "系統將寄送密碼重設指示"
            )
        }

    raw_token = None
    token_hash = None

    # 建立密碼重設 Token
    try:
        raw_token = create_password_reset_token(
            db=db,
            user_id=user.id,
        )

        token_hash = hash_reset_token(raw_token)

        db.commit()

    except Exception:
        db.rollback()

        logger.exception(
            "建立密碼重設 Token 失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="目前無法處理密碼重設申請",
        )

    # 寄送密碼重設 Email
    try:
        send_password_reset_email(
            to_email=user.email,
            raw_token=raw_token,
        )

    except Exception:
        logger.exception(
            "密碼重設 Email 寄送失敗"
        )

        # 寄送失敗時，讓剛建立的 Token 立即失效
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

            logger.exception(
                "作廢失敗的密碼重設 Token 時發生錯誤"
            )

        return {
            "message": (
                "如果此 Email 已註冊且可以使用，"
                "系統將寄送密碼重設指示"
            )
        }

    return {
        "message": (
            "如果此 Email 已註冊且可以使用，"
            "系統將寄送密碼重設指示"
        )
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
