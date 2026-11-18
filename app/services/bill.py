from datetime import date
from decimal import Decimal

from app.models.bill import Bill


def calculate_bill_total(bill: Bill) -> Decimal:
    """帳單應繳總額 = 原始金額 + 稅額 - 折扣。"""
    return bill.original_amount + bill.tax_amount - bill.discount_amount


def get_bill_status(
    bill: Bill,
    paid_amount: Decimal = Decimal("0"),
    as_of: date | None = None,
) -> str:
    """依作廢、付款金額及到期日即時計算帳單狀態。"""
    if bill.is_voided:
        return "voided"

    total = calculate_bill_total(bill)
    if paid_amount >= total:
        return "paid"
    if paid_amount > 0:
        return "partially_paid"

    today = as_of or date.today()
    if bill.due_date is not None and bill.due_date < today:
        return "overdue"
    return "unpaid"


def bill_to_dict(
    bill: Bill,
    paid_amount: Decimal = Decimal("0"),
    as_of: date | None = None,
) -> dict:
    total = calculate_bill_total(bill)
    paid = min(max(paid_amount, Decimal("0")), total)
    return {
        "id": bill.id,
        "family_id": bill.family_id,
        "bill_number": bill.bill_number,
        "title": bill.title,
        "category_id": bill.category_id,
        "bill_date": bill.bill_date,
        "billing_period_start": bill.billing_period_start,
        "billing_period_end": bill.billing_period_end,
        "due_date": bill.due_date,
        "original_amount": bill.original_amount,
        "tax_amount": bill.tax_amount,
        "discount_amount": bill.discount_amount,
        "total_amount": total,
        "paid_amount": paid,
        "remaining_amount": max(total - paid, Decimal("0")),
        "currency_code": bill.currency_code,
        "status": get_bill_status(bill, paid, as_of),
        "note": bill.note,
        "is_voided": bill.is_voided,
        "voided_at": bill.voided_at,
        "voided_by": bill.voided_by,
        "void_reason": bill.void_reason,
        "created_by": bill.created_by,
        "updated_by": bill.updated_by,
        "created_at": bill.created_at,
        "updated_at": bill.updated_at,
    }
