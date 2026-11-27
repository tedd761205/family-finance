import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import cast, exists, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.einvoice import EInvoice, EInvoiceImportBatch, EInvoiceItem
from app.models.user import User
from app.services.audit_log import add_audit_log


router = APIRouter(prefix="/einvoices", tags=["Electronic invoices"])

MAX_INVOICES = 5000
MAX_TOTAL_ITEMS = 20000
MAX_ITEMS_PER_INVOICE = 1000
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("1000000000000000000")
INVOICE_NUMBER_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{8}$")
TAX_ID_PATTERN = re.compile(r"^[0-9]{8}$")


def _authorize(db: Session, user: User, family_id: int, permission: str) -> str:
    try:
        _, roles = require_permission(
            db=db,
            user_id=user.id,
            family_id=family_id,
            permission_code=permission,
        )
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="imports",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _check_created_by_scope(created_by: int, user: User, scope: str, detail: str) -> None:
    if scope == "own" and created_by != user.id:
        raise HTTPException(status_code=404, detail=detail)


def _safe_filename(value: object) -> str:
    name = str(value or "電子發票.csv").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "電子發票.csv")[:255]


def _parse_amount(value: object, label: str, *, allow_negative: bool) -> Decimal:
    try:
        amount = Decimal(str(value).strip().replace(",", "").replace("NT$", "").replace("$", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"{label}金額格式不正確")
    if not amount.is_finite():
        raise HTTPException(status_code=422, detail=f"{label}金額必須是有效數字")
    if amount.as_tuple().exponent < -2:
        raise HTTPException(status_code=422, detail=f"{label}金額最多支援小數 2 位")
    if abs(amount) >= MAX_AMOUNT:
        raise HTTPException(status_code=422, detail=f"{label}金額超出系統可保存範圍")
    if not allow_negative and amount < 0:
        raise HTTPException(status_code=422, detail=f"{label}金額不可為負數")
    return amount.quantize(CENT)


def _parse_invoice_payload(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="發票資料格式不正確")
    invoice_number = str(raw.get("invoice_number") or "").strip().upper()
    if not INVOICE_NUMBER_PATTERN.fullmatch(invoice_number):
        raise HTTPException(status_code=422, detail="發票號碼格式不正確")
    try:
        invoice_date = date.fromisoformat(str(raw.get("date") or raw.get("invoice_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 日期格式不正確")

    merchant_tax_id = str(raw.get("merchant_tax_id") or "").strip() or None
    if merchant_tax_id and not TAX_ID_PATTERN.fullmatch(merchant_tax_id):
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的店家統編格式不正確")

    merchant_name = str(raw.get("merchant_name") or "").strip()
    if len(merchant_name) > 200:
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的店家名稱過長")
    merchant_name = merchant_name or "未提供店家"

    invoice_status = str(raw.get("invoice_status") or "").strip()
    if len(invoice_status) > 50:
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的狀態文字過長")
    carrier_type = str(raw.get("carrier_type") or "").strip() or None
    if carrier_type and len(carrier_type) > 80:
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的載具類型過長")

    total_amount = _parse_amount(raw.get("total_amount"), f"發票 {invoice_number} 總", allow_negative=False)
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS_PER_INVOICE:
        raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的明細筆數超出限制")

    items = []
    detail_total = Decimal("0.00")
    for line_number, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的第 {line_number} 筆明細格式不正確")
        item_name = str(item.get("item_name") or item.get("name") or "").strip()
        if not item_name:
            raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的第 {line_number} 筆品項名稱不可空白")
        if len(item_name) > 200:
            raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的第 {line_number} 筆品項名稱過長")
        amount = _parse_amount(item.get("amount"), f"發票 {invoice_number} 第 {line_number} 筆明細", allow_negative=True)
        source_line_number = item.get("source_line")
        if source_line_number is not None:
            try:
                source_line_number = int(source_line_number)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的來源行號不正確")
            if source_line_number < 1 or source_line_number > 20000:
                raise HTTPException(status_code=422, detail=f"發票 {invoice_number} 的來源行號超出範圍")
        items.append({
            "line_number": line_number,
            "item_name": item_name,
            "amount": amount,
            "source_line_number": source_line_number,
        })
        detail_total += amount

    difference_amount = detail_total - total_amount
    is_duplicate = raw.get("duplicate") is True
    if is_duplicate:
        verification_status = "duplicate"
    elif not items:
        verification_status = "missing_details"
    elif difference_amount == 0:
        verification_status = "matched"
    else:
        verification_status = "mismatch"

    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "merchant_tax_id": merchant_tax_id,
        "merchant_name": merchant_name,
        "total_amount": total_amount,
        "invoice_status": invoice_status,
        "carrier_type": carrier_type,
        "detail_total": detail_total,
        "difference_amount": difference_amount,
        "verification_status": verification_status,
        "is_duplicate": is_duplicate,
        "items": items,
    }


def _batch_summary(batch: EInvoiceImportBatch) -> dict:
    return {
        "id": batch.id,
        "family_id": batch.family_id,
        "source_filename": batch.source_filename,
        "status": batch.status,
        "total_invoices": batch.total_invoices,
        "saved_invoices": batch.saved_invoices,
        "duplicate_invoices": batch.duplicate_invoices,
        "issue_invoices": batch.issue_invoices,
        "created_by": batch.created_by,
        "created_at": batch.created_at,
    }


def _invoice_summary(invoice: EInvoice) -> dict:
    return {
        "id": invoice.id,
        "family_id": invoice.family_id,
        "import_batch_id": invoice.import_batch_id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "merchant_tax_id": invoice.merchant_tax_id,
        "merchant_name": invoice.merchant_name,
        "total_amount": str(invoice.total_amount),
        "invoice_status": invoice.invoice_status,
        "carrier_type": invoice.carrier_type,
        "detail_total": str(invoice.detail_total),
        "difference_amount": str(invoice.difference_amount),
        "verification_status": invoice.verification_status,
        "is_duplicate": invoice.is_duplicate,
        "is_voided": invoice.is_voided,
        "created_by": invoice.created_by,
        "created_at": invoice.created_at,
    }


def _invoice_detail(invoice: EInvoice, items: list[EInvoiceItem]) -> dict:
    result = _invoice_summary(invoice)
    result["items"] = [
        {
            "id": item.id,
            "line_number": item.line_number,
            "item_name": item.item_name,
            "amount": str(item.amount),
            "source_line_number": item.source_line_number,
        }
        for item in items
    ]
    return result


@router.post("/imports", status_code=status.HTTP_201_CREATED, summary="將已檢查的發票正式保存到家庭發票庫")
def save_invoice_import(
    family_id: int = Query(..., gt=0),
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.create")
    _authorize(db, current_user, family_id, "imports.confirm")

    raw_invoices = payload.get("invoices") if isinstance(payload, dict) else None
    if not isinstance(raw_invoices, list) or not raw_invoices:
        raise HTTPException(status_code=422, detail="沒有可保存的發票資料")
    if len(raw_invoices) > MAX_INVOICES:
        raise HTTPException(status_code=413, detail=f"單次最多保存 {MAX_INVOICES} 張發票")

    parsed = []
    total_items = 0
    for raw in raw_invoices:
        invoice = _parse_invoice_payload(raw)
        total_items += len(invoice["items"])
        if total_items > MAX_TOTAL_ITEMS:
            raise HTTPException(status_code=413, detail=f"單次最多保存 {MAX_TOTAL_ITEMS} 筆商品／折扣明細")
        parsed.append(invoice)

    filename = _safe_filename(payload.get("source_filename"))
    source_sha256 = str(payload.get("source_sha256") or "").strip().lower() or None
    if source_sha256 and not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise HTTPException(status_code=422, detail="來源檔案 SHA-256 格式不正確")

    invoice_numbers = [item["invoice_number"] for item in parsed]
    existing_numbers = set()
    if invoice_numbers:
        existing_numbers = set(
            value[0]
            for value in db.query(EInvoice.invoice_number).filter(
                EInvoice.family_id == family_id,
                EInvoice.invoice_number.in_(set(invoice_numbers)),
            ).all()
        )

    batch = EInvoiceImportBatch(
        family_id=family_id,
        source_filename=filename,
        source_sha256=source_sha256,
        status="completed",
        total_invoices=len(parsed),
        created_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    seen = set()
    saved_count = 0
    duplicate_count = 0
    issue_count = 0
    try:
        for invoice_data in parsed:
            invoice_number = invoice_data["invoice_number"]
            if invoice_number in seen or invoice_number in existing_numbers:
                duplicate_count += 1
                continue
            seen.add(invoice_number)

            invoice = EInvoice(
                family_id=family_id,
                import_batch_id=batch.id,
                invoice_number=invoice_number,
                invoice_date=invoice_data["invoice_date"],
                merchant_tax_id=invoice_data["merchant_tax_id"],
                merchant_name=invoice_data["merchant_name"],
                total_amount=invoice_data["total_amount"],
                invoice_status=invoice_data["invoice_status"],
                carrier_type=invoice_data["carrier_type"],
                detail_total=invoice_data["detail_total"],
                difference_amount=invoice_data["difference_amount"],
                verification_status=invoice_data["verification_status"],
                is_duplicate=invoice_data["is_duplicate"],
                created_by=current_user.id,
                updated_by=current_user.id,
            )
            db.add(invoice)
            db.flush()
            for item_data in invoice_data["items"]:
                db.add(EInvoiceItem(
                    family_id=family_id,
                    invoice_id=invoice.id,
                    line_number=item_data["line_number"],
                    item_name=item_data["item_name"],
                    amount=item_data["amount"],
                    source_line_number=item_data["source_line_number"],
                ))
            saved_count += 1
            if invoice.verification_status != "matched":
                issue_count += 1

        batch.saved_invoices = saved_count
        batch.duplicate_invoices = duplicate_count
        batch.issue_invoices = issue_count
        batch.status = "completed_with_issues" if (duplicate_count or issue_count) else "completed"
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="einvoice_import_batch",
            entity_id=batch.id,
            new_values={
                "source_filename": filename,
                "total_invoices": len(parsed),
                "saved_invoices": saved_count,
                "duplicate_invoices": duplicate_count,
                "issue_invoices": issue_count,
                "source_sha256": source_sha256,
            },
            description="將電子發票匯入家庭發票庫；未建立收入或支出交易",
        )
        db.commit()
        db.refresh(batch)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="發票保存時發生重複資料或關聯衝突，請重新整理歷史發票後再試") from exc
    except Exception:
        db.rollback()
        raise

    return {
        "success": True,
        "message": f"已保存 {saved_count} 張發票，略過重複 {duplicate_count} 張。",
        "batch": _batch_summary(batch),
    }


@router.get("/batches", summary="查詢家庭發票匯入批次")
def list_einvoice_import_batches(
    family_id: int = Query(..., gt=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.view")
    query = db.query(EInvoiceImportBatch).filter(EInvoiceImportBatch.family_id == family_id)
    if scope == "own":
        query = query.filter(EInvoiceImportBatch.created_by == current_user.id)
    total = query.count()
    batches = query.order_by(
        EInvoiceImportBatch.created_at.desc(), EInvoiceImportBatch.id.desc()
    ).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "batches": [_batch_summary(batch) for batch in batches]}


@router.get("", summary="搜尋及分頁查詢家庭歷史發票")
def list_einvoices(
    family_id: int = Query(..., gt=0),
    q: str | None = Query(default=None, max_length=120),
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    verification_status: str = Query(default="all"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    min_amount: Decimal | None = Query(default=None, ge=0),
    max_amount: Decimal | None = Query(default=None, ge=0),
    include_voided: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.view")
    query = db.query(EInvoice).filter(EInvoice.family_id == family_id)
    if scope == "own":
        query = query.filter(EInvoice.created_by == current_user.id)
    if not include_voided:
        query = query.filter(EInvoice.is_voided.is_(False))

    if month:
        year, month_number = (int(value) for value in month.split("-"))
        month_start = date(year, month_number, 1)
        month_end = date(year + 1, 1, 1) if month_number == 12 else date(year, month_number + 1, 1)
        query = query.filter(EInvoice.invoice_date >= month_start, EInvoice.invoice_date < month_end)

    if start_date:
        query = query.filter(EInvoice.invoice_date >= start_date)
    if end_date:
        query = query.filter(EInvoice.invoice_date <= end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="開始日期不可晚於結束日期")
    if min_amount is not None:
        query = query.filter(EInvoice.total_amount >= min_amount)
    if max_amount is not None:
        query = query.filter(EInvoice.total_amount <= max_amount)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(status_code=422, detail="最低金額不可大於最高金額")

    if verification_status == "duplicate":
        query = query.filter(EInvoice.is_duplicate.is_(True))
    elif verification_status != "all":
        if verification_status not in {"matched", "mismatch", "missing_details"}:
            raise HTTPException(status_code=422, detail="發票狀態篩選條件不正確")
        query = query.filter(EInvoice.verification_status == verification_status)

    term = (q or "").strip()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        search_terms = [
            EInvoice.invoice_number.ilike(pattern, escape="\\"),
            EInvoice.merchant_name.ilike(pattern, escape="\\"),
            EInvoice.merchant_tax_id.ilike(pattern, escape="\\"),
            EInvoice.invoice_status.ilike(pattern, escape="\\"),
            EInvoice.carrier_type.ilike(pattern, escape="\\"),
        ]
        search_terms.append(cast(EInvoice.invoice_date, String).ilike(pattern, escape="\\"))
        search_terms.append(
            exists().where(
                EInvoiceItem.family_id == family_id,
                EInvoiceItem.invoice_id == EInvoice.id,
                EInvoiceItem.item_name.ilike(pattern, escape="\\"),
            )
        )
        numeric_text = term.replace(",", "").replace("NT$", "").replace("$", "").strip()
        try:
            numeric_amount = Decimal(numeric_text)
            if numeric_amount.is_finite() and numeric_amount >= 0:
                search_terms.append(EInvoice.total_amount == numeric_amount)
                search_terms.append(
                    exists().where(
                        EInvoiceItem.family_id == family_id,
                        EInvoiceItem.invoice_id == EInvoice.id,
                        EInvoiceItem.amount == numeric_amount,
                    )
                )
        except InvalidOperation:
            pass
        query = query.filter(or_(*search_terms))

    total = query.count()
    invoices = query.order_by(
        EInvoice.invoice_date.desc(), EInvoice.created_at.desc(), EInvoice.id.desc()
    ).offset(skip).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "invoices": [_invoice_summary(invoice) for invoice in invoices],
    }


@router.get("/{invoice_id}", summary="查詢單張家庭發票及商品明細")
def get_einvoice(
    invoice_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.view")
    invoice = db.query(EInvoice).filter(
        EInvoice.id == invoice_id,
        EInvoice.family_id == family_id,
        EInvoice.is_voided.is_(False),
    ).first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="找不到此家庭發票")
    _check_created_by_scope(invoice.created_by, current_user, scope, "找不到此家庭發票")
    items = db.query(EInvoiceItem).filter(
        EInvoiceItem.family_id == family_id,
        EInvoiceItem.invoice_id == invoice_id,
    ).order_by(EInvoiceItem.line_number.asc()).all()
    return {"success": True, "invoice": _invoice_detail(invoice, items)}


@router.post("/{invoice_id}/void", summary="作廢家庭發票保存紀錄")
def void_einvoice(
    invoice_id: int,
    family_id: int = Query(..., gt=0),
    reason: str = Query(..., min_length=1, max_length=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.void")
    invoice = db.query(EInvoice).filter(
        EInvoice.id == invoice_id,
        EInvoice.family_id == family_id,
    ).with_for_update().first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="找不到此家庭發票")
    _check_created_by_scope(invoice.created_by, current_user, scope, "找不到此家庭發票")
    if invoice.is_voided:
        raise HTTPException(status_code=409, detail="此發票已經作廢")
    invoice.is_voided = True
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by = current_user.id
    invoice.void_reason = reason.strip()
    invoice.updated_by = current_user.id
    add_audit_log(
        db,
        family_id=family_id,
        actor_user_id=current_user.id,
        action="void",
        entity_type="einvoice",
        entity_id=invoice.id,
        old_values={"is_voided": False},
        new_values={"is_voided": True, "reason": invoice.void_reason},
        description="作廢家庭發票保存紀錄；不影響其他帳務交易",
    )
    db.commit()
    db.refresh(invoice)
    return {"success": True, "message": "發票紀錄已作廢；不會刪除明細或修改正式帳務。", "invoice": _invoice_summary(invoice)}
