"""HTTP contracts for users. These types never leave the API layer as ORM rows."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

RoleName = Literal["patient", "admin", "doctor", "reception"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=320)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")
    role: RoleName = "patient"
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool = True

    @field_validator("display_name", "email", mode="before")
    @classmethod
    def strip_identity(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def compact_phone(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return None
        return "".join(character for character in stripped if character not in " -()")

    @model_validator(mode="after")
    def password_matches_role(self) -> Self:
        if self.role == "patient" and self.password is not None:
            raise ValueError("Patients cannot have a password.")
        if self.role != "patient" and self.password is None:
            raise ValueError("Staff accounts require a password.")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str
    phone: str | None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int
