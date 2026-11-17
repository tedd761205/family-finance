
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountReportResponse(BaseModel):
    family_id: int
    account_id: int
    account_name: str
    account_type: str
    currency_code: str

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # 帳戶餘額
    opening_balance: Decimal
    current_balance: Decimal

    # 期間收支
    total_income: Decimal
    total_expense: Decimal
    net_amount: Decimal

    # 期間轉帳
    transfer_in_amount: Decimal
    transfer_out_amount: Decimal

    # 信用卡繳款
    credit_card_payment_in: Decimal
    credit_card_payment_out: Decimal

    # 信用卡退款
    credit_card_refund_amount: Decimal

    # 交易筆數
    income_count: int
    expense_count: int

    transfer_in_count: int
    transfer_out_count: int

    credit_card_payment_count: int
    credit_card_refund_count: int

    transaction_count: int

    model_config = ConfigDict(from_attributes=True)


class AccountTransactionItem(BaseModel):
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

    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountTransactionListResponse(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)
