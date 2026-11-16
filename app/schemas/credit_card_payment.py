
from datetime import datetime
from decimal import Decimal
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class CreditCardPaymentBase(BaseModel):
    """信用卡繳款共用欄位"""

    amount: Decimal = Field(
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    currency_code: str = Field(
        min_length=3,
        max_length=3,
    )

    payment_date: datetime

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    note: str | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("幣別代碼必須為三個英文字母")

        return value

    @field_validator("description", "note")
    @classmethod
    def strip_optional_strings(cls, value):
        if value is None:
            return None

        value = value.strip()

        return value or None


class CreditCardPaymentCreate(CreditCardPaymentBase):
    """新增信用卡繳款"""

    from_account_id: int = Field(gt=0)

    credit_card_account_id: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_different_accounts(self):
        if self.from_account_id == self.credit_card_account_id:
            raise ValueError("來源帳戶不可與信用卡帳戶相同")

        return self


class CreditCardPaymentUpdate(BaseModel):
    """修改信用卡繳款"""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=4,
    )

    payment_date: datetime | None = None

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    note: str | None = None

    @field_validator("description", "note")
    @classmethod
    def strip_optional_strings(cls, value):
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_required_fields_not_null(self):
        required_fields = [
            "amount",
            "payment_date",
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


class CreditCardPaymentResponse(CreditCardPaymentBase):
    """信用卡繳款回傳資料"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int

    from_account_id: int
    credit_card_account_id: int

    is_voided: bool
    voided_at: datetime | None = None

    created_by: int
    created_at: datetime
    updated_at: datetime
