from app.core.passwords import hash_password, verify_password


def test_hash_is_not_the_password_and_rejects_a_wrong_value() -> None:
    stored = hash_password("password123")
    assert stored != "password123"
    assert verify_password("password123", stored) is True
    assert verify_password("password124", stored) is False
    assert verify_password("password123", "not-a-hash") is False
