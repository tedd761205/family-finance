from datetime import datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BillPaymentCreate(BaseModel):
    bill_id: int = Field(gt=0)
    account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4)
    currency_code: str = Field(min_length=3, max_length=3)
    payment_date: datetime
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)
    description: str | None = Field(default=None, max_length=200)
    note: str | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @field_validator("description", "note")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        return value.strip() or None


class BillRefundCreate(BaseModel):
    account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4)
    currency_code: str = Field(min_length=3, max_length=3)
    payment_date: datetime
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)
    description: str | None = Field(default=None, max_length=200)
    note: str | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")
        return value

    @field_validator("description", "note")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        return value.strip() or None


class BillPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    bill_id: int
    account_id: int
    payment_type: str
    original_payment_id: int | None
    amount: Decimal
    currency_code: str
    account_amount: Decimal
    account_currency_code: str
    exchange_rate: Decimal
    exchange_difference: Decimal
    payment_date: datetime
    description: str | None
    note: str | None
    is_voided: bool
    voided_at: datetime | None
    voided_by: int | None
    void_reason: str | None
    created_by: int
    created_at: datetime


class BillPaymentListResponse(BaseModel):
    success: bool
    total: int
    skip: int
    limit: int
    payments: list[BillPaymentResponse]


class BillPaymentMessageResponse(BaseModel):
    success: bool
    message: str
    payment: BillPaymentResponse
