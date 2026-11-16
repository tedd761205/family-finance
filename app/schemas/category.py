
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CategoryType = Literal["income", "expense"]


class CategoryCreate(BaseModel):
    """新增家庭分類"""

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


class CategoryUpdate(BaseModel):
    """修改家庭分類"""

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


class CategoryResponse(BaseModel):
    """分類資料回應"""

    model_config = ConfigDict(from_attributes=True)

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


class CategoryListResponse(BaseModel):
    """分類清單回應"""

    success: bool
    total: int
    categories: list[CategoryResponse]


class CategoryMessageResponse(BaseModel):
    """分類操作訊息回應"""

    success: bool
    message: str
    category: CategoryResponse
