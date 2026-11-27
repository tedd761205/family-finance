import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, cast, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.electronic_invoice import (
    ElectronicInvoice,
    ElectronicInvoiceImportBatch,
    ElectronicInvoiceItem,
)
from app.models.user import User
from app.schemas.electronic_invoice import (
    ElectronicInvoiceDetail,
    ElectronicInvoiceImportRequest,
    ElectronicInvoiceImportResponse,
    ElectronicInvoiceListItem,
    ElectronicInvoiceListResponse,
    ElectronicInvoiceVoidRequest,
)
from app.services.audit_log import add_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/electronic-invoices", tags=["Electronic Invoices"])


def _authorize(db: Session, user_id: int, family_id: int, action: str) -> str:
    try:
        _, roles = require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code=f"invoices.{action}",
        )
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="invoices",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _get_invoice(db: Session, family_id: int, invoice_id: int, *, lock: bool = False) -> ElectronicInvoice:
    query = db.query(ElectronicInvoice).filter(
        ElectronicInvoice.id == invoice_id,
        ElectronicInvoice.family_id == family_id,
    )
    if lock:
        query = query.with_for_update()
    invoice = query.first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="找不到此家庭發票")
    return invoice


def _check_owner(invoice: ElectronicInvoice, user: User, scope: str) -> None:
    if scope == "own" and invoice.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭發票")


def _invoice_list_item(invoice: ElectronicInvoice, item_count: int) -> ElectronicInvoiceListItem:
    return ElectronicInvoiceListItem(
        id=invoice.id,
        family_id=invoice.family_id,
        import_batch_id=invoice.import_batch_id,
        invoice_date=invoice.invoice_date,
        invoice_number=invoice.invoice_number,
        merchant_tax_id=invoice.merchant_tax_id,
        merchant_name=invoice.merchant_name,
        total_amount=invoice.total_amount,
        detail_total_amount=invoice.detail_total_amount,
        difference_amount=invoice.difference_amount,
        currency_code=invoice.currency_code,
        invoice_status=invoice.invoice_status,
        carrier_type=invoice.carrier_type,
        validation_status=invoice.validation_status,
        duplicate_in_source=invoice.duplicate_in_source,
        linked_transaction_id=invoice.linked_transaction_id,
        is_voided=invoice.is_voided,
        created_by=invoice.created_by,
        created_at=invoice.created_at,
        item_count=item_count,
    )


@router.post(
    "/imports",
    response_model=ElectronicInvoiceImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_invoice_import(
    payload: ElectronicInvoiceImportRequest,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存瀏覽器已解析的發票資料；不建立交易，也不保存載具號碼或原始 CSV。"""
    _authorize(db, current_user.id, family_id, "import")

    invoice_numbers = list({item.invoice_number for item in payload.invoices})
    existing_rows = db.query(
        ElectronicInvoice.invoice_number,
    ).filter(
        ElectronicInvoice.family_id == family_id,
        ElectronicInvoice.invoice_number.in_(invoice_numbers),
    ).all()
    existing_numbers = {row.invoice_number for row in existing_rows}

    seen_numbers: set[str] = set()
    prepared: list[tuple[Any, Decimal | None, Decimal | None, str]] = []
    duplicate_count = 0
    detail_count = 0

    for incoming in payload.invoices:
        invoice_number = incoming.invoice_number
        if invoice_number in existing_numbers or invoice_number in seen_numbers:
            duplicate_count += 1
            continue
        seen_numbers.add(invoice_number)

        item_total = sum((row.amount for row in incoming.items), Decimal("0"))
        detail_total = item_total if incoming.items else None
        difference = item_total - incoming.total_amount if incoming.items else None

        if incoming.duplicate_in_source:
            validation_status = "duplicate_in_file"
        elif not incoming.items:
            validation_status = "missing_details"
        elif difference != Decimal("0"):
            validation_status = "mismatch"
        else:
            validation_status = "matched"

        prepared.append((incoming, detail_total, difference, validation_status))
        detail_count += len(incoming.items)

    batch = ElectronicInvoiceImportBatch(
        family_id=family_id,
        source_filename=payload.source_filename,
        received_count=len(payload.invoices),
        saved_count=len(prepared),
        duplicate_count=duplicate_count,
        created_by=current_user.id,
    )

    try:
        db.add(batch)
        db.flush()

            for incoming, detail_total, difference, validation_status in prepared:
            invoice = ElectronicInvoice(
                family_id=family_id,
                import_batch_id=batch.id,
                invoice_date=incoming.invoice_date,
                invoice_number=incoming.invoice_number,
                merchant_tax_id=incoming.merchant_tax_id,
                merchant_name=incoming.merchant_name,
                total_amount=incoming.total_amount,
                detail_total_amount=detail_total,
                difference_amount=difference,
                currency_code="TWD",
                invoice_status=incoming.invoice_status,
                carrier_type=incoming.carrier_type,
                validation_status=validation_status,
                duplicate_in_source=incoming.duplicate_in_source,
                created_by=current_user.id,
            )
            db.add(invoice)
            db.flush()

            db.add_all([
                ElectronicInvoiceItem(
                    family_id=family_id,
                    invoice_id=invoice.id,
                    item_name=item.item_name,
                    amount=item.amount,
                    sort_order=index,
                    created_by=current_user.id,
                )
                for index, item in enumerate(incoming.items)
            ])

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="import",
            entity_type="electronic_invoice_import_batch",
            entity_id=batch.id,
            new_values={
                "source_filename": batch.source_filename,
                "received_count": batch.received_count,
                "saved_count": batch.saved_count,
                "duplicate_count": batch.duplicate_count,
                "detail_count": detail_count,
            },
            description="保存電子發票匯入批次",
        )
        db.commit()
        db.refresh(batch)
        return ElectronicInvoiceImportResponse(
            message=(
                f"已保存 {batch.saved_count} 張發票；"
                f"{batch.duplicate_count} 張因家庭歷史紀錄或本次重複而略過。"
            ),
            batch_id=batch.id,
            received_count=batch.received_count,
            saved_count=batch.saved_count,
            duplicate_count=batch.duplicate_count,
            detail_count=detail_count,
        )
    except IntegrityError:
        db.rollback()
        logger.exception("保存電子發票時發生資料完整性錯誤")
        raise HTTPException(
            status_code=409,
            detail="發票資料與既有紀錄發生衝突，請重新整理歷史發票後再試。",
        )


@router.get("", response_model=ElectronicInvoiceListResponse)
def list_electronic_invoices(
    family_id: int = Query(..., gt=0),
    q: str | None = Query(default=None, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
    validation_status: str | None = Query(default=None, pattern="^(matched|mismatch|missing_details|duplicate_in_file)$"),
    include_voided: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="開始日期不可晚於結束日期")

    query = db.query(ElectronicInvoice).filter(ElectronicInvoice.family_id == family_id)
    if scope == "own":
        query = query.filter(ElectronicInvoice.created_by == current_user.id)
    if not include_voided:
        query = query.filter(ElectronicInvoice.is_voided.is_(False))
    if start_date is not None:
        query = query.filter(ElectronicInvoice.invoice_date >= start_date)
    if end_date is not None:
        query = query.filter(ElectronicInvoice.invoice_date <= end_date)
    if validation_status:
        query = query.filter(ElectronicInvoice.validation_status == validation_status)

    keyword = (q or "").strip()
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        item_match = exists().where(and_(
            ElectronicInvoiceItem.family_id == family_id,
            ElectronicInvoiceItem.invoice_id == ElectronicInvoice.id,
            ElectronicInvoiceItem.item_name.ilike(pattern, escape="\\"),
        ))
        query = query.filter(or_(
            ElectronicInvoice.invoice_number.ilike(pattern, escape="\\"),
            ElectronicInvoice.merchant_name.ilike(pattern, escape="\\"),
            ElectronicInvoice.merchant_tax_id.ilike(pattern, escape="\\"),
            ElectronicInvoice.invoice_status.ilike(pattern, escape="\\"),
            cast(ElectronicInvoice.invoice_date, String).ilike(pattern, escape="\\"),
            cast(ElectronicInvoice.total_amount, String).ilike(pattern, escape="\\"),
            item_match,
        ))

    total = query.count()
    rows = query.order_by(
        ElectronicInvoice.invoice_date.desc(),
        ElectronicInvoice.id.desc(),
    ).offset(skip).limit(limit).all()

    ids = [row.id for row in rows]
    item_counts: dict[int, int] = {}
    if ids:
        item_counts = {
            invoice_id: count
            for invoice_id, count in db.query(
                ElectronicInvoiceItem.invoice_id,
                func.count(ElectronicInvoiceItem.id),
            ).filter(
                ElectronicInvoiceItem.family_id == family_id,
                ElectronicInvoiceItem.invoice_id.in_(ids),
            ).group_by(ElectronicInvoiceItem.invoice_id).all()
        }

    return ElectronicInvoiceListResponse(
        total=total,
        skip=skip,
        limit=limit,
        invoices=[_invoice_list_item(row, item_counts.get(row.id, 0)) for row in rows],
    )


@router.get("/{invoice_id}", response_model=ElectronicInvoiceDetail)
def get_electronic_invoice(
    invoice_id: int,
    family_id: int = Query(..., gt=0),
    include_voided: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    invoice = _get_invoice(db, family_id, invoice_id)
    _check_owner(invoice, current_user, scope)
    if invoice.is_voided and not include_voided:
        raise HTTPException(status_code=404, detail="找不到此家庭發票")

    items = db.query(ElectronicInvoiceItem).filter(
        ElectronicInvoiceItem.family_id == family_id,
        ElectronicInvoiceItem.invoice_id == invoice.id,
    ).order_by(ElectronicInvoiceItem.sort_order, ElectronicInvoiceItem.id).all()
    data = _invoice_list_item(invoice, len(items)).model_dump()
    data["items"] = [
        {"id": item.id, "item_name": item.item_name, "amount": item.amount, "sort_order": item.sort_order}
        for item in items
    ]
    return ElectronicInvoiceDetail.model_validate(data)


@router.delete("/{invoice_id}", response_model=ElectronicInvoiceDetail)
def void_electronic_invoice(
    invoice_id: int,
    payload: ElectronicInvoiceVoidRequest,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "void")
    invoice = _get_invoice(db, family_id, invoice_id, lock=True)
    _check_owner(invoice, current_user, scope)
    if invoice.is_voided:
        raise HTTPException(status_code=409, detail="此發票已經作廢")
    if invoice.linked_transaction_id is not None:
        raise HTTPException(status_code=409, detail="此發票已連結帳務紀錄，請先解除連結後再作廢")

    old_values = {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "merchant_name": invoice.merchant_name,
        "total_amount": invoice.total_amount,
        "is_voided": invoice.is_voided,
    }
    invoice.is_voided = True
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by = current_user.id
    invoice.void_reason = payload.reason

    try:
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="void",
            entity_type="electronic_invoice",
            entity_id=invoice.id,
            old_values=old_values,
            new_values={**old_values, "is_voided": True, "void_reason": invoice.void_reason},
            description="作廢電子發票紀錄",
        )
        db.commit()
        db.refresh(invoice)
        items = db.query(ElectronicInvoiceItem).filter(
            ElectronicInvoiceItem.family_id == family_id,
            ElectronicInvoiceItem.invoice_id == invoice.id,
        ).order_by(ElectronicInvoiceItem.sort_order, ElectronicInvoiceItem.id).all()
        data = _invoice_list_item(invoice, len(items)).model_dump()
        data["items"] = [
            {"id": item.id, "item_name": item.item_name, "amount": item.amount, "sort_order": item.sort_order}
            for item in items
        ]
        return ElectronicInvoiceDetail.model_validate(data)
    except IntegrityError:
        db.rollback()
        logger.exception("作廢電子發票時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="作廢發票失敗，請重新整理後再試")
