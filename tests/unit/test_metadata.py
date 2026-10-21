from typing import cast

from sqlalchemy import Table

from app.modules.users.models import User


def test_user_table_matches_the_initial_migration() -> None:
    table = cast(Table, User.__table__)
    assert table.name == "users"
    assert set(table.columns.keys()) == {
        "id",
        "display_name",
        "email",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert table.primary_key.name == "pk_users"
    unique_names = {constraint.name for constraint in table.constraints}
    assert "uq_users_email" in unique_names
    assert "password" not in table.columns
