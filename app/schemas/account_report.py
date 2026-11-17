
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int
    account_id: int
    account_name: str
    account_type: str
    currency_code: str

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    opening_balance: Decimal
    current_balance: Decimal

    total_income: Decimal
    total_expense: Decimal
    net_amount: Decimal

    transfer_in_amount: Decimal
    transfer_out_amount: Decimal

    credit_card_payment_in: Decimal
    credit_card_payment_out: Decimal

    credit_card_refund_amount: Decimal

    income_transaction_count: int
    expense_transaction_count: int

    transfer_in_count: int
    transfer_out_count: int

    credit_card_payment_count: int
    credit_card_refund_count: int

    transaction_count: int


class AccountTransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    account_id: int

    transaction_type: str
    amount: Decimal
    currency_code: str
    transaction_date: datetime

    description: Optional[str] = None
    category_id: Optional[int] = None

    transfer_id: Optional[int] = None
    related_transaction_id: Optional[int] = None
    credit_card_payment_id: Optional[int] = None

    external_reference: Optional[str] = None
    note: Optional[str] = None

    is_voided: bool
    voided_at: Optional[datetime] = None

    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AccountTransactionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int
    account_id: int
    account_name: str
    account_type: str
    currency_code: str

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    total_count: int
    page: int
    page_size: int

    transactions: list[AccountTransactionItem]
