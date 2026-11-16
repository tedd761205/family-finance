
"""
家庭記帳系統：Google OAuth 身分驗證服務

功能：
1. 驗證 Google ID Token
2. 驗證 Token 簽章
3. 驗證 Token 有效期限
4. 驗證 Google Client ID（Audience）
5. 驗證 Google Token 簽發者
6. 確認 Google Email 已驗證
7. 回傳可信任的 Google 使用者資料

注意：
- 不接受前端直接提供的 Email 作為登入依據。
- 使用 Google 的 sub 作為唯一外部身分識別碼。
- 不在此服務中建立或合併系統使用者。
"""

import os
import logging

from google.auth.transport import requests
from google.oauth2 import id_token


logger = logging.getLogger(__name__)


class GoogleOAuthError(Exception):
    """Google OAuth 驗證錯誤。"""


def get_google_client_id() -> str:
    """
    取得 Google OAuth Client ID。

    從環境變數 GOOGLE_CLIENT_ID 讀取。
    """

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()

    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID 尚未設定"
        )

    return client_id


def verify_google_id_token(raw_token: str) -> dict:
    """
    驗證 Google ID Token。

    Args:
        raw_token:
            前端取得的 Google ID Token。

    Returns:
        dict:
            {
                "sub": Google 唯一使用者識別碼,
                "email": 已驗證的 Email,
                "email_verified": True,
                "name": Google 顯示名稱,
                "picture": Google 頭像網址
            }

    Raises:
        GoogleOAuthError:
            Token 無效或驗證失敗。
    """

    if not isinstance(raw_token, str) or not raw_token.strip():
        raise GoogleOAuthError(
            "Google ID Token 不可為空"
        )

    client_id = get_google_client_id()

    try:
        request = requests.Request()

        payload = id_token.verify_oauth2_token(
            raw_token,
            request,
            audience=client_id,
        )

    except Exception as exc:
        logger.warning(
            "Google ID Token 驗證失敗：%s",
            type(exc).__name__,
        )

        raise GoogleOAuthError(
            "Google 登入驗證失敗"
        ) from exc

    # 確認 Token 簽發者
    issuer = payload.get("iss")

    if issuer not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise GoogleOAuthError(
            "Google Token 簽發者不正確"
        )

    # Google sub 是穩定且唯一的外部使用者識別碼
    subject = payload.get("sub")

    if not isinstance(subject, str) or not subject.strip():
        raise GoogleOAuthError(
            "Google 使用者識別碼無效"
        )

    # 必須確認 Email 已由 Google 驗證
    email = payload.get("email")

    email_verified = payload.get("email_verified")

    if email_verified is not True:
        raise GoogleOAuthError(
            "Google Email 尚未完成驗證"
        )

    if not isinstance(email, str) or not email.strip():
        raise GoogleOAuthError(
            "Google Email 無效"
        )

    # 顯示名稱為選填，若沒有則使用 Email 前綴
    name = payload.get("name")

    if not isinstance(name, str) or not name.strip():
        name = email.split("@")[0]

    picture = payload.get("picture")

    if not isinstance(picture, str):
        picture = None

    return {
        "sub": subject,
        "email": email.strip().lower(),
        "email_verified": True,
        "name": name.strip(),
        "picture": picture,
    }
