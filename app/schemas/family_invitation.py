from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class FamilyInvitationCreate(BaseModel):
    email: EmailStr = Field(description="受邀家人的 Google 帳號 Email")


class FamilyInvitationCreateResponse(BaseModel):
    success: bool
    invitation_id: int
    family_id: int
    email: str
    status: str
    expires_at: datetime
    invite_url: str


class FamilyInvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class FamilyInvitationActionResponse(BaseModel):
    success: bool
    message: str
    family_id: int | None = None
    family_member_id: int | None = None
