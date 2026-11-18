import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.account import Account
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.transaction import Transaction
from app.models.user import User
from app.services.audit_log import add_audit_log

router = APIRouter(prefix="/imports", tags=["Bank statement imports"])
TAIPEI = ZoneInfo("Asia/Taipei")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
ALLOWED_MAPPING_KEYS = {"date", "amount", "description", "type", "currency_code", "external_reference"}


def _authorize(db: Session, user: User, family_id: int, permission: str, resource: str = "imports") -> str:
    try:
        _, roles = require_permission(db, user.id, family_id, permission)
        return require_data_scope(db, roles, family_id, resource)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _decode_csv(raw: bytes) -> str:
    if not raw:
        raise HTTPException(status_code=422, detail="CSV 檔案不可為空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV 檔案不可超過 10 MB")
    for encoding in ("utf-8-sig", "cp950"):
        try:
            text = raw.decode(encoding)
            if "\x00" in text:
                raise ValueError("NUL byte")
            return text
        except (UnicodeDecodeError, ValueError):
            continue
    raise HTTPException(status_code=415, detail="無法辨識 CSV 編碼，請轉存為 UTF-8 或 Big5/CP950")


def _read_csv(raw: bytes):
    text = _decode_csv(raw)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    headers = [str(x).strip() if x is not None else "" for x in (reader.fieldnames or [])]
    if not headers or any(not x for x in headers) or len(set(headers)) != len(headers):
        raise HTTPException(status_code=422, detail="CSV 標題列不可空白或重複")
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise HTTPException(status_code=413, detail=f"單一檔案最多匯入 {MAX_ROWS} 筆資料")
        rows.append({str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None})
    if not rows:
        raise HTTPException(status_code=422, detail="CSV 沒有可匯入的資料列")
    return headers, rows


def _parse_date(value: str) -> datetime:
    value = (value or "").strip()
    if not value:
        raise ValueError("日期不可空白")
    parsed = None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError("日期格式無法辨識")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(timezone.utc)


def _parse_amount(value: str) -> tuple[Decimal, bool]:
    raw = (value or "").strip().replace(",", "").replace("NT$", "").replace("TWD", "").replace("$", "").strip()
    negative_parentheses = raw.startswith("(") and raw.endswith(")")
    if negative_parentheses:
        raw = raw[1:-1].strip()
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("金額格式無法辨識") from exc
    negative = amount < 0 or negative_parentheses
    amount = abs(amount)
    if amount <= 0:
        raise ValueError("金額必須大於 0")
    if max(0, -amount.as_tuple().exponent) > 4:
        raise ValueError("金額最多支援小數 4 位")
    if len(amount.as_tuple().digits) > 20:
        raise ValueError("金額超出系統精度")
    return amount, negative


def _parse_type(value: str, negative: bool) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return "expense" if negative else "income"
    if normalized in {"expense", "debit", "withdrawal", "支出", "扣款", "轉出", "借方"}:
        return "expense"
    if normalized in {"income", "credit", "deposit", "收入", "存入", "轉入", "貸方"}:
        return "income"
    raise ValueError("交易類型只接受收入／支出或銀行常見借貸標示")


def _fingerprint(account_id: int, transaction_date: datetime, transaction_type: str, amount: Decimal, currency: str, description: str, reference: str | None) -> str:
    if reference:
        source = [account_id, transaction_date.isoformat(), transaction_type, format(amount, "f"), currency, reference.strip().casefold()]
    else:
        source = [account_id, transaction_date.isoformat(), transaction_type, format(amount, "f"), currency, description.strip().casefold()]
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _filename(value: str | None) -> str:
    name = (value or "statement.csv").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "statement.csv")[:255]


def _batch_summary(batch: BankImportBatch) -> dict:
    return {
        "id": batch.id, "family_id": batch.family_id, "account_id": batch.account_id,
        "source_filename": batch.source_filename, "status": batch.status,
        "total_rows": batch.total_rows, "ready_rows": batch.ready_rows,
        "duplicate_rows": batch.duplicate_rows, "invalid_rows": batch.invalid_rows,
        "imported_rows": batch.imported_rows, "created_by": batch.created_by,
        "confirmed_by": batch.confirmed_by, "confirmed_at": batch.confirmed_at,
        "created_at": batch.created_at,
    }


def _row_summary(row: BankImportRow) -> dict:
    return {
        "id": row.id, "row_number": row.row_number, "transaction_date": row.transaction_date,
        "transaction_type": row.transaction_type, "amount": str(row.amount) if row.amount is not None else None,
        "currency_code": row.currency_code, "description": row.description,
        "external_reference": row.external_reference, "status": row.status,
        "duplicate_of_row_id": row.duplicate_of_row_id, "error_message": row.error_message,
    }


def _get_batch(db: Session, family_id: int, batch_id: int, lock: bool = False) -> BankImportBatch:
    query = db.query(BankImportBatch).filter(
        BankImportBatch.id == batch_id, BankImportBatch.family_id == family_id,
    )
    if lock:
        query = query.with_for_update()
    batch = query.first()
    if batch is None:
        raise HTTPException(status_code=404, detail="找不到此家庭匯入批次")
    return batch


def _check_batch_scope(batch: BankImportBatch, user: User, scope: str):
    if scope == "own" and batch.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯入批次")


@router.post("/inspect", summary="讀取 CSV 標題與範例資料，不建立匯入批次")
def inspect_csv(
    family_id: int = Query(..., gt=0),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user, family_id, "imports.create")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="第一階段僅支援 CSV 檔案")
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    headers, rows = _read_csv(raw)
    return {"success": True, "filename": _filename(file.filename), "headers": headers, "sample_rows": rows[:3], "total_rows": len(rows)}


@router.post("/batches", status_code=status.HTTP_201_CREATED, summary="上傳並預覽銀行／信用卡 CSV")
def create_import_batch(
    family_id: int = Query(..., gt=0),
    account_id: int = Query(..., gt=0),
    mapping: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import_scope = _authorize(db, current_user, family_id, "imports.create")
    try:
        mapping_data = json.loads(mapping)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="欄位對應格式不正確")
    if not isinstance(mapping_data, dict) or set(mapping_data) - ALLOWED_MAPPING_KEYS:
        raise HTTPException(status_code=422, detail="欄位對應包含不支援的欄位")
    for required in ("date", "amount", "description"):
        if not isinstance(mapping_data.get(required), str) or not mapping_data[required].strip():
            raise HTTPException(status_code=422, detail=f"請指定「{required}」欄位")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="第一階段僅支援 CSV 檔案")
    account = db.query(Account).filter(
        Account.id == account_id, Account.family_id == family_id, Account.is_active.is_(True),
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="找不到可使用的啟用中家庭帳戶")
    try:
        _, account_roles = require_permission(db, current_user.id, family_id, "accounts.view")
        account_scope = require_data_scope(db, account_roles, family_id, "accounts")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if account_scope == "own" and account.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭帳戶")
    transaction_scope = None
    try:
        _, transaction_roles = require_permission(db, current_user.id, family_id, "transactions.create")
        transaction_scope = require_data_scope(db, transaction_roles, family_id, "transactions")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if import_scope == "own" or transaction_scope == "own":
        if account.created_by != current_user.id:
            raise HTTPException(status_code=404, detail="目前資料範圍不允許匯入此帳戶")

    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    headers, source_rows = _read_csv(raw)
    selected_headers = {value.strip() for value in mapping_data.values() if isinstance(value, str) and value.strip()}
    missing_headers = sorted(selected_headers - set(headers))
    if missing_headers:
        raise HTTPException(status_code=422, detail={"message": "欄位對應的 CSV 標題不存在", "missing_headers": missing_headers})

    batch = BankImportBatch(
        family_id=family_id, account_id=account_id, source_filename=_filename(file.filename),
        status="previewed", column_mapping=mapping_data, total_rows=len(source_rows),
        created_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    counts = {"ready": 0, "duplicate": 0, "invalid": 0}
    seen: dict[str, int] = {}
    for row_number, source in enumerate(source_rows, start=2):
        raw_data = {key: str(source.get(header, ""))[:500] for key, header in mapping_data.items() if isinstance(header, str)}
        parsed = {"date": None, "type": None, "amount": None, "currency": None, "description": None, "reference": None}
        fingerprint = hashlib.sha256(json.dumps([account_id, row_number, raw_data], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        error = None
        try:
            parsed["date"] = _parse_date(source.get(mapping_data["date"], ""))
            parsed["amount"], negative = _parse_amount(source.get(mapping_data["amount"], ""))
            parsed["type"] = _parse_type(source.get(mapping_data.get("type", ""), "") if mapping_data.get("type") else "", negative)
            parsed["currency"] = (source.get(mapping_data.get("currency_code", ""), "") if mapping_data.get("currency_code") else account.currency_code).strip().upper() or account.currency_code
            if not re.fullmatch(r"[A-Z]{3}", parsed["currency"]):
                raise ValueError("幣別必須為三個英文字母")
            if parsed["currency"] != account.currency_code:
                raise ValueError(f"CSV 幣別 {parsed['currency']} 與帳戶幣別 {account.currency_code} 不一致")
            parsed["description"] = (source.get(mapping_data["description"], "") or "").strip()[:200]
            if not parsed["description"]:
                raise ValueError("交易說明不可空白")
            parsed["reference"] = (source.get(mapping_data.get("external_reference", ""), "") if mapping_data.get("external_reference") else "").strip()[:100] or None
            fingerprint = _fingerprint(account_id, parsed["date"], parsed["type"], parsed["amount"], parsed["currency"], parsed["description"], parsed["reference"])
        except (ValueError, KeyError) as exc:
            error = str(exc)[:500]

        duplicate_of = None
        is_duplicate = False
        if error is None:
            if fingerprint in seen:
                is_duplicate = True
                duplicate_of = seen[fingerprint]
            else:
                previous = db.query(BankImportRow).filter(
                    BankImportRow.family_id == family_id,
                    BankImportRow.fingerprint == fingerprint,
                ).order_by(BankImportRow.id.desc()).first()
                if previous is not None:
                    is_duplicate = True
                    duplicate_of = previous.id
                elif parsed["reference"]:
                    prior_transaction = db.query(Transaction.id).filter(
                        Transaction.family_id == family_id, Transaction.account_id == account_id,
                        Transaction.external_reference == parsed["reference"], Transaction.is_voided.is_(False),
                    ).first()
                    is_duplicate = prior_transaction is not None

        row_item = BankImportRow(
            family_id=family_id, batch_id=batch.id, row_number=row_number,
            fingerprint=fingerprint, transaction_date=parsed["date"],
            transaction_type=parsed["type"], amount=parsed["amount"],
            currency_code=parsed["currency"], description=parsed["description"],
            external_reference=parsed["reference"], raw_data=raw_data,
            status="invalid" if error else ("duplicate" if is_duplicate else "ready"),
            duplicate_of_row_id=duplicate_of, error_message=error or ("與既有匯入或帳務資料重複" if is_duplicate else None),
        )
        db.add(row_item)
        db.flush()
        if fingerprint not in seen and error is None:
            seen[fingerprint] = row_item.id
        counts[row_item.status] += 1

    batch.ready_rows = counts["ready"]
    batch.duplicate_rows = counts["duplicate"]
    batch.invalid_rows = counts["invalid"]
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="create", entity_type="bank_import_batch", entity_id=batch.id,
        new_values={"account_id": account_id, "source_filename": batch.source_filename, "total_rows": batch.total_rows, **counts},
        description="建立銀行／信用卡對帳單匯入預覽；尚未寫入正式交易",
    )
    db.commit()
    db.refresh(batch)
    preview = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id, BankImportRow.batch_id == batch.id,
    ).order_by(BankImportRow.row_number.asc()).limit(100).all()
    return {"success": True, "batch": _batch_summary(batch), "rows": [_row_summary(x) for x in preview], "preview_limit": 100}


@router.get("/batches", summary="查詢家庭匯入批次")
def list_import_batches(
    family_id: int = Query(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.view")
    query = db.query(BankImportBatch).filter(BankImportBatch.family_id == family_id)
    if scope == "own":
        query = query.filter(BankImportBatch.created_by == current_user.id)
    total = query.count()
    items = query.order_by(BankImportBatch.created_at.desc(), BankImportBatch.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "batches": [_batch_summary(x) for x in items]}


@router.get("/batches/{batch_id}", summary="查詢匯入批次與暫存明細")
def get_import_batch(
    batch_id: int,
    family_id: int = Query(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(0, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.view")
    batch = _get_batch(db, family_id, batch_id)
    _check_batch_scope(batch, current_user, scope)
    rows = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id, BankImportRow.batch_id == batch_id,
    ).order_by(BankImportRow.row_number.asc()).offset(skip).limit(limit).all()
    return {"success": True, "batch": _batch_summary(batch), "rows": [_row_summary(x) for x in rows]}


@router.post("/batches/{batch_id}/confirm", summary="人工確認匯入批次並建立正式交易")
def confirm_import_batch(
    batch_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import_scope = _authorize(db, current_user, family_id, "imports.confirm")
    try:
        _, roles = require_permission(db, current_user.id, family_id, "transactions.create")
        transaction_scope = require_data_scope(db, roles, family_id, "transactions")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    batch = _get_batch(db, family_id, batch_id, lock=True)
    _check_batch_scope(batch, current_user, import_scope)
    if batch.status != "previewed":
        raise HTTPException(status_code=409, detail="只有尚未確認的匯入批次可以入帳")
    if transaction_scope == "own" and batch.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯入批次")
    account = db.query(Account).filter(
        Account.id == batch.account_id, Account.family_id == family_id, Account.is_active.is_(True),
    ).first()
    if account is None:
        raise HTTPException(status_code=409, detail="匯入帳戶已停用或不存在，無法入帳")
    rows = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id, BankImportRow.batch_id == batch.id,
        BankImportRow.status == "ready",
    ).order_by(BankImportRow.row_number.asc()).with_for_update().all()
    if not rows:
        raise HTTPException(status_code=409, detail="此批次沒有可確認的有效資料列")
    created_ids = []
    try:
        for row in rows:
            if row.transaction_date is None or row.amount is None or row.transaction_type not in {"income", "expense"}:
                raise HTTPException(status_code=409, detail=f"第 {row.row_number} 列資料不完整，請重新匯入")
            transaction = Transaction(
                family_id=family_id, account_id=batch.account_id,
                transaction_type=row.transaction_type, amount=row.amount,
                currency_code=row.currency_code or account.currency_code,
                transaction_date=row.transaction_date, description=row.description,
                external_reference=row.external_reference,
                note=f"由匯入批次 #{batch.id} 第 {row.row_number} 列建立",
                import_row_id=row.id, created_by=current_user.id,
            )
            db.add(transaction)
            db.flush()
            row.status = "imported"
            created_ids.append(transaction.id)
            add_audit_log(
                db, family_id=family_id, actor_user_id=current_user.id,
                action="create", entity_type="transaction", entity_id=transaction.id,
                new_values={"account_id": transaction.account_id, "transaction_type": transaction.transaction_type,
                            "amount": transaction.amount, "currency_code": transaction.currency_code,
                            "transaction_date": transaction.transaction_date, "description": transaction.description,
                            "external_reference": transaction.external_reference, "import_row_id": row.id},
                description="由銀行／信用卡對帳單匯入交易",
            )
        batch.status = "confirmed"
        batch.ready_rows = 0
        batch.imported_rows = len(created_ids)
        batch.confirmed_by = current_user.id
        batch.confirmed_at = datetime.now(timezone.utc)
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="confirm", entity_type="bank_import_batch", entity_id=batch.id,
            new_values={"status": batch.status, "imported_rows": batch.imported_rows, "transaction_ids": created_ids},
            description="人工確認匯入批次並正式建立交易",
        )
        db.commit()
        db.refresh(batch)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="匯入資料已處理或與現有交易衝突；未建立部分交易，請重新整理批次") from exc
    except Exception:
        db.rollback()
        raise
    return {"success": True, "message": f"已成功建立 {len(created_ids)} 筆正式交易", "batch": _batch_summary(batch), "transaction_ids": created_ids}


@router.post("/batches/{batch_id}/void", summary="取消尚未入帳的匯入批次")
def void_import_batch(
    batch_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "imports.void")
    batch = _get_batch(db, family_id, batch_id, lock=True)
    _check_batch_scope(batch, current_user, scope)
    if batch.status != "previewed":
        raise HTTPException(status_code=409, detail="只有尚未入帳的預覽批次可以取消；已入帳資料請透過交易作廢流程處理")
    skipped = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id, BankImportRow.batch_id == batch.id,
        BankImportRow.status == "ready",
    ).update({"status": "skipped"}, synchronize_session=False)
    batch.status = "cancelled"
    batch.ready_rows = 0
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="void", entity_type="bank_import_batch", entity_id=batch.id,
        new_values={"status": "cancelled", "skipped_rows": skipped},
        description="取消尚未入帳的銀行／信用卡對帳單匯入批次",
    )
    db.commit()
    db.refresh(batch)
    return {"success": True, "message": "匯入批次已取消，未建立正式交易", "batch": _batch_summary(batch)}
