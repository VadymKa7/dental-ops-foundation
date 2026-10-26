import pytest
from pydantic import ValidationError

from app.modules.users.schemas import UserCreate


def test_display_name_and_email_are_stripped() -> None:
    payload = UserCreate(display_name="  Ada Lovelace  ", email="  Ada@Example.com  ")
    assert payload.display_name == "Ada Lovelace"
    # EmailStr lowercases the domain. The service lowercases the whole address.
    assert payload.email == "Ada@example.com"
    assert payload.phone is None
    assert payload.role == "patient"
    assert payload.password is None
    assert payload.is_active is True


def test_blank_display_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(display_name="   ", email="ada@example.com")


def test_display_name_length_limits() -> None:
    UserCreate(display_name="Al", email="ada@example.com")
    UserCreate(display_name="A" * 120, email="ada@example.com")
    with pytest.raises(ValidationError):
        UserCreate(display_name="A", email="ada@example.com")
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
                "nickname": "not-stored",
            }
        )


def test_phone_is_optional_and_compacted() -> None:
    payload = UserCreate(
        display_name="Ada",
        email="ada@example.com",
        phone=" +380 50 123 4567 ",
    )
    assert payload.phone == "+380501234567"
    with pytest.raises(ValidationError):
        UserCreate(display_name="Ada", email="ada@example.com", phone="123")


def test_patient_password_is_rejected_and_staff_password_is_required() -> None:
    with pytest.raises(ValidationError):
        UserCreate(display_name="Ada", email="ada@example.com", password="password123")
    with pytest.raises(ValidationError):
        UserCreate(display_name="Ada", email="ada@example.com", role="doctor")
    payload = UserCreate(
        display_name="Ada",
        email="ada@example.com",
        role="doctor",
        password="  password123  ",
    )
    assert payload.role == "doctor"
    assert payload.password == "  password123  "
