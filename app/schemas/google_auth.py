
"""
家庭記帳系統：Google 登入資料結構

負責：
1. 接收前端傳入的 Google ID Token
2. 驗證 Token 欄位格式
3. 限制 Token 長度
4. 定義外部登入身分清單回傳格式

注意：
真正的 Google Token 簽章及身分驗證，
由 app.services.google_oauth 負責。
"""

from pydantic import BaseModel, Field


class GoogleLoginRequest(BaseModel):
    """Google 登入請求"""

    id_token: str = Field(
        min_length=1,
        max_length=10000,
        description="Google OAuth ID Token",
    )


class GoogleLinkRequest(BaseModel):
    """綁定 Google 帳號請求"""

    id_token: str = Field(
        min_length=1,
        max_length=10000,
        description="Google OAuth ID Token",
    )


class IdentityItem(BaseModel):
    """已綁定的登入身分"""

    provider: str
    email: str | None = None


class IdentityListResponse(BaseModel):
    """已綁定登入方式清單"""

    success: bool
    total: int
    identities: list[IdentityItem]
    has_password: bool
