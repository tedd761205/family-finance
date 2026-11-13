
"""
家庭記帳系統：密碼重設服務

負責：
1. 產生安全的密碼重設 Token
2. 儲存 Token 的 SHA-256 雜湊值
3. 管理 Token 有效期限
4. 讓舊的重設 Token 失效
5. 驗證 Token 並更新使用者密碼
6. 遞增 Token 版本，使舊登入 Token 失效

注意：
- 資料庫不儲存原始 Token。
- 原始 Token 只能交給呼叫端用於寄送重設連結。
- 本服務不負責 commit，由呼叫端管理交易。
"""

import hashlib
import secrets

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import PasswordResetToken, User
from app.security import hash_password


# 密碼重設 Token 有效期限：30 分鐘
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30


def get_utc_now() -> datetime:
    """取得目前 UTC 時間。"""

    return datetime.now(timezone.utc)


def hash_reset_token(token: str) -> str:
    """將原始 Token 轉換為 SHA-256 雜湊值。"""

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def create_password_reset_token(
    db: Session,
    user_id: int,
) -> str:
    """
    建立密碼重設 Token。

    回傳：
        原始 Token，僅供呼叫端建立重設連結及寄送 Email。

    注意：
        資料庫只會儲存 Token 的 SHA-256 雜湊值。
        不在此函式執行 commit。
    """

    now = get_utc_now()

    # 確認使用者存在且啟用
    user = db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if user is None:
        raise ValueError("使用者不存在或帳號已停用")

    # 讓該使用者先前尚未使用的重設 Token 失效
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    # 產生安全隨機 Token
    raw_token = secrets.token_urlsafe(32)

    # 計算 Token 雜湊值
    token_hash = hash_reset_token(raw_token)

    # 設定有效期限
    expires_at = now + timedelta(
        minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )

    reset_token = PasswordResetToken(
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
    )

    db.add(reset_token)

    return raw_token


def reset_user_password(
    db: Session,
    raw_token: str,
    new_password: str,
) -> bool:
    """
    驗證密碼重設 Token 並更新使用者密碼。

    驗證條件：
    1. Token 必須存在。
    2. Token 尚未使用。
    3. Token 尚未過期。
    4. 使用者帳號必須存在且啟用。

    成功：
        更新密碼雜湊值。
        將 Token 標記為已使用。
        遞增使用者 Token 版本，使舊登入 Token 失效。

    失敗：
        回傳 False。

    注意：
        本函式不執行 commit，由呼叫端管理交易。
        呼叫端必須在成功後 commit，發生例外時 rollback。
    """

    # 驗證輸入
    if not isinstance(raw_token, str) or not raw_token.strip():
        return False

    if not isinstance(new_password, str):
        raise ValueError("密碼格式不正確")

    if len(new_password) < 8 or len(new_password) > 128:
        raise ValueError("密碼長度必須介於 8 至 128 個字元")

    now = get_utc_now()

    # 計算收到的 Token 雜湊值
    token_hash = hash_reset_token(raw_token)

    # 鎖定 Token 資料，避免同一 Token 被同時使用
    reset_token = db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if reset_token is None:
        return False

    # 鎖定並確認使用者存在且啟用
    user = db.execute(
        select(User)
        .where(
            User.id == reset_token.user_id,
            User.is_active.is_(True),
        )
        .with_for_update()
    ).scalar_one_or_none()

    if user is None:
        return False

    # 更新密碼雜湊值
    user.password_hash = hash_password(new_password)

    # 標記密碼重設 Token 已使用
    reset_token.used_at = now

    # 遞增 Token 版本，使所有舊登入 JWT 失效
    user.token_version += 1

    return True
