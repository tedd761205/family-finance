"""家庭稽核紀錄唯讀查詢 API。"""
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import audit_log_query_params

router = APIRouter(prefix="/families", tags=["Audit Logs"])
TAIPEI_TZ = timezone(timedelta(hours=8))


@router.get("/{family_id}/audit-logs")
def list_family_audit_logs(
    family_id: int,
    filters: dict = Depends(audit_log_query_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """依角色資料範圍查詢家庭稽核紀錄；此 API 僅供讀取。"""
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="此帳號已停用，無法查詢稽核紀錄")
    try:
        _, roles = require_permission(
            db=db, user_id=current_user.id, family_id=family_id,
            permission_code="audit_logs.view",
        )
        scope = require_data_scope(
            db=db, roles=roles, family_id=family_id, resource="audit_logs",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    start_date = filters["start_date"]
    end_date = filters["end_date"]
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="開始日期不可晚於結束日期")

    query = (
        db.query(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .filter(AuditLog.family_id == family_id)
    )
    if scope == "own":
        query = query.filter(AuditLog.actor_user_id == current_user.id)
    if start_date:
        start_at = datetime.combine(start_date, time.min, tzinfo=TAIPEI_TZ)
        query = query.filter(AuditLog.created_at >= start_at)
    if end_date:
        end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=TAIPEI_TZ)
        query = query.filter(AuditLog.created_at < end_at)
    if filters["action"]:
        query = query.filter(AuditLog.action == filters["action"].strip())
    if filters["entity_type"]:
        query = query.filter(AuditLog.entity_type == filters["entity_type"].strip())

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(filters["offset"])
        .limit(filters["limit"])
        .all()
    )
    records = []
    for log, actor in rows:
        records.append({
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "actor_user_id": log.actor_user_id,
            "actor_name": actor.display_name if actor else ("系統" if log.actor_user_id is None else "已停用帳號"),
            "actor_email": actor.email if actor else None,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "description": log.description,
            "old_values": log.old_values,
            "new_values": log.new_values,
        })
    return {
        "success": True,
        "scope": scope,
        "total": total,
        "limit": filters["limit"],
        "offset": filters["offset"],
        "records": records,
    }
