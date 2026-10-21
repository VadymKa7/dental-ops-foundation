import pytest
from pydantic import ValidationError

from app.modules.users.schemas import UserCreate


def test_display_name_and_email_are_stripped() -> None:
    payload = UserCreate(display_name="  Ada Lovelace  ", email="  Ada@Example.com  ")
    assert payload.display_name == "Ada Lovelace"
    # EmailStr lowercases the domain. The service lowercases the whole address.
    assert payload.email == "Ada@example.com"
    assert payload.is_active is True


def test_blank_display_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(display_name="   ", email="ada@example.com")


def test_display_name_length_limits() -> None:
    UserCreate(display_name="A" * 120, email="ada@example.com")
    with pytest.raises(ValidationError):
        UserCreate(display_name="A" * 121, email="ada@example.com")


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(display_name="Ada", email="not-an-email")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "display_name": "Ada",
                "email": "ada@example.com",
                "password": "not-stored",
            }
        )
