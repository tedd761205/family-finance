
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TransactionType(str, Enum):
    """交易類型"""

    INCOME = "income"
    EXPENSE = "expense"
    OPENING_BALANCE = "opening_balance"


class TransactionBase(BaseModel):
    """交易共用欄位"""

    transaction_type: TransactionType

    amount: Decimal = Field(
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    currency_code: str = Field(
        min_length=3,
        max_length=3,
    )

    transaction_date: datetime

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    category_id: int | None = Field(
        default=None,
        gt=0,
    )

    external_reference: str | None = Field(
        default=None,
        max_length=100,
    )

    note: str | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")

        return value

    @field_validator("description", "external_reference", "note")
    @classmethod
    def strip_optional_strings(cls, value):
        if value is None:
            return None

        value = value.strip()

        return value or None


class TransactionCreate(TransactionBase):
    """新增交易"""

    account_id: int = Field(gt=0)


class TransactionUpdate(BaseModel):
    """修改交易"""

    model_config = ConfigDict(extra="forbid")

    transaction_type: TransactionType | None = None

    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    transaction_date: datetime | None = None

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    category_id: int | None = Field(
        default=None,
        gt=0,
    )

    external_reference: str | None = Field(
        default=None,
        max_length=100,
    )

    note: str | None = None

    @field_validator("description", "external_reference", "note")
    @classmethod
    def strip_optional_strings(cls, value):
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_required_fields_not_null(self):
        required_fields = [
            "transaction_type",
            "amount",
            "transaction_date",
        ]

        for field_name in required_fields:
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(
                    f"{field_name} 不可為 null"
                )

        return self


class TransactionResponse(TransactionBase):
    """交易回傳資料"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    account_id: int

    transfer_id: int | None = None
    related_transaction_id: int | None = None

    # 信用卡繳款主檔 ID
    credit_card_payment_id: int | None = None

    is_voided: bool
    voided_at: datetime | None = None

    created_by: int
    created_at: datetime
    updated_at: datetime
