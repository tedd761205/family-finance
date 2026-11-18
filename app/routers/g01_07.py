import csv
import hashlib
import io
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.bill import Bill
from app.models.export_template import ExportTemplate, ExportTemplateVersion, ExportSchedule, ExportRun
from app.models.family_member import FamilyMember
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.g01_07 import (
    ExportTemplateCreate, ExportTemplateUpdate, ExportTemplateItem,
    ExportTemplateListResponse, ExportScheduleCreate, ExportScheduleItem,
    ExportRunItem, NotificationItem, NotificationListResponse,
)
from app.services.audit_log import add_audit_log
from app.services import attachment_storage

router = APIRouter(tags=["家庭協作、通知與匯出"])
TAIPEI = ZoneInfo("Asia/Taipei")


def _authorize(db: Session, user_id: int, family_id: int, permission: str, resource: str | None = None) -> str | None:
    try:
        _, roles = require_permission(db, user_id, family_id, permission)
        return require_data_scope(db, roles, family_id, resource) if resource else None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _notify(db: Session, *, family_id: int, recipient_user_id: int, actor_user_id: int | None,
            notification_type: str, title: str, body: str | None = None, payload: dict | None = None):
    item = Notification(
        family_id=family_id, recipient_user_id=recipient_user_id,
        actor_user_id=actor_user_id, notification_type=notification_type,
        title=title, body=body, payload=payload,
    )
    db.add(item)
    return item


def _notify_family_members(db: Session, *, family_id: int, actor_user_id: int,
                           notification_type: str, title: str, body: str, payload: dict):
    members = db.query(FamilyMember).filter(
        FamilyMember.family_id == family_id, FamilyMember.status == "active",
    ).all()
    for member in members:
        if member.user_id != actor_user_id:
            _notify(db, family_id=family_id, recipient_user_id=member.user_id,
                    actor_user_id=actor_user_id, notification_type=notification_type,
                    title=title, body=body, payload=payload)


def _template(db: Session, family_id: int, template_id: int, lock: bool = False) -> ExportTemplate:
    query = db.query(ExportTemplate).filter(
        ExportTemplate.id == template_id, ExportTemplate.family_id == family_id,
    )
    if lock:
        query = query.with_for_update()
    item = query.first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    return item


def _snapshot(template: ExportTemplate) -> dict:
    return {
        "name": template.name, "description": template.description,
        "config": template.config, "version": template.version,
        "status": template.status,
    }


def _next_run(frequency: str, hour: int, minute: int, weekday: int | None, monthday: int | None) -> datetime:
    now_local = datetime.now(TAIPEI)
    candidate_date = now_local.date()
    candidate = datetime.combine(candidate_date, time(hour, minute), TAIPEI)
    if candidate <= now_local:
        candidate_date += timedelta(days=1)
    if frequency == "daily":
        pass
    elif frequency == "weekly":
        days = (weekday - candidate_date.weekday()) % 7
        candidate_date += timedelta(days=days)
        candidate = datetime.combine(candidate_date, time(hour, minute), TAIPEI)
        if candidate <= now_local:
            candidate_date += timedelta(days=7)
    else:
        day = monthday or 1
        year, month = candidate_date.year, candidate_date.month
        if candidate_date.day > day or (candidate_date.day == day and candidate <= now_local):
            month += 1
            if month > 12:
                year, month = year + 1, 1
        candidate_date = date(year, month, day)
    candidate = datetime.combine(candidate_date, time(hour, minute), TAIPEI)
    return candidate.astimezone(timezone.utc)


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return format(value, "f")
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _render_export(db: Session, family_id: int, run: ExportRun, user_id: int | None, scope: str) -> bytes:
    config = run.template_snapshot["config"]
    dataset = config["dataset"]
    columns = config["columns"]
    if dataset == "transactions":
        query = db.query(Transaction).filter(
            Transaction.family_id == family_id, Transaction.is_voided.is_(False),
        )
        if scope == "own":
            query = query.filter(Transaction.created_by == user_id)
        rows = query.order_by(Transaction.transaction_date.asc(), Transaction.id.asc()).limit(50000).all()
        mapping = {
            "id": lambda x: x.id, "occurred_on": lambda x: x.transaction_date,
            "type": lambda x: x.transaction_type, "amount": lambda x: x.amount,
            "currency_code": lambda x: x.currency_code, "description": lambda x: x.description,
            "category_id": lambda x: x.category_id, "account_id": lambda x: x.account_id,
            "created_by": lambda x: x.created_by,
        }
    else:
        query = db.query(Bill).filter(Bill.family_id == family_id, Bill.is_voided.is_(False))
        if scope == "own":
            query = query.filter(Bill.created_by == user_id)
        rows = query.order_by(Bill.bill_date.asc(), Bill.id.asc()).limit(50000).all()
        mapping = {
            "id": lambda x: x.id, "bill_number": lambda x: x.bill_number,
            "title": lambda x: x.title, "bill_date": lambda x: x.bill_date,
            "due_date": lambda x: x.due_date, "original_amount": lambda x: x.original_amount,
            "currency_code": lambda x: x.currency_code, "status": lambda x: "voided" if x.is_voided else "active",
            "created_by": lambda x: x.created_by,
        }
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_cell(mapping[column](row)) for column in columns])
    return output.getvalue().encode("utf-8-sig")


@router.get("/notifications", response_model=NotificationListResponse, summary="查詢本人家庭通知")
def list_notifications(
    family_id: int = Query(..., gt=0), unread_only: bool = False,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "notifications.view")
    query = db.query(Notification).filter(
        Notification.family_id == family_id,
        Notification.recipient_user_id == current_user.id,
    )
    total = query.count()
    unread = query.filter(Notification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "unread": unread, "notifications": items}


@router.post("/notifications/{notification_id}/read", response_model=NotificationItem, summary="標記通知已讀")
def mark_notification_read(
    notification_id: int, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "notifications.view")
    item = db.query(Notification).filter(
        Notification.id == notification_id, Notification.family_id == family_id,
        Notification.recipient_user_id == current_user.id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此通知")
    if item.read_at is None:
        item.read_at = datetime.now(timezone.utc)
        add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                      action="read", entity_type="notification", entity_id=item.id,
                      description="標記家庭通知為已讀")
        db.commit()
        db.refresh(item)
    return item


@router.get("/exports/templates", response_model=ExportTemplateListResponse, summary="查詢家庭共用匯出範本")
def list_export_templates(
    family_id: int = Query(..., gt=0), status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.view", "exports")
    query = db.query(ExportTemplate).filter(ExportTemplate.family_id == family_id)
    if scope == "own":
        query = query.filter(ExportTemplate.created_by == current_user.id)
    if status_filter in {"draft", "published", "disabled"}:
        query = query.filter(ExportTemplate.status == status_filter)
    items = query.order_by(ExportTemplate.updated_at.desc(), ExportTemplate.id.desc()).all()
    return {"success": True, "total": len(items), "templates": items}


@router.post("/exports/templates", response_model=ExportTemplateItem, status_code=201, summary="建立家庭共用匯出範本")
def create_export_template(
    body: ExportTemplateCreate, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "exports.create", "exports")
    template = ExportTemplate(
        family_id=family_id, name=body.name.strip(), description=body.description,
        config=body.config, status="draft", version=1,
        created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(template)
    db.flush()
    db.add(ExportTemplateVersion(
        family_id=family_id, template_id=template.id, version=1,
        name=template.name, description=template.description,
        config=template.config, status="draft", created_by=current_user.id,
    ))
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="create", entity_type="export_template", entity_id=template.id,
                  new_values=_snapshot(template), description="建立家庭共用匯出範本草稿")
    db.commit()
    db.refresh(template)
    return template


@router.put("/exports/templates/{template_id}", response_model=ExportTemplateItem, summary="更新匯出範本（樂觀鎖定）")
def update_export_template(
    template_id: int, body: ExportTemplateUpdate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "exports.update", "exports")
    template = _template(db, family_id, template_id, lock=True)
    if _authorize(db, current_user.id, family_id, "exports.update", "exports") == "own" and template.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    if template.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "EXPORT_TEMPLATE_VERSION_CONFLICT",
            "message": "範本已被其他家庭成員更新，請檢視差異並以最新版本手動合併後重試",
            "expected_version": body.expected_version,
            "latest_version": template.version,
            "latest": _snapshot(template),
        })
    old = _snapshot(template)
    template.name = body.name.strip()
    template.description = body.description
    template.config = body.config
    template.version += 1
    template.status = "draft"
    template.updated_by = current_user.id
    db.add(ExportTemplateVersion(
        family_id=family_id, template_id=template.id, version=template.version,
        name=template.name, description=template.description,
        config=template.config, status="draft", created_by=current_user.id,
    ))
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="update", entity_type="export_template", entity_id=template.id,
                  old_values=old, new_values=_snapshot(template),
                  description="更新匯出範本；需重新發布才會套用於排程")
    db.commit()
    db.refresh(template)
    return template


@router.post("/exports/templates/{template_id}/publish", response_model=ExportTemplateItem, summary="發布匯出範本版本")
def publish_export_template(
    template_id: int, expected_version: int = Query(..., ge=1),
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "exports.publish", "exports")
    template = _template(db, family_id, template_id, lock=True)
    if _authorize(db, current_user.id, family_id, "exports.publish", "exports") == "own" and template.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    if template.version != expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "EXPORT_TEMPLATE_VERSION_CONFLICT",
            "expected_version": expected_version, "latest_version": template.version,
            "latest": _snapshot(template),
        })
    if template.status == "disabled":
        raise HTTPException(status_code=409, detail="停用中的範本不可直接發布，請先建立新草稿版本")
    template.status = "published"
    version = db.query(ExportTemplateVersion).filter(
        ExportTemplateVersion.family_id == family_id,
        ExportTemplateVersion.template_id == template.id,
        ExportTemplateVersion.version == template.version,
    ).with_for_update().first()
    if version is not None:
        version.status = "published"
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="publish", entity_type="export_template", entity_id=template.id,
                  new_values=_snapshot(template), description="發布家庭共用匯出範本版本")
    _notify_family_members(
        db, family_id=family_id, actor_user_id=current_user.id,
        notification_type="export_template.published", title="家庭匯出範本已更新",
        body=f"家庭成員已發布範本「{template.name}」第 {template.version} 版。",
        payload={"template_id": template.id, "version": template.version},
    )
    db.commit()
    db.refresh(template)
    return template


@router.get("/exports/templates/{template_id}/versions", summary="查詢匯出範本版本歷程")
def list_export_template_versions(
    template_id: int, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.view", "exports")
    template = _template(db, family_id, template_id)
    if scope == "own" and template.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    versions = db.query(ExportTemplateVersion).filter(
        ExportTemplateVersion.family_id == family_id,
        ExportTemplateVersion.template_id == template_id,
    ).order_by(ExportTemplateVersion.version.desc()).all()
    return {"success": True, "versions": versions}


@router.post("/exports/schedules", response_model=ExportScheduleItem, status_code=201, summary="建立定期匯出排程")
def create_export_schedule(
    body: ExportScheduleCreate, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "exports.schedule", "exports")
    template = _template(db, family_id, body.template_id)
    if _authorize(db, current_user.id, family_id, "exports.schedule", "exports") == "own" and template.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    if template.status != "published":
        raise HTTPException(status_code=409, detail="只有已發布的範本可以建立定期匯出")
    next_run = _next_run(body.frequency, body.local_hour, body.local_minute, body.weekday, body.monthday)
    schedule = ExportSchedule(
        family_id=family_id, template_id=template.id, name=body.name.strip(),
        frequency=body.frequency, weekday=body.weekday, monthday=body.monthday,
        local_hour=body.local_hour, local_minute=body.local_minute,
        timezone="Asia/Taipei", enabled=body.enabled, next_run_at=next_run,
        created_by=current_user.id,
    )
    db.add(schedule)
    db.flush()
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="create", entity_type="export_schedule", entity_id=schedule.id,
                  new_values={"template_id": template.id, "frequency": body.frequency,
                              "timezone": "Asia/Taipei", "next_run_at": next_run},
                  description="建立定期匯出排程")
    _notify_family_members(
        db, family_id=family_id, actor_user_id=current_user.id,
        notification_type="export_schedule.created", title="家庭定期匯出排程已建立",
        body=f"已建立排程「{schedule.name}」，時區為 Asia/Taipei。",
        payload={"schedule_id": schedule.id, "template_id": template.id},
    )
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/exports/schedules", summary="查詢定期匯出排程")
def list_export_schedules(
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.view", "exports")
    query = db.query(ExportSchedule).filter(ExportSchedule.family_id == family_id)
    if scope == "own":
        query = query.filter(ExportSchedule.created_by == current_user.id)
    items = query.order_by(ExportSchedule.created_at.desc()).all()
    return {"success": True, "total": len(items), "schedules": items}


@router.post("/exports/schedules/{schedule_id}/disable", response_model=ExportScheduleItem, summary="停用定期匯出排程")
def disable_export_schedule(
    schedule_id: int, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "exports.schedule", "exports")
    item = db.query(ExportSchedule).filter(
        ExportSchedule.id == schedule_id, ExportSchedule.family_id == family_id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出排程")
    item.enabled = False
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="disable", entity_type="export_schedule", entity_id=item.id,
                  new_values={"enabled": False}, description="停用定期匯出排程")
    db.commit()
    db.refresh(item)
    return item


@router.post("/exports/templates/{template_id}/run", response_model=ExportRunItem, status_code=201, summary="立即執行匯出")
def run_export(
    template_id: int, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.create", "exports")
    template = _template(db, family_id, template_id)
    if scope == "own" and template.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到此家庭匯出範本")
    if template.status != "published":
        raise HTTPException(status_code=409, detail="只有已發布的匯出範本可以執行")
    dataset = template.config.get("dataset")
    data_permission = "transactions.view" if dataset == "transactions" else "bills.view"
    data_resource = dataset
    data_scope = _authorize(db, current_user.id, family_id, data_permission, data_resource)
    effective_scope = "own" if scope == "own" or data_scope == "own" else "family"
    run = ExportRun(
        family_id=family_id, template_id=template.id, template_version=template.version,
        template_snapshot={**_snapshot(template), "data_scope": effective_scope}, status="running", requested_by=current_user.id,
    )
    db.add(run)
    db.flush()
    try:
        content = _render_export(db, family_id, run, current_user.id, effective_scope)
        digest = hashlib.sha256(content).hexdigest()
        key = f"family-{family_id}/exports/{uuid.uuid4().hex}.csv"
        attachment_storage.upload_object(key, content, "text/csv; charset=utf-8", digest)
        run.object_key = key
        run.sha256 = digest
        run.file_size = len(content)
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        _notify(db, family_id=family_id, recipient_user_id=current_user.id, actor_user_id=current_user.id,
                notification_type="export.completed", title="家庭資料匯出完成",
                body=f"匯出範本「{template.name}」已完成，可至匯出紀錄下載。",
                payload={"template_id": template.id, "run_id": run.id})
        add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                      action="export", entity_type="export_run", entity_id=run.id,
                      new_values={"template_id": template.id, "template_version": template.version,
                                  "sha256": digest, "file_size": len(content)},
                      description="執行家庭資料匯出")
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        try:
            if "key" in locals():
                attachment_storage.delete_object(key)
        except Exception:
            pass
        raise


@router.get("/exports/runs", summary="查詢匯出執行紀錄")
def list_export_runs(
    family_id: int = Query(..., gt=0), skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.view", "exports")
    query = db.query(ExportRun).filter(ExportRun.family_id == family_id)
    if scope == "own":
        query = query.filter(ExportRun.requested_by == current_user.id)
    total = query.count()
    items = query.order_by(ExportRun.created_at.desc(), ExportRun.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "runs": items}


@router.get("/exports/runs/{run_id}/download", summary="下載匯出檔案")
def download_export_run(
    run_id: int, family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.download", "exports")
    run = db.query(ExportRun).filter(
        ExportRun.id == run_id, ExportRun.family_id == family_id,
    ).first()
    if run is None or run.status != "succeeded" or not run.object_key:
        raise HTTPException(status_code=404, detail="找不到可下載的匯出檔案")
    if scope == "own" and run.requested_by != current_user.id:
        raise HTTPException(status_code=404, detail="找不到可下載的匯出檔案")
    dataset = run.template_snapshot["config"]["dataset"]
    data_permission = "transactions.view" if dataset == "transactions" else "bills.view"
    data_scope = _authorize(db, current_user.id, family_id, data_permission, dataset)
    original_scope = run.template_snapshot.get("data_scope", "family")
    if original_scope == "family" and data_scope != "family":
        raise HTTPException(status_code=403, detail="目前資料範圍已縮小，無法下載先前包含全家庭資料的匯出檔案")
    if data_scope == "own" and run.requested_by != current_user.id:
        raise HTTPException(status_code=404, detail="目前權限不允許下載此家庭匯出檔案")
    content = attachment_storage.download_object(run.object_key)
    if hashlib.sha256(content).hexdigest() != run.sha256:
        raise HTTPException(status_code=500, detail="匯出檔案完整性驗證失敗")
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id,
                  action="download", entity_type="export_run", entity_id=run.id,
                  new_values={"sha256": run.sha256}, description="下載家庭匯出檔案")
    db.commit()
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="family-export-{run.id}.csv"',
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/exports/dashboard", summary="匯出管理儀表板統計")
def export_dashboard(
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "exports.dashboard", "exports")
    query = db.query(ExportRun).filter(ExportRun.family_id == family_id)
    if scope == "own":
        query = query.filter(ExportRun.requested_by == current_user.id)
    runs = query.order_by(ExportRun.created_at.desc()).limit(1000).all()
    counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "revoked": 0}
    daily = {}
    for run in runs:
        counts[run.status] = counts.get(run.status, 0) + 1
        day = run.created_at.astimezone(TAIPEI).date().isoformat()
        daily[day] = daily.get(day, 0) + 1
    failed = [ExportRunItem.model_validate(x).model_dump(mode="json") for x in runs if x.status == "failed"][:20]
    return {
        "success": True, "timezone": "Asia/Taipei", "total": len(runs),
        "status_counts": counts,
        "daily_trend": [{"date": k, "count": v} for k, v in sorted(daily.items())],
        "recent_failures": failed,
    }



def process_due_exports(db: Session, *, limit: int = 25) -> dict:
    """Worker entry point. Each due schedule is re-authorized before any export data is read."""
    now = datetime.now(timezone.utc)
    schedules = db.query(ExportSchedule).filter(
        ExportSchedule.enabled.is_(True),
        ExportSchedule.next_run_at <= now,
    ).order_by(ExportSchedule.next_run_at.asc(), ExportSchedule.id.asc()).with_for_update(skip_locked=True).limit(limit).all()
    result = {"checked": 0, "succeeded": 0, "failed": 0, "disabled": 0}
    for schedule in schedules:
        result["checked"] += 1
        template = None
        published = None
        key = None
        try:
            template = _template(db, schedule.family_id, schedule.template_id, lock=True)
            published = db.query(ExportTemplateVersion).filter(
                ExportTemplateVersion.family_id == schedule.family_id,
                ExportTemplateVersion.template_id == template.id,
                ExportTemplateVersion.status == "published",
            ).order_by(ExportTemplateVersion.version.desc()).first()
            if published is None:
                schedule.enabled = False
                _notify(db, family_id=schedule.family_id, recipient_user_id=schedule.created_by,
                        actor_user_id=None, notification_type="export_schedule.disabled",
                        title="定期匯出已暫停", body="目前沒有可用的已發布範本版本，排程已自動停用。",
                        payload={"schedule_id": schedule.id})
                add_audit_log(db, family_id=schedule.family_id, actor_user_id=None,
                              action="disable", entity_type="export_schedule", entity_id=schedule.id,
                              new_values={"enabled": False}, description="排程因無已發布範本而自動停用")
                result["disabled"] += 1
                db.commit()
                continue

            dataset = published.config.get("dataset")
            data_permission = "transactions.view" if dataset == "transactions" else "bills.view"
            try:
                _, schedule_roles = require_permission(
                    db, schedule.created_by, schedule.family_id, "exports.schedule",
                )
                require_permission(db, schedule.created_by, schedule.family_id, "exports.create")
                _, data_roles = require_permission(db, schedule.created_by, schedule.family_id, data_permission)
                data_scope = require_data_scope(db, data_roles, schedule.family_id, dataset)
                if data_scope not in {"own", "family"}:
                    raise PermissionError("匯出資料範圍已失效")
            except PermissionError:
                schedule.enabled = False
                _notify(db, family_id=schedule.family_id, recipient_user_id=schedule.created_by,
                        actor_user_id=None, notification_type="export_schedule.permission_revoked",
                        title="定期匯出已暫停：權限變更",
                        body="排程建立者已不具備執行匯出所需的家庭成員資格或權限，因此排程已停用。",
                        payload={"schedule_id": schedule.id})
                add_audit_log(db, family_id=schedule.family_id, actor_user_id=None,
                              action="disable", entity_type="export_schedule", entity_id=schedule.id,
                              new_values={"enabled": False, "reason": "permission_revoked"},
                              description="排程執行前重新驗證權限失敗，已自動停用")
                result["disabled"] += 1
                db.commit()
                continue

            snapshot = {
                "name": published.name, "description": published.description,
                "config": published.config, "version": published.version,
                "status": "published", "data_scope": data_scope,
            }
            run = ExportRun(
                family_id=schedule.family_id, template_id=template.id,
                schedule_id=schedule.id, requested_by=schedule.created_by,
                template_version=published.version, template_snapshot=snapshot,
                status="running",
            )
            db.add(run)
            db.flush()
            content = _render_export(db, schedule.family_id, run, schedule.created_by, data_scope)
            digest = hashlib.sha256(content).hexdigest()
            key = f"family-{schedule.family_id}/exports/{uuid.uuid4().hex}.csv"
            attachment_storage.upload_object(key, content, "text/csv; charset=utf-8", digest)
            run.object_key = key
            run.sha256 = digest
            run.file_size = len(content)
            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            schedule.last_run_at = now
            schedule.next_run_at = _next_run(
                schedule.frequency, schedule.local_hour, schedule.local_minute,
                schedule.weekday, schedule.monthday,
            )
            _notify(db, family_id=schedule.family_id, recipient_user_id=schedule.created_by,
                    actor_user_id=None, notification_type="export.completed",
                    title="定期家庭資料匯出完成",
                    body=f"排程「{schedule.name}」已完成，使用範本最新已發布版本 {published.version}。",
                    payload={"schedule_id": schedule.id, "run_id": run.id, "template_version": published.version})
            add_audit_log(db, family_id=schedule.family_id, actor_user_id=None,
                          action="scheduled_export", entity_type="export_run", entity_id=run.id,
                          new_values={"schedule_id": schedule.id, "template_version": published.version,
                                      "sha256": digest, "file_size": len(content)},
                          description="定期匯出成功；執行時重新驗證權限並使用最新已發布範本")
            db.commit()
            result["succeeded"] += 1
        except Exception as exc:
            db.rollback()
            if key is not None:
                try:
                    attachment_storage.delete_object(key)
                except Exception:
                    pass
            current = db.query(ExportSchedule).filter(
                ExportSchedule.id == schedule.id, ExportSchedule.family_id == schedule.family_id,
            ).with_for_update().first()
            if current is not None:
                if template is not None:
                    failed = ExportRun(
                        family_id=current.family_id, template_id=current.template_id,
                        schedule_id=current.id, requested_by=current.created_by,
                        template_version=published.version if published is not None else template.version,
                        template_snapshot={
                            "name": published.name if published is not None else template.name,
                            "description": published.description if published is not None else template.description,
                            "config": published.config if published is not None else template.config,
                            "version": published.version if published is not None else template.version,
                            "status": "published" if published is not None else template.status,
                            "data_scope": "own",
                        },
                        status="failed", error_code=type(exc).__name__[:80],
                        completed_at=datetime.now(timezone.utc),
                    )
                    db.add(failed)
                _notify(db, family_id=current.family_id, recipient_user_id=current.created_by,
                        actor_user_id=None, notification_type="export.failed",
                        title="定期家庭資料匯出失敗",
                        body="排程執行失敗，請檢查範本、權限及儲存服務設定。",
                        payload={"schedule_id": current.id})
                add_audit_log(db, family_id=current.family_id, actor_user_id=None,
                              action="scheduled_export_failed", entity_type="export_schedule", entity_id=current.id,
                              new_values={"error_code": type(exc).__name__[:80]},
                              description="定期匯出執行失敗")
                current.last_run_at = now
                current.next_run_at = _next_run(
                    current.frequency, current.local_hour, current.local_minute,
                    current.weekday, current.monthday,
                )
                db.commit()
            result["failed"] += 1
    return result
