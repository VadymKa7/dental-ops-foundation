"""HTTP contracts for users. These types never leave the API layer as ORM rows."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=120)
    email: EmailStr = Field(max_length=320)
    is_active: bool = True


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int
