
"""
家庭記帳系統：帳戶收支統計 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountReportResponse(BaseModel):
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
