from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_id: int
    notification_type: str
    title: str
    body: str | None
    payload: dict | None
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    success: bool
    total: int
    unread: int
    notifications: list[NotificationItem]


class ExportTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    config: dict

    @field_validator("config")
    @classmethod
    def validate_config(cls, value):
        dataset = value.get("dataset")
        columns = value.get("columns")
        allowed = {
            "transactions": {"id", "occurred_on", "type", "amount", "currency_code", "description", "category_id", "account_id", "created_by"},
            "bills": {"id", "bill_number", "title", "bill_date", "due_date", "original_amount", "currency_code", "status", "created_by"},
        }
        if dataset not in allowed or not isinstance(columns, list) or not columns:
            raise ValueError("匯出範本必須指定 transactions 或 bills，且至少選擇一個欄位")
        if len(columns) > 20 or len(set(columns)) != len(columns) or any(c not in allowed[dataset] for c in columns):
            raise ValueError("匯出欄位包含不支援或重複的欄位")
        return value


class ExportTemplateUpdate(ExportTemplateCreate):
    expected_version: int = Field(ge=1)


class ExportTemplateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_id: int
    name: str
    description: str | None
    config: dict
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ExportTemplateListResponse(BaseModel):
    success: bool
    total: int
    templates: list[ExportTemplateItem]


class ExportScheduleCreate(BaseModel):
    template_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    frequency: str
    weekday: int | None = Field(default=None, ge=0, le=6)
    monthday: int | None = Field(default=None, ge=1, le=28)
    local_hour: int = Field(default=8, ge=0, le=23)
    local_minute: int = Field(default=0, ge=0, le=59)
    enabled: bool = True

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value):
        if value not in {"daily", "weekly", "monthly"}:
            raise ValueError("frequency 僅接受 daily、weekly 或 monthly")
        return value


class ExportScheduleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_id: int
    template_id: int
    name: str
    frequency: str
    weekday: int | None
    monthday: int | None
    local_hour: int
    local_minute: int
    timezone: str
    enabled: bool
    next_run_at: datetime
    last_run_at: datetime | None


class ExportRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_id: int
    template_id: int
    schedule_id: int | None
    template_version: int
    status: str
    sha256: str | None
    file_size: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
