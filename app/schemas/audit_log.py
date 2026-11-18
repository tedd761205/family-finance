"""稽核紀錄查詢參數。"""
from datetime import date
from fastapi import Query


def audit_log_query_params(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    action: str | None = Query(default=None, max_length=50),
    entity_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return {
        "start_date": start_date,
        "end_date": end_date,
        "action": action,
        "entity_type": entity_type,
        "limit": limit,
        "offset": offset,
    }
