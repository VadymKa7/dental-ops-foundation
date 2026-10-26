from typing import cast

from sqlalchemy import Table

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.users.models import User


def test_user_table_matches_the_model() -> None:
    table = cast(Table, User.__table__)
    assert table.name == "users"
    assert set(table.columns.keys()) == {
        "id",
        "display_name",
        "email",
        "phone",
        "role",
        "password_hash",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert table.primary_key.name == "pk_users"
    unique_names = {constraint.name for constraint in table.constraints}
    assert "uq_users_email" in unique_names
    assert "ck_users_role" in unique_names
    assert "password" not in table.columns


def test_session_and_audit_tables_keep_secrets_out() -> None:
    sessions = cast(Table, AuthSession.__table__)
    audit = cast(Table, AuditEvent.__table__)
    assert set(sessions.columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "expires_at",
        "revoked_at",
        "created_at",
    }
    assert "token" not in sessions.columns
    assert sessions.primary_key.name == "pk_sessions"
    session_names = {constraint.name for constraint in sessions.constraints}
    assert "uq_sessions_token_hash" in session_names
    assert "fk_sessions_user_id_users" in session_names
    assert set(audit.columns.keys()) == {
        "id",
        "actor_user_id",
        "action",
        "resource_type",
        "resource_id",
        "created_at",
    }
    assert "email" not in audit.columns
    assert audit.primary_key.name == "pk_audit_events"
    audit_names = {constraint.name for constraint in audit.constraints}
    assert "fk_audit_events_actor_user_id_users" in audit_names
