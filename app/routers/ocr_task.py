import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.attachment import Attachment
from app.models.bill import Bill
from app.models.ocr_task import OcrTask
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.ocr_task import OcrTaskListResponse, OcrTaskMessageResponse, OcrTaskResponse
from app.services.audit_log import add_audit_log
from app.services.ocr_tasks import MAX_ATTEMPTS, process_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr/tasks", tags=["OCR"])


def _authorize(db: Session, user: User, family_id: int, action: str) -> str:
    try:
        _, roles = require_permission(
            db=db, user_id=user.id, family_id=family_id,
            permission_code=f"ocr.{action}",
        )
        return require_data_scope(db=db, roles=roles, family_id=family_id, resource="ocr")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _get_task(db: Session, family_id: int, task_id: int) -> OcrTask:
    task = db.query(OcrTask).filter(
        OcrTask.id == task_id, OcrTask.family_id == family_id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="找不到此 OCR 任務")
    return task


def _check_access(db: Session, user: User, task: OcrTask, scope: str) -> Attachment:
    if scope == "own" and task.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此 OCR 任務")
    attachment = db.query(Attachment).filter(
        Attachment.id == task.attachment_id,
        Attachment.family_id == task.family_id,
        Attachment.is_voided.is_(False),
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在或已作廢")
    if task.created_by != user.id and scope == "own":
        raise HTTPException(status_code=404, detail="找不到此 OCR 任務")

    # OCR access never grants access to the underlying financial record by itself.
    parent_permission = "bills.view" if attachment.bill_id is not None else "transactions.view"
    resource = "bills" if attachment.bill_id is not None else "transactions"
    try:
        _, roles = require_permission(
            db=db, user_id=user.id, family_id=task.family_id,
            permission_code=parent_permission,
        )
        parent_scope = require_data_scope(
            db=db, roles=roles, family_id=task.family_id, resource=resource,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if attachment.bill_id is not None:
        parent = db.query(Bill).filter(
            Bill.id == attachment.bill_id, Bill.family_id == task.family_id,
            Bill.is_voided.is_(False),
        ).first()
    else:
        parent = db.query(Transaction).filter(
            Transaction.id == attachment.transaction_id,
            Transaction.family_id == task.family_id,
            Transaction.is_voided.is_(False),
        ).first()
    if parent is None or (parent_scope == "own" and parent.created_by != user.id):
        raise HTTPException(status_code=404, detail="找不到附件所屬帳務資料")
    return attachment


@router.post("", response_model=OcrTaskMessageResponse, status_code=status.HTTP_201_CREATED)
def create_ocr_task(
    attachment_id: int = Query(..., gt=0),
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "create")
    attachment = db.query(Attachment).filter(
        Attachment.id == attachment_id, Attachment.family_id == family_id,
        Attachment.is_voided.is_(False),
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="找不到此家庭附件")
    # Also require attachment visibility and its parent financial-record scope.
    try:
        _, roles = require_permission(
            db=db, user_id=current_user.id, family_id=family_id,
            permission_code="attachments.view",
        )
        attachment_scope = require_data_scope(
            db=db, roles=roles, family_id=family_id, resource="attachments",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if attachment_scope == "own" and attachment.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此附件")

    parent_permission = "bills.view" if attachment.bill_id is not None else "transactions.view"
    parent_resource = "bills" if attachment.bill_id is not None else "transactions"
    try:
        _, parent_roles = require_permission(
            db=db, user_id=current_user.id, family_id=family_id,
            permission_code=parent_permission,
        )
        parent_scope = require_data_scope(
            db=db, roles=parent_roles, family_id=family_id, resource=parent_resource,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    parent_model = Bill if attachment.bill_id is not None else Transaction
    parent_id = attachment.bill_id if attachment.bill_id is not None else attachment.transaction_id
    parent = db.query(parent_model).filter(
        parent_model.id == parent_id, parent_model.family_id == family_id,
        parent_model.is_voided.is_(False),
    ).first()
    if parent is None or (parent_scope == "own" and parent.created_by != current_user.id):
        raise HTTPException(status_code=404, detail="找不到附件所屬帳務資料")

    existing = db.query(OcrTask).filter(
        OcrTask.family_id == family_id, OcrTask.attachment_id == attachment_id,
    ).first()
    if existing is not None:
        return {"success": True, "message": "此附件已有 OCR 任務", "task": existing}
    task = OcrTask(
        family_id=family_id, attachment_id=attachment_id,
        status="queued", provider="google_vision", created_by=current_user.id,
    )
    db.add(task)
    try:
        db.flush()
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="create", entity_type="ocr_task", entity_id=task.id,
            new_values={"attachment_id": attachment_id, "provider": task.provider},
            description="建立帳單圖片 OCR 任務",
        )
        db.commit()
        db.refresh(task)
    except IntegrityError:
        db.rollback()
        task = db.query(OcrTask).filter(
            OcrTask.family_id == family_id, OcrTask.attachment_id == attachment_id,
        ).first()
        if task is None:
            raise HTTPException(status_code=409, detail="建立 OCR 任務時發生衝突")
    return {"success": True, "message": "OCR 任務已建立，請執行辨識", "task": task}


@router.get("", response_model=OcrTaskListResponse)
def list_ocr_tasks(
    family_id: int = Query(..., gt=0),
    attachment_id: int | None = Query(default=None, gt=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "view")
    query = db.query(OcrTask).filter(OcrTask.family_id == family_id)
    if scope == "own":
        query = query.filter(OcrTask.created_by == current_user.id)
    if attachment_id is not None:
        query = query.filter(OcrTask.attachment_id == attachment_id)
    total = query.count()
    tasks = query.order_by(OcrTask.created_at.desc(), OcrTask.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "tasks": tasks}


@router.get("/{task_id}", response_model=OcrTaskResponse)
def get_ocr_task(
    task_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "view")
    task = _get_task(db, family_id, task_id)
    _check_access(db, current_user, task, scope)
    return task


@router.post("/{task_id}/process", response_model=OcrTaskMessageResponse)
def run_ocr_task(
    task_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "create")
    task = _get_task(db, family_id, task_id)
    _check_access(db, current_user, task, scope)
    if task.status not in {"queued", "failed"}:
        raise HTTPException(status_code=409, detail="目前任務狀態不可執行")
    if task.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=409, detail="已達最大 OCR 重試次數")
    task.status = "processing"
    task.attempts += 1
    task.started_at = datetime.now(timezone.utc)
    task.completed_at = None
    task.error_code = None
    task.error_message = None
    db.commit()  # Persist lease before making an external provider request.
    task = db.query(OcrTask).filter(OcrTask.id == task_id, OcrTask.family_id == family_id).first()
    process_task(db, task)
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="update", entity_type="ocr_task", entity_id=task.id,
        new_values={"status": task.status, "attempts": task.attempts},
        description="執行 OCR 圖片辨識",
    )
    db.commit()
    db.refresh(task)
    return {"success": True, "message": "OCR 辨識作業已完成，請核對擷取內容", "task": task}


@router.post("/{task_id}/retry", response_model=OcrTaskMessageResponse)
def retry_ocr_task(
    task_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "retry")
    task = _get_task(db, family_id, task_id)
    _check_access(db, current_user, task, scope)
    if task.status != "failed":
        raise HTTPException(status_code=409, detail="只有失敗的 OCR 任務可以重試")
    if task.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=409, detail="已達最大 OCR 重試次數")
    task.status = "queued"
    task.error_code = None
    task.error_message = None
    task.completed_at = None
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="update", entity_type="ocr_task", entity_id=task.id,
        new_values={"status": "queued"}, description="重新排入 OCR 辨識佇列",
    )
    db.commit()
    db.refresh(task)
    return {"success": True, "message": "OCR 任務已重新排入佇列", "task": task}


@router.post("/{task_id}/confirm", response_model=OcrTaskMessageResponse)
def confirm_ocr_task(
    task_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user, family_id, "confirm")
    task = _get_task(db, family_id, task_id)
    _check_access(db, current_user, task, scope)
    if task.status != "succeeded" or not task.extracted_text:
        raise HTTPException(status_code=409, detail="只有成功辨識且有文字內容的任務可以確認")
    task.status = "confirmed"
    task.confirmed_at = datetime.now(timezone.utc)
    task.confirmed_by = current_user.id
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="confirm", entity_type="ocr_task", entity_id=task.id,
        new_values={"status": "confirmed", "suggested_fields": task.suggested_fields},
        description="人工確認 OCR 辨識結果",
    )
    db.commit()
    db.refresh(task)
    return {"success": True, "message": "OCR 結果已確認；尚未建立或修改正式帳單", "task": task}
