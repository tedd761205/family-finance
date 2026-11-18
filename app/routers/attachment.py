import hashlib
import logging
import re
import uuid
import warnings
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.attachment import Attachment
from app.models.bill import Bill
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.attachment import (
    AttachmentListResponse,
    AttachmentMessageResponse,
    AttachmentResponse,
)
from app.services import attachment_storage
from app.services.audit_log import add_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/attachments", tags=["Attachments"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _authorize(db: Session, user_id: int, family_id: int, action: str) -> str:
    try:
        _, roles = require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code=f"attachments.{action}",
        )
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="attachments",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _parent_scope(db: Session, user: User, family_id: int, *, bill_id=None, transaction_id=None):
    if (bill_id is None) == (transaction_id is None):
        raise HTTPException(status_code=422, detail="附件必須且只能關聯一張帳單或一筆交易")

    if bill_id is not None:
        try:
            _, roles = require_permission(
                db=db, user_id=user.id, family_id=family_id,
                permission_code="bills.view",
            )
            scope = require_data_scope(
                db=db, roles=roles, family_id=family_id, resource="bills",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        bill = db.query(Bill).filter(
            Bill.id == bill_id, Bill.family_id == family_id,
        ).first()
        if bill is None or bill.is_voided:
            raise HTTPException(status_code=404, detail="找不到此家庭帳單")
        if scope == "own" and bill.created_by != user.id:
            raise HTTPException(status_code=404, detail="找不到此家庭帳單")
        return bill

    try:
        _, roles = require_permission(
            db=db, user_id=user.id, family_id=family_id,
            permission_code="transactions.view",
        )
        scope = require_data_scope(
            db=db, roles=roles, family_id=family_id, resource="transactions",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.family_id == family_id,
    ).first()
    if transaction is None or transaction.is_voided:
        raise HTTPException(status_code=404, detail="找不到此家庭交易")
    if scope == "own" and transaction.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭交易")
    return transaction


def _check_attachment_access(attachment: Attachment, user: User, scope: str):
    if scope == "own" and attachment.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此附件")


def _get_attachment(db: Session, family_id: int, attachment_id: int) -> Attachment:
    attachment = db.query(Attachment).filter(
        Attachment.id == attachment_id,
        Attachment.family_id == family_id,
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="找不到此家庭附件")
    return attachment


def _check_parent_for_attachment(db: Session, user: User, attachment: Attachment):
    _parent_scope(
        db, user, attachment.family_id,
        bill_id=attachment.bill_id,
        transaction_id=attachment.transaction_id,
    )


def _safe_filename(value: str | None) -> str:
    name = (value or "attachment").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\\x00-\\x1f\\x7f]", "", name).strip()
    return (name or "attachment")[:255]


def _normalize_image(raw: bytes) -> tuple[bytes, str, str]:
    if not raw:
        raise HTTPException(status_code=422, detail="附件內容不可為空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="附件大小不可超過 10 MB")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                image_format = source.format
                if image_format not in ALLOWED_FORMATS:
                    raise HTTPException(
                        status_code=415,
                        detail="目前僅接受 JPEG、PNG 或 WebP 圖片",
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(status_code=415, detail="目前不接受動畫圖片")
                width, height = source.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="圖片尺寸超出安全限制")
                source.verify()

            with Image.open(BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source)
                content_type, extension = ALLOWED_FORMATS[image_format]
                output = BytesIO()
                if image_format == "JPEG":
                    image = image.convert("RGB")
                    image.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
                elif image_format == "PNG":
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    image.save(output, format="PNG", optimize=True)
                else:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    image.save(output, format="WEBP", quality=88, method=4)
                normalized = output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=422, detail="無法辨識圖片內容或圖片檔案已損毀")

    if not normalized or len(normalized) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="圖片處理後大小超出 10 MB 限制")
    return normalized, content_type, extension


def _storage_error(exc: Exception):
    logger.exception("附件物件儲存操作失敗")
    raise HTTPException(
        status_code=503,
        detail="附件儲存服務目前無法使用，請稍後再試",
    ) from exc


def _cleanup_object(object_key: str):
    try:
        attachment_storage.delete_object(object_key)
    except Exception:
        logger.exception("附件資料庫寫入失敗後，清理暫存物件也失敗；需人工檢查孤兒物件")


@router.post(
    "",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上傳帳單或交易附件",
)
def upload_attachment(
    family_id: int = Query(..., gt=0),
    bill_id: int | None = Query(default=None, gt=0),
    transaction_id: int | None = Query(default=None, gt=0),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "upload")
    parent = _parent_scope(
        db, current_user, family_id, bill_id=bill_id, transaction_id=transaction_id,
    )
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="附件大小不可超過 10 MB")
    content, content_type, extension = _normalize_image(raw)
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"family-{family_id}/attachments/{uuid.uuid4().hex}.{extension}"
    original_filename = _safe_filename(file.filename)

    try:
        attachment_storage.upload_object(object_key, content, content_type, digest)
    except attachment_storage.AttachmentStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _storage_error(exc)

    attachment = Attachment(
        family_id=family_id,
        bill_id=bill_id,
        transaction_id=transaction_id,
        object_key=object_key,
        original_filename=original_filename,
        content_type=content_type,
        file_size=len(content),
        sha256=digest,
        created_by=current_user.id,
    )
    try:
        db.add(attachment)
        db.flush()
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="attachment",
            entity_id=attachment.id,
            new_values={
                "bill_id": bill_id,
                "transaction_id": transaction_id,
                "original_filename": original_filename,
                "content_type": content_type,
                "file_size": len(content),
                "sha256": digest,
            },
            description="上傳財務附件",
        )
        db.commit()
        db.refresh(attachment)
        return attachment
    except IntegrityError as exc:
        db.rollback()
        _cleanup_object(object_key)
        logger.exception("建立附件資料時發生完整性錯誤")
        raise HTTPException(status_code=409, detail="附件資料關聯不合法或違反資料庫限制") from exc
    except Exception:
        db.rollback()
        _cleanup_object(object_key)
        raise


@router.get("", response_model=AttachmentListResponse, summary="查詢帳單或交易附件")
def list_attachments(
    family_id: int = Query(..., gt=0),
    bill_id: int | None = Query(default=None, gt=0),
    transaction_id: int | None = Query(default=None, gt=0),
    include_voided: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    _parent_scope(db, current_user, family_id, bill_id=bill_id, transaction_id=transaction_id)
    query = db.query(Attachment).filter(Attachment.family_id == family_id)
    query = query.filter(
        Attachment.bill_id == bill_id if bill_id is not None
        else Attachment.transaction_id == transaction_id
    )
    if scope == "own":
        query = query.filter(Attachment.created_by == current_user.id)
    if not include_voided:
        query = query.filter(Attachment.is_voided.is_(False))
    total = query.count()
    items = query.order_by(Attachment.created_at.desc(), Attachment.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "attachments": items}


@router.get("/{attachment_id}", response_model=AttachmentResponse, summary="查詢附件資訊")
def get_attachment(
    attachment_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    attachment = _get_attachment(db, family_id, attachment_id)
    _check_attachment_access(attachment, current_user, scope)
    _check_parent_for_attachment(db, current_user, attachment)
    return attachment


@router.get("/{attachment_id}/content", summary="讀取附件圖片")
def download_attachment(
    attachment_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    attachment = _get_attachment(db, family_id, attachment_id)
    _check_attachment_access(attachment, current_user, scope)
    _check_parent_for_attachment(db, current_user, attachment)
    if attachment.is_voided:
        raise HTTPException(status_code=404, detail="找不到此附件")

    try:
        content = attachment_storage.download_object(attachment.object_key)
    except attachment_storage.AttachmentStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _storage_error(exc)

    if hashlib.sha256(content).hexdigest() != attachment.sha256:
        logger.error("附件 SHA-256 驗證失敗，attachment_id=%s", attachment.id)
        raise HTTPException(status_code=500, detail="附件完整性驗證失敗")

    add_audit_log(
        db,
        family_id=family_id,
        actor_user_id=current_user.id,
        action="download",
        entity_type="attachment",
        entity_id=attachment.id,
        new_values={"sha256": attachment.sha256},
        description="讀取財務附件",
    )
    db.commit()

    filename = quote(attachment.original_filename, safe="")
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "Content-Length": str(len(content)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/{attachment_id}",
    response_model=AttachmentMessageResponse,
    summary="作廢附件",
)
def void_attachment(
    attachment_id: int,
    family_id: int = Query(..., gt=0),
    reason: str | None = Query(default=None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "void")
    attachment = _get_attachment(db, family_id, attachment_id)
    _check_attachment_access(attachment, current_user, scope)
    _check_parent_for_attachment(db, current_user, attachment)
    if attachment.is_voided:
        raise HTTPException(status_code=409, detail="此附件已經作廢")

    attachment.is_voided = True
    attachment.voided_at = datetime.now(timezone.utc)
    attachment.voided_by = current_user.id
    attachment.void_reason = reason.strip() if reason and reason.strip() else None
    add_audit_log(
        db,
        family_id=family_id,
        actor_user_id=current_user.id,
        action="void",
        entity_type="attachment",
        entity_id=attachment.id,
        new_values={
            "is_voided": True,
            "voided_at": attachment.voided_at,
            "void_reason": attachment.void_reason,
        },
        description="作廢財務附件（檔案本體保留）",
    )
    db.commit()
    db.refresh(attachment)
    return {"success": True, "message": "附件已作廢，原始檔案仍保留", "attachment": attachment}
