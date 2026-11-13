
"""
家庭記帳系統：安全與驗證工具

功能：
1. 使用 Argon2id 雜湊及驗證密碼。
2. 電子郵件格式驗證與標準化。
3. 建立及驗證 JWT Access Token。

注意：
- 不儲存明文密碼。
- JWT Secret 從環境變數讀取，不寫死在程式碼。
- Access Token 預設有效期限為 20 分鐘。
- 本模組尚未實作伺服器端 Token 撤銷機制。
"""

import os
import secrets

from datetime import datetime, timedelta, timezone

import jwt

from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash


# =========================================================
# 密碼安全
# =========================================================

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    將明文密碼轉換成安全雜湊。

    回傳：
        Argon2id password hash
    """

    if not isinstance(password, str) or not password:
        raise ValueError("密碼不可為空")

    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    驗證使用者輸入的密碼是否正確。
    """

    if not isinstance(password, str) or not password:
        return False

    if not isinstance(hashed_password, str) or not hashed_password:
        return False

    try:
        return password_hasher.verify(password, hashed_password)
    except Exception:
        return False


# =========================================================
# 電子郵件驗證
# =========================================================

def normalize_email(email: str) -> str:
    """
    驗證電子郵件格式並統一為小寫。

    不進行實際寄信或信箱存在性驗證。
    """

    if not isinstance(email, str):
        raise ValueError("電子郵件格式不正確")

    email = email.strip().lower()

    if not email:
        raise ValueError("電子郵件不可為空")

    try:
        result = validate_email(
            email,
            check_deliverability=False,
        )

        return result.normalized.lower()

    except EmailNotValidError as exc:
        raise ValueError(f"電子郵件格式錯誤：{exc}") from exc


# =========================================================
# JWT 設定
# =========================================================

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 20


def _get_jwt_secret() -> str:
    """
    從環境變數取得 JWT 金鑰。

    優先使用 JWT_SECRET_KEY；
    若尚未設定，暫時使用既有 SECRET_KEY。

    不在模組載入時讀取，避免影響 GitHub Actions
    的程式匯入及語法驗證。
    """

    secret = (
        os.getenv("JWT_SECRET_KEY")
        or os.getenv("SECRET_KEY")
    )

    if not secret:
        raise RuntimeError(
            "尚未設定 JWT_SECRET_KEY 或 SECRET_KEY 環境變數"
        )

    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT Secret 長度不足，至少需要 32 bytes"
        )

    return secret


# =========================================================
# 建立 Access Token
# =========================================================

def create_access_token(
    subject: int | str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    建立 JWT Access Token。

    Payload 包含：
    - sub：使用者 ID
    - iat：簽發時間
    - exp：到期時間
    - jti：Token 唯一識別碼
    - type：Token 類型
    """

    if subject is None or not str(subject).strip():
        raise ValueError("使用者 ID 不可為空")

    if expires_delta is None:
        expires_delta = timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    if expires_delta <= timedelta(0):
        raise ValueError("Token 有效期限必須大於零")

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "type": "access",
    }

    token = jwt.encode(
        payload,
        _get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )

    return token


# =========================================================
# 驗證 Access Token
# =========================================================

def decode_access_token(token: str) -> dict:
    """
    驗證 JWT Access Token。

    驗證項目：
    1. 簽章是否正確。
    2. Token 是否過期。
    3. 必要欄位是否存在。
    4. Token 類型是否為 access。

    驗證失敗會拋出例外，
    後續由 FastAPI 認證層統一處理。
    """

    if not isinstance(token, str) or not token.strip():
        raise ValueError("Token 不可為空")

    payload = jwt.decode(
        token,
        _get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "iat",
                "exp",
                "jti",
                "type",
            ]
        },
    )

    if payload.get("type") != "access":
        raise ValueError("Token 類型不正確")

    if not isinstance(payload.get("sub"), str):
        raise ValueError("Token 使用者識別資料不正確")

    if not payload["sub"].strip():
        raise ValueError("Token 使用者識別資料不可為空")

    if not isinstance(payload.get("jti"), str):
        raise ValueError("Token 識別碼不正確")

    return payload
