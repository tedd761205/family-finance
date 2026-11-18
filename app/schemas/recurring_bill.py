from datetime import date, datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecurringBillCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category_id: int | None = Field(default=None, gt=0)
    frequency: str
    interval_count: int = Field(default=1, ge=1, le=120)
    start_date: date
    end_date: date | None = None
    next_run_date: date | None = None
    due_days_after: int = Field(default=0, ge=0, le=365)
    original_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    currency_code: str = Field(default="TWD", min_length=3, max_length=3)
    note: str | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("定期帳單名稱不可空白")
        return value

    @field_validator("frequency")
    @classmethod
    def valid_frequency(cls, value):
        if value not in {"weekly", "monthly", "yearly"}:
            raise ValueError("週期僅支援 weekly、monthly、yearly")
        return value

    @field_validator("currency_code")
    @classmethod
    def valid_currency(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @model_validator(mode="after")
    def valid_dates_and_amounts(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("結束日期不可早於開始日期")
        if self.original_amount + self.tax_amount - self.discount_amount < 0:
            raise ValueError("折扣金額不可大於原始金額加稅額")
        if self.next_run_date and self.next_run_date < self.start_date:
            raise ValueError("下次產生日期不可早於開始日期")
        return self


class RecurringBillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = Field(default=None, gt=0)
    frequency: str | None = None
    interval_count: int | None = Field(default=None, ge=1, le=120)
    start_date: date | None = None
    end_date: date | None = None
    next_run_date: date | None = None
    due_days_after: int | None = Field(default=None, ge=0, le=365)
    original_amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    discount_amount: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    note: str | None = None

    @field_validator("frequency")
    @classmethod
    def valid_frequency(cls, value):
        if value is not None and value not in {"weekly", "monthly", "yearly"}:
            raise ValueError("週期僅支援 weekly、monthly、yearly")
        return value

    @field_validator("currency_code")
    @classmethod
    def valid_currency(cls, value):
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("沒有提供任何修改內容")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("結束日期不可早於開始日期")
        if self.next_run_date and self.start_date and self.next_run_date < self.start_date:
            raise ValueError("下次產生日期不可早於開始日期")
        return self


class RecurringBillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_id: int
    title: str
    category_id: int | None
    frequency: str
    interval_count: int
    start_date: date
    end_date: date | None
    next_run_date: date
    due_days_after: int
    original_amount: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    currency_code: str
    note: str | None
    is_active: bool
    created_by: int
    updated_by: int | None
    created_at: datetime
    updated_at: datetime


class RecurringBillListResponse(BaseModel):
    success: bool
    total: int
    recurring_bills: list[RecurringBillResponse]


class GenerateResponse(BaseModel):
    success: bool
    generated_count: int
    bill_ids: list[int]
    next_run_date: date | None
