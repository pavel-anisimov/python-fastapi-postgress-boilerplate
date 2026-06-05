from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from app.models.role import Role, UserRole
from app.models.token import EmailToken
from app.models.user import User
from app.routers import auth
from app.schemas.auth import EmailIn, RefreshIn, RegisterIn, ResetPasswordIn
from app.security import create_access_token, create_refresh_token, verify_password


class FakeResult:
    def __init__(self, value: Any):
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


@dataclass
class SentEmail:
    kind: str
    email: str
    token: str


class FakeSession:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.roles: list[Role] = [Role(id=1, name="user")]
        self.user_roles: list[UserRole] = []
        self.tokens: list[EmailToken] = []
        self._next_user_id = 1
        self._next_token_id = 1
        self.commits = 0

    def add(self, obj: Any) -> None:
        if isinstance(obj, User):
            if obj.id is None:
                obj.id = self._next_user_id
                self._next_user_id += 1
            self.users.append(obj)
            return
        if isinstance(obj, EmailToken):
            if obj.id is None:
                obj.id = self._next_token_id
                self._next_token_id += 1
            self.tokens.append(obj)
            return
        if isinstance(obj, UserRole):
            self.user_roles.append(obj)
            return
        raise AssertionError(f"unexpected add: {obj!r}")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _obj: Any) -> None:
        return None

    async def delete(self, obj: Any) -> None:
        if isinstance(obj, EmailToken) and obj in self.tokens:
            self.tokens.remove(obj)

    async def get(self, model: type[Any], id_: int) -> Any:
        if model is User:
            return next((u for u in self.users if u.id == id_), None)
        if model is EmailToken:
            return next((t for t in self.tokens if t.id == id_), None)
        raise AssertionError(f"unexpected get model: {model!r}")

    async def scalar(self, statement: Any) -> Any:
        return self._first(statement)

    async def execute(self, statement: Any) -> FakeResult:
        return FakeResult(self._first(statement))

    def _first(self, statement: Any) -> Any:
        entity = statement.column_descriptions[0].get("entity")
        if entity is User:
            rows = self.users
        elif entity is Role:
            rows = self.roles
        elif entity is EmailToken:
            rows = self.tokens
        else:
            raise AssertionError(f"unexpected select entity: {entity!r}")

        for row in rows:
            if all(_matches(row, criterion) for criterion in statement._where_criteria):
                return row
        return None


def _matches(row: Any, criterion: Any) -> bool:
    if isinstance(criterion, BooleanClauseList):
        return all(_matches(row, child) for child in criterion.clauses)
    if isinstance(criterion, BinaryExpression):
        return getattr(row, criterion.left.key) == criterion.right.value
    raise AssertionError(f"unsupported criterion: {criterion!r}")


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[SentEmail]:
    sent: list[SentEmail] = []
    monkeypatch.setattr(
        auth,
        "send_verify_email",
        lambda email, token: sent.append(SentEmail("verify", email, token)),
    )
    monkeypatch.setattr(
        auth,
        "send_reset_password_email",
        lambda email, token: sent.append(SentEmail("reset", email, token)),
    )
    return sent


@pytest.mark.asyncio
async def test_register_returns_accepted_response_and_does_not_return_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    response = await auth.register(RegisterIn(email="USER@Example.COM", password="secret"), session)

    assert response.model_dump() == {
        "ok": True,
        "message": "registration accepted; verification email sent",
    }
    assert not hasattr(response, "access_token")
    assert session.users[0].email == "user@example.com"
    assert session.users[0].is_active is True
    assert session.users[0].is_verified is False
    assert session.users[0].email_verified_at is None
    assert verify_password("secret", session.users[0].hashed_password)
    assert session.tokens[0].purpose == "verify"
    assert session.user_roles[0].role_id == 1
    assert sent_emails == [SentEmail("verify", "user@example.com", sent_emails[0].token)]


@pytest.mark.asyncio
async def test_duplicate_register_is_rejected(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    with pytest.raises(HTTPException) as exc:
        await auth.register(RegisterIn(email="USER@example.com", password="secret"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Email already registered"


@pytest.mark.asyncio
async def test_login_before_verification_returns_403(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    with pytest.raises(HTTPException) as exc:
        await auth.login(RegisterIn(email="user@example.com", password="secret"), session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Email is not verified"


@pytest.mark.asyncio
async def test_verify_activates_user_and_sets_email_verified_at(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    response = await auth.verify_email(sent_emails[0].token, session)

    assert response.model_dump() == {"ok": True, "message": "email verified"}
    assert session.users[0].is_verified is True
    assert session.users[0].email_verified_at is not None
    assert session.tokens == []


@pytest.mark.asyncio
async def test_expired_verify_token_is_rejected(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)
    session.tokens[0].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email(sent_emails[0].token, session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_login_after_verification_returns_access_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)
    await auth.verify_email(sent_emails[0].token, session)

    response = await auth.login(RegisterIn(email="USER@example.com", password="secret"), session)

    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token


@pytest.mark.asyncio
async def test_resend_verification_returns_safe_response(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    response = await auth.resend_verification(EmailIn(email="USER@example.com"), session)

    assert response.model_dump() == {
        "ok": True,
        "message": "if an account exists and is not verified, a verification email has been sent",
    }
    assert len([email for email in sent_emails if email.kind == "verify"]) == 2


@pytest.mark.asyncio
async def test_forgot_password_returns_safe_response(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    response = await auth.forgot_password(EmailIn(email="USER@example.com"), session)

    assert response.model_dump() == {"ok": True, "message": "if an account exists, a reset email has been sent"}
    assert sent_emails[-1].kind == "reset"
    assert session.tokens[-1].purpose == "reset"


@pytest.mark.asyncio
async def test_reset_password_updates_password_and_replaces_old_login(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="old-password"), session)
    await auth.verify_email(sent_emails[0].token, session)
    await auth.forgot_password(EmailIn(email="user@example.com"), session)
    reset_token = sent_emails[-1].token

    response = await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    assert response.model_dump() == {"ok": True, "message": "password has been reset"}
    with pytest.raises(HTTPException) as exc:
        await auth.login(RegisterIn(email="user@example.com", password="old-password"), session)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"

    login = await auth.login(RegisterIn(email="user@example.com", password="new-password"), session)
    assert login.access_token


SAFE_RESEND_RESPONSE = {
    "ok": True,
    "message": "if an account exists and is not verified, a verification email has been sent",
}
SAFE_FORGOT_RESPONSE = {
    "ok": True,
    "message": "if an account exists, a reset email has been sent",
}
SENSITIVE_FIELDS = {"hashed_password", "password", "token", "access_token", "refresh_token", "token_hash"}


def assert_no_sensitive_fields(payload: dict[str, Any]) -> None:
    assert SENSITIVE_FIELDS.isdisjoint(payload.keys())


def last_email(sent_emails: list[SentEmail], kind: str) -> SentEmail:
    return [email for email in sent_emails if email.kind == kind][-1]


async def register_user(
    session: FakeSession,
    sent_emails: list[SentEmail],
    email: str = "user@example.com",
    password: str = "secret",
) -> User:
    await auth.register(RegisterIn(email=email, password=password), session)
    assert sent_emails
    return session.users[-1]


async def verify_user(session: FakeSession, token: str) -> None:
    await auth.verify_email(token, session)


async def forgot_password(
    session: FakeSession,
    sent_emails: list[SentEmail],
    email: str = "user@example.com",
) -> str:
    await auth.forgot_password(EmailIn(email=email), session)
    return last_email(sent_emails, "reset").token


@pytest.mark.asyncio
async def test_register_creates_exactly_one_future_verify_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    before = datetime.now(timezone.utc)

    await auth.register(RegisterIn(email="USER@Example.COM", password="secret"), session)

    verify_tokens = [token for token in session.tokens if token.purpose == "verify"]
    assert len(verify_tokens) == 1
    assert verify_tokens[0].expires_at > before
    assert verify_tokens[0].token_hash != sent_emails[0].token
    assert sent_emails[0].email == "user@example.com"


@pytest.mark.asyncio
async def test_register_hashes_password_and_never_stores_raw_password(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    await auth.register(RegisterIn(email="user@example.com", password="plain-password"), session)

    user = session.users[0]
    assert user.hashed_password != "plain-password"
    assert verify_password("plain-password", user.hashed_password)


@pytest.mark.asyncio
async def test_register_assigns_default_user_role_when_role_exists(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    assert len(session.user_roles) == 1
    assert session.user_roles[0].user_id == session.users[0].id
    assert session.user_roles[0].role_id == 1


@pytest.mark.asyncio
async def test_register_succeeds_without_default_user_role_when_role_missing(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    session.roles = []

    response = await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    assert response.model_dump() == {
        "ok": True,
        "message": "registration accepted; verification email sent",
    }
    assert len(session.users) == 1
    assert len(session.tokens) == 1
    assert session.user_roles == []
    assert sent_emails[0].email == "user@example.com"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_invalid_credentials(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        await auth.login(RegisterIn(email="unknown@example.com", password="secret"), session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_invalid_credentials(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails, password="correct-password")

    with pytest.raises(HTTPException) as exc:
        await auth.login(RegisterIn(email="user@example.com", password="wrong-password"), session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_inactive_verified_user_returns_403(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    user = await register_user(session, sent_emails, password="secret")
    await verify_user(session, sent_emails[0].token)
    user.is_active = False

    with pytest.raises(HTTPException) as exc:
        await auth.login(RegisterIn(email="USER@example.com", password="secret"), session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "User is inactive"


@pytest.mark.asyncio
async def test_login_response_contains_only_bearer_token_fields(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails, password="secret")
    await verify_user(session, sent_emails[0].token)

    response = await auth.login(RegisterIn(email="USER@example.com", password="secret"), session)
    payload = response.model_dump()

    assert set(payload) == {"access_token", "refresh_token", "token_type"}
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert "hashed_password" not in payload


@pytest.mark.asyncio
async def test_reused_verify_token_fails(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    token = sent_emails[0].token
    await auth.verify_email(token, session)

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email(token, session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_reset_token_cannot_be_used_for_email_verification(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    reset_token = await forgot_password(session, sent_emails)

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email(reset_token, session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_invalid_random_verify_token_fails(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email("not-a-real-token", session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_verify_token_for_missing_user_fails_safely(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    token = sent_emails[0].token
    session.users.clear()

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email(token, session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "User not found"


@pytest.mark.asyncio
async def test_already_verified_user_with_valid_verify_token_is_deterministic(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    user = await register_user(session, sent_emails)
    user.is_verified = True
    existing_verified_at = datetime.now(timezone.utc) - timedelta(hours=1)
    user.email_verified_at = existing_verified_at

    response = await auth.verify_email(sent_emails[0].token, session)

    assert response.model_dump() == {"ok": True, "message": "email verified"}
    assert user.is_verified is True
    assert user.email_verified_at is not None
    assert session.tokens == []


@pytest.mark.asyncio
async def test_resend_verification_unknown_email_returns_safe_response_without_email(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    response = await auth.resend_verification(EmailIn(email="unknown@example.com"), session)

    assert response.model_dump() == SAFE_RESEND_RESPONSE
    assert sent_emails == []
    assert session.tokens == []


@pytest.mark.asyncio
async def test_resend_verification_verified_email_returns_safe_response_without_email(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)
    sent_emails.clear()

    response = await auth.resend_verification(EmailIn(email="USER@example.com"), session)

    assert response.model_dump() == SAFE_RESEND_RESPONSE
    assert sent_emails == []
    assert session.tokens == []


@pytest.mark.asyncio
async def test_resend_verification_unverified_user_gets_new_verify_token_and_email(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    original_token_hash = session.tokens[0].token_hash

    response = await auth.resend_verification(EmailIn(email="USER@example.com"), session)

    assert response.model_dump() == SAFE_RESEND_RESPONSE
    verify_tokens = [token for token in session.tokens if token.purpose == "verify"]
    assert len(verify_tokens) == 1
    assert verify_tokens[-1].token_hash != original_token_hash
    assert sent_emails[-1].kind == "verify"
    assert sent_emails[-1].email == "user@example.com"


@pytest.mark.asyncio
async def test_resend_verification_invalidates_previous_verify_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    old_token = sent_emails[0].token

    await auth.resend_verification(EmailIn(email="user@example.com"), session)

    with pytest.raises(HTTPException) as exc:
        await auth.verify_email(old_token, session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_returns_safe_response_without_email(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    response = await auth.forgot_password(EmailIn(email="unknown@example.com"), session)

    assert response.model_dump() == SAFE_FORGOT_RESPONSE
    assert sent_emails == []
    assert session.tokens == []


@pytest.mark.asyncio
async def test_forgot_password_existing_user_creates_future_hashed_reset_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    before = datetime.now(timezone.utc)

    response = await auth.forgot_password(EmailIn(email="USER@example.com"), session)

    assert response.model_dump() == SAFE_FORGOT_RESPONSE
    reset_tokens = [token for token in session.tokens if token.purpose == "reset"]
    assert len(reset_tokens) == 1
    assert reset_tokens[0].expires_at > before
    assert reset_tokens[0].token_hash != last_email(sent_emails, "reset").token
    assert last_email(sent_emails, "reset").email == "user@example.com"


@pytest.mark.asyncio
async def test_reset_token_is_deleted_or_invalidated_after_use(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails, password="old-password")
    await verify_user(session, sent_emails[0].token)
    reset_token = await forgot_password(session, sent_emails)

    await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    assert all(token.purpose != "reset" for token in session.tokens)


@pytest.mark.asyncio
async def test_reused_reset_token_fails(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails, password="old-password")
    await verify_user(session, sent_emails[0].token)
    reset_token = await forgot_password(session, sent_emails)
    await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    with pytest.raises(HTTPException) as exc:
        await auth.reset_password(ResetPasswordIn(token=reset_token, password="another-password"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_expired_reset_token_fails(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    reset_token = await forgot_password(session, sent_emails)
    session.tokens[-1].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(HTTPException) as exc:
        await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_verify_token_cannot_be_used_as_reset_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)

    with pytest.raises(HTTPException) as exc:
        await auth.reset_password(ResetPasswordIn(token=sent_emails[0].token, password="new-password"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_invalid_random_reset_token_fails(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        await auth.reset_password(ResetPasswordIn(token="not-a-real-token", password="new-password"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired token"


@pytest.mark.asyncio
async def test_reset_password_for_missing_user_fails_safely(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    reset_token = await forgot_password(session, sent_emails)
    session.users.clear()

    with pytest.raises(HTTPException) as exc:
        await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "User not found"


@pytest.mark.asyncio
async def test_reset_password_does_not_change_email_verification_state(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    user = await register_user(session, sent_emails, password="old-password")
    await verify_user(session, sent_emails[0].token)
    verified_at = user.email_verified_at
    reset_token = await forgot_password(session, sent_emails)

    await auth.reset_password(ResetPasswordIn(token=reset_token, password="new-password"), session)

    assert user.is_verified is True
    assert user.email_verified_at == verified_at


@pytest.mark.asyncio
async def test_current_user_dto_is_safe_for_authenticated_user(sent_emails: list[SentEmail]) -> None:
    from app.routers import users

    session = FakeSession()
    user = await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)

    payload = await users.me(session, user)

    assert payload["id"] == user.id
    assert payload["email"] == "user@example.com"
    assert payload["is_active"] is True
    assert payload["is_verified"] is True
    assert "email_verified_at" in payload
    assert "roles" in payload
    assert_no_sensitive_fields(payload)


@pytest.mark.asyncio
async def test_current_user_invalid_token_is_rejected() -> None:
    from app.deps import get_current_user

    session = FakeSession()
    bearer = type("Bearer", (), {"credentials": "not-a-jwt"})()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer, session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_current_user_rejects_inactive_user(sent_emails: list[SentEmail]) -> None:
    from app.deps import get_current_user
    from app.security import create_access_token

    session = FakeSession()
    user = await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)
    user.is_active = False
    bearer = type("Bearer", (), {"credentials": create_access_token(user.email)})()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer, session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "User is inactive"


@pytest.mark.asyncio
async def test_current_user_unverified_behavior_is_explicitly_rejected(sent_emails: list[SentEmail]) -> None:
    from app.deps import get_current_user
    from app.security import create_access_token

    session = FakeSession()
    user = await register_user(session, sent_emails)
    bearer = type("Bearer", (), {"credentials": create_access_token(user.email)})()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer, session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Email is not verified"


@pytest.mark.asyncio
async def test_refresh_with_valid_refresh_token_returns_new_access_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails, password="secret")
    await verify_user(session, sent_emails[0].token)
    login = await auth.login(RegisterIn(email="user@example.com", password="secret"), session)

    response = await auth.refresh(RefreshIn(refresh_token=login.refresh_token), session)

    assert response.token_type == "bearer"
    assert response.access_token
    assert not hasattr(response, "refresh_token")


@pytest.mark.asyncio
async def test_refresh_rejects_access_token_used_as_refresh_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)
    access_token = create_access_token("user@example.com")

    with pytest.raises(HTTPException) as exc:
        await auth.refresh(RefreshIn(refresh_token=access_token), session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_rejects_random_invalid_token(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        await auth.refresh(RefreshIn(refresh_token="not-a-jwt"), session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_rejects_missing_user(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    refresh_token = create_refresh_token("missing@example.com")

    with pytest.raises(HTTPException) as exc:
        await auth.refresh(RefreshIn(refresh_token=refresh_token), session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_rejects_inactive_user(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    user = await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)
    user.is_active = False
    refresh_token = create_refresh_token(user.email)

    with pytest.raises(HTTPException) as exc:
        await auth.refresh(RefreshIn(refresh_token=refresh_token), session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "User is inactive"


@pytest.mark.asyncio
async def test_refresh_rejects_unverified_user(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    user = await register_user(session, sent_emails)
    refresh_token = create_refresh_token(user.email)

    with pytest.raises(HTTPException) as exc:
        await auth.refresh(RefreshIn(refresh_token=refresh_token), session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Email is not verified"


@pytest.mark.asyncio
async def test_current_user_rejects_refresh_token_used_as_bearer_access_token(sent_emails: list[SentEmail]) -> None:
    from app.deps import get_current_user

    session = FakeSession()
    user = await register_user(session, sent_emails)
    await verify_user(session, sent_emails[0].token)
    bearer = type("Bearer", (), {"credentials": create_refresh_token(user.email)})()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(bearer, session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"
