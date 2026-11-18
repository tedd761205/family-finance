import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.recurring_bill import RecurringBill


def advance_date(value: date, frequency: str, interval_count: int, anchor_day: int | None = None, anchor_month: int | None = None) -> date:
    """依原始日錨點推進週期；月末日期不足時採該月最後一天。"""
    if frequency == "weekly":
        return value + timedelta(days=7 * interval_count)
    if frequency == "monthly":
        month_index = value.year * 12 + value.month - 1 + interval_count
        year, month0 = divmod(month_index, 12)
        month = month0 + 1
        day = anchor_day or value.day\n        return date(year, month, min(day, calendar.monthrange(year, month)[1]))
    if frequency == "yearly":
        year = value.year + interval_count
        month = anchor_month or value.month\n        day = anchor_day or value.day\n        return date(year, month, min(day, calendar.monthrange(year, month)[1]))
    raise ValueError("不支援的定期帳單週期")


def generate_due_bills(db: Session, rule: RecurringBill, through_date: date, actor_user_id: int) -> list[int]:
    """產生至指定日期為止的帳單；唯一索引確保每一期不重複。"""
    if not rule.is_active:
        return []
    generated_ids: list[int] = []
    current = rule.next_run_date
    while current <= through_date and (rule.end_date is None or current <= rule.end_date):
        bill = Bill(
            family_id=rule.family_id,
            title=rule.title,
            category_id=rule.category_id,
            bill_date=current,
            billing_period_start=current,
            billing_period_end=current,
            due_date=current + timedelta(days=rule.due_days_after),
            original_amount=rule.original_amount,
            tax_amount=rule.tax_amount,
            discount_amount=rule.discount_amount,
            currency_code=rule.currency_code,
            note=rule.note,
            recurring_bill_id=rule.id,
            recurring_occurrence_date=current,
            created_by=actor_user_id,
        )
        db.add(bill)
        db.flush()
        generated_ids.append(bill.id)
        current = advance_date(\n            current, rule.frequency, rule.interval_count,\n            anchor_day=rule.start_date.day, anchor_month=rule.start_date.month,\n        )
    rule.next_run_date = current
    if rule.end_date is not None and current > rule.end_date:
        rule.is_active = False
    return generated_ids
