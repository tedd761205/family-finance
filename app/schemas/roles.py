"""角色與成員角色指派 API schemas。"""
from pydantic import BaseModel, Field


class RoleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    permission_codes: list[str] = Field(default_factory=list, max_length=200)
    data_scopes: dict[str, str] = Field(default_factory=dict)


class MemberRoleAssignment(BaseModel):
    role_ids: list[int] = Field(min_length=1, max_length=30)
