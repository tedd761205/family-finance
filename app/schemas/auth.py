
"""
家庭記帳系統：認證相關資料結構

負責：
1. 使用者註冊資料驗證
2. 使用者登入資料驗證
3. Access Token 回傳格式
4. 使用者公開資料格式

注意：
不會將 password 或 password_hash 回傳給前端。
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    """使用者註冊請求"""

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    display_name: str = Field(
        min_length=1,
        max_length=100,
    )


class UserLogin(BaseModel):
    """使用者登入請求"""

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class TokenResponse(BaseModel):
    """登入成功後回傳的 Token"""

    access_token: str

    token_type: str = "bearer"

    expires_in: int = 1200


class UserPublic(BaseModel):
    """提供給前端的使用者公開資料"""

    model_config = ConfigDict(from_attributes=True)

    id: int

    email: EmailStr

    display_name: str

    is_active: bool
