
"""
家庭記帳系統：家庭資料結構

負責：
1. 驗證建立家庭的請求資料。
2. 定義家庭建立成功後的回傳格式。
3. 定義使用者家庭清單的回傳格式。

安全原則：
- 不接受前端傳入 user_id。
- 建立者身分由後端 JWT 驗證取得。
- 家庭清單由目前登入者的身分查詢。
"""

from pydantic import BaseModel, ConfigDict, Field


class FamilyCreate(BaseModel):
    """建立家庭請求"""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="家庭名稱",
    )

    currency: str = Field(
        default="TWD",
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
        description="家庭預設幣別，例如 TWD",
    )


class FamilyCreateResponse(BaseModel):
    """建立家庭成功回傳"""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    family_id: int
    family_name: str
    currency: str
    family_member_id: int
    user_id: int
    admin_role_id: int
    admin_role_name: str


class FamilyListItem(BaseModel):
    """使用者加入的單一家庭"""

    family_id: int
    family_name: str
    currency: str
    family_member_id: int
    status: str


class FamilyListResponse(BaseModel):
    """使用者家庭清單回傳"""

    success: bool
    total: int
    families: list[FamilyListItem]
