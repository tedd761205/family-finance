
"""
家庭記帳系統：Google 登入資料結構

負責：
1. 接收前端傳入的 Google ID Token
2. 驗證 Token 欄位格式
3. 限制 Token 長度

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
