
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


CategoryType = Literal["income", "expense"]


# =========================================================
# 新增分類
# =========================================================

class CategoryCreate(BaseModel):

    category_type: CategoryType

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    parent_id: int | None = Field(
        default=None,
        gt=0,
    )

    icon: str | None = Field(
        default=None,
        max_length=50,
    )

    color: str | None = Field(
        default=None,
        max_length=20,
    )

    sort_order: int = Field(
        default=0,
        ge=0,
    )

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("分類名稱不可為空白")

        return value


# =========================================================
# 修改分類
# =========================================================

class CategoryUpdate(BaseModel):

    category_type: CategoryType | None = None

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    parent_id: int | None = Field(
        default=None,
        gt=0,
    )

    icon: str | None = Field(
        default=None,
        max_length=50,
    )

    color: str | None = Field(
        default=None,
        max_length=20,
    )

    sort_order: int | None = Field(
        default=None,
        ge=0,
    )

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("分類名稱不可為空白")

        return value

    @model_validator(mode="after")
    def validate_required_fields(self):

        # 只有使用者明確傳入的欄位才檢查
        # 未傳入的欄位允許維持原值

        if (
            "category_type" in self.model_fields_set
            and self.category_type is None
        ):
            raise ValueError("分類類型不可為 null")

        if (
            "name" in self.model_fields_set
            and self.name is None
        ):
            raise ValueError("分類名稱不可為 null")

        if (
            "sort_order" in self.model_fields_set
            and self.sort_order is None
        ):
            raise ValueError("排序不可為 null")

        return self


# =========================================================
# 分類回應
# =========================================================

class CategoryResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    family_id: int | None

    category_type: str
    name: str

    parent_id: int | None

    icon: str | None
    color: str | None

    is_system: bool
    is_active: bool

    sort_order: int

    note: str | None

    created_by: int | None

    created_at: datetime
    updated_at: datetime


# =========================================================
# 分類列表回應
# =========================================================

class CategoryListResponse(BaseModel):

    success: bool
    total: int
    categories: list[CategoryResponse]


# =========================================================
# 分類操作回應
# =========================================================

class CategoryMessageResponse(BaseModel):

    success: bool
    message: str
    category: CategoryResponse
