from datetime import datetime
from decimal import Decimal
import re

from pydantic import BaseModel, Field, field_validator


class EInvoicePaymentInput(BaseModel):
    account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    payment_date: datetime
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=10)
    description: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("description", "note")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        return value.strip() or None


class EInvoicePostingCreate(BaseModel):
    # An empty payment list records the approved purchase obligation without changing an account balance.
    payments: list[EInvoicePaymentInput] = Field(default_factory=list, max_length=20)


class EInvoicePaymentsAdd(BaseModel):
    payments: list[EInvoicePaymentInput] = Field(min_length=1, max_length=20)
