
"""
家庭記帳系統：帳戶收支統計與明細 Schema
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountReportResponse(BaseModel):
    """帳戶收支統計"""

    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(..., gt=0)
    account_id: int = Field(..., gt=0)
    account_name: str
    account_type: str
    currency_code: str = Field(..., min_length=3, max_length=3)

    start_date: str | None = None
    end_date: str | None = None

    total_income: Decimal = Field(default=Decimal("0"))
    total_expense: Decimal = Field(default=Decimal("0"))
    net_amount: Decimal = Field(default=Decimal("0"))

    transfer_in_amount: Decimal = Field(default=Decimal("0"))
    transfer_out_amount: Decimal = Field(default=Decimal("0"))

    credit_card_payment_in: Decimal = Field(default=Decimal("0"))
    credit_card_payment_out: Decimal = Field(default=Decimal("0"))

    credit_card_refund_amount: Decimal = Field(
        default=Decimal("0"),
        description="信用卡退款金額，不列入一般收入",
    )

    income_transaction_count: int = Field(default=0, ge=0)
    expense_transaction_count: int = Field(default=0, ge=0)

    transfer_in_count: int = Field(default=0, ge=0)
    transfer_out_count: int = Field(default=0, ge=0)

    credit_card_payment_count: int = Field(default=0, ge=0)

    credit_card_refund_count: int = Field(
        default=0,
        ge=0,
        description="信用卡退款筆數",
    )

    transaction_count: int = Field(
        default=0,
        ge=0,
        description="統計期間內有效交易筆數，包含特殊交易",
    )


class AccountTransactionItem(BaseModel):
    """單筆帳戶交易明細"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., gt=0)
    family_id: int = Field(..., gt=0)
    account_id: int = Field(..., gt=0)

    transaction_type: str
    amount: Decimal
    currency_code: str = Field(..., min_length=3, max_length=3)

    transaction_date: datetime
    description: str | None = None

    category_id: int | None = None

    transfer_id: int | None = None
    related_transaction_id: int | None = None
    credit_card_payment_id: int | None = None

    external_reference: str | None = None
    note: str | None = None

    is_voided: bool
    voided_at: datetime | None = None

    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class AccountTransactionListResponse(BaseModel):
    """帳戶交易明細列表"""

    family_id: int = Field(..., gt=0)
    account_id: int = Field(..., gt=0)

    account_name: str
    account_type: str
    currency_code: str = Field(..., min_length=3, max_length=3)

    start_date: str | None = None
    end_date: str | None = None

    total_count: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)

    transactions: list[AccountTransactionItem] = Field(
        default_factory=list
    )
