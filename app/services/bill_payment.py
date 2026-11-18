from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.bill_payment import BillPayment


def get_bill_paid_amounts(
    db: Session,
    family_id: int,
    bill_ids: Iterable[int],
) -> dict[int, Decimal]:
    ids = list(set(bill_ids))
    if not ids:
        return {}
    net_amount = func.sum(
        case(
            (BillPayment.payment_type == "payment", BillPayment.amount),
            else_=-BillPayment.amount,
        )
    )
    rows = (
        db.query(BillPayment.bill_id, net_amount)
        .filter(
            BillPayment.family_id == family_id,
            BillPayment.bill_id.in_(ids),
            BillPayment.is_voided.is_(False),
        )
        .group_by(BillPayment.bill_id)
        .all()
    )
    return {bill_id: amount or Decimal("0") for bill_id, amount in rows}


def get_bill_paid_amount(db: Session, family_id: int, bill_id: int) -> Decimal:
    return get_bill_paid_amounts(db, family_id, [bill_id]).get(bill_id, Decimal("0"))


def get_payment_refunded_amount(db: Session, family_id: int, payment_id: int) -> Decimal:
    value = (
        db.query(func.coalesce(func.sum(BillPayment.amount), 0))
        .filter(
            BillPayment.family_id == family_id,
            BillPayment.original_payment_id == payment_id,
            BillPayment.payment_type == "refund",
            BillPayment.is_voided.is_(False),
        )
        .scalar()
    )
    return Decimal(value or 0)
