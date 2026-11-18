from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    bill_id: int | None
    transaction_id: int | None
    original_filename: str
    content_type: str
    file_size: int
    sha256: str
    is_voided: bool
    voided_at: datetime | None
    void_reason: str | None
    created_by: int
    created_at: datetime


class AttachmentListResponse(BaseModel):
    success: bool = True
    total: int
    attachments: list[AttachmentResponse]


class AttachmentVoidRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AttachmentMessageResponse(BaseModel):
    success: bool = True
    message: str
    attachment: AttachmentResponse
