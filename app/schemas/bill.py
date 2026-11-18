from datetime import date, datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BillCreate(BaseModel):
    bill_number: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    category_id: int | None = Field(default=None, gt=0)
    bill_date: date
    billing_period_start: date | None = None
    billing_period_end: date | None = None
    due_date: date | None = None
    original_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    currency_code: str = Field(default="TWD", min_length=3, max_length=3)
    note: str | None = None

    @field_validator("bill_number", "title", "note")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("title")
    @classmethod
    def require_title(cls, value):
        if not value:
            raise ValueError("帳單名稱不可空白")
        return value

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @model_validator(mode="after")
    def validate_amounts_and_period(self):
        if self.original_amount + self.tax_amount - self.discount_amount < 0:
            raise ValueError("折扣金額不可大於原始金額加稅額")
        if (
            self.billing_period_start is not None
            and self.billing_period_end is not None
            and self.billing_period_start > self.billing_period_end
        ):
            raise ValueError("帳單期間起日不可晚於迄日")
        if (self.billing_period_start is None) != (self.billing_period_end is None):
            raise ValueError("帳單期間起日與迄日必須同時提供")
        return self


class BillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bill_number: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = Field(default=None, gt=0)
    bill_date: date | None = None
    billing_period_start: date | None = None
    billing_period_end: date | None = None
    due_date: date | None = None
    original_amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    discount_amount: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    note: str | None = None

    @field_validator("bill_number", "title", "note")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value):
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        for field_name in (
            "title", "bill_date", "original_amount", "tax_amount",
            "discount_amount", "currency_code",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不可為 null")
        if not self.model_fields_set:
            raise ValueError("沒有提供任何修改內容")
        return self


class BillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    bill_number: str | None
    title: str
    category_id: int | None
    bill_date: date
    billing_period_start: date | None
    billing_period_end: date | None
    due_date: date | None
    original_amount: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    currency_code: str
    status: str
    note: str | None
    is_voided: bool
    voided_at: datetime | None
    voided_by: int | None
    void_reason: str | None
    created_by: int
    updated_by: int | None
    created_at: datetime
    updated_at: datetime


class BillListResponse(BaseModel):
    success: bool
    total: int
    skip: int
    limit: int
    bills: list[BillResponse]


class BillMessageResponse(BaseModel):
    success: bool
    message: str
    bill: BillResponse
