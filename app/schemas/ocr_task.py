from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OcrTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    attachment_id: int
    status: str
    provider: str
    attempts: int
    extracted_text: str | None
    suggested_fields: dict | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    created_by: int
    created_at: datetime


class OcrTaskListResponse(BaseModel):
    success: bool = True
    total: int
    tasks: list[OcrTaskResponse]


class OcrTaskMessageResponse(BaseModel):
    success: bool = True
    message: str
    task: OcrTaskResponse
