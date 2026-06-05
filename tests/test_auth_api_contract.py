from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest

from app import deps
from app.main import app
from app.routers import auth, users
from tests.test_auth_flow import FakeSession, SentEmail


SENSITIVE_FIELDS = {"hashed_password", "password", "token", "token_hash", "refresh_token"}


@dataclass
class ApiResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None


async def asgi_request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> ApiResponse:
    parsed = urlsplit(url)
    body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    request_headers = {
        "host": "testserver",
        "content-length": str(len(body)),
    }
    if json_body is not None:
        request_headers["content-type"] = "application/json"
    if headers:
        request_headers.update(headers)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": parsed.path,
        "raw_path": parsed.path.encode("ascii"),
        "query_string": parsed.query.encode("ascii"),
        "headers": [(key.lower().encode("ascii"), value.encode("latin-1")) for key, value in request_headers.items()],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    sent_request = False
    status_code = 500
    response_headers: dict[str, str] = {}
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if sent_request:
            return {"type": "http.disconnect"}
        sent_request = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code, response_headers
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = {
                key.decode("latin-1"): value.decode("latin-1") for key, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return ApiResponse(status_code=status_code, headers=response_headers, body=b"".join(chunks))


@pytest.fixture
def api_state(monkeypatch: pytest.MonkeyPatch):
    session = FakeSession()
    sent_emails: list[SentEmail] = []

    monkeypatch.setattr(
        auth,
        "send_verify_email",
        lambda email, token: sent_emails.append(SentEmail("verify", email, token)),
    )
    monkeypatch.setattr(
        auth,
        "send_reset_password_email",
        lambda email, token: sent_emails.append(SentEmail("reset", email, token)),
    )

    async def override_db():
        yield session

    app.dependency_overrides[deps.get_db] = override_db
    app.dependency_overrides[auth.get_session] = override_db
    app.dependency_overrides[users.get_db] = override_db
    yield session, sent_emails
    app.dependency_overrides.clear()


def assert_no_sensitive_fields(payload: dict[str, Any]) -> None:
    assert SENSITIVE_FIELDS.isdisjoint(payload.keys())


def last_email(sent_emails: list[SentEmail], kind: str) -> SentEmail:
    return [email for email in sent_emails if email.kind == kind][-1]


@pytest.mark.asyncio
async def test_post_auth_register_contract(api_state) -> None:
    _session, sent_emails = api_state

    response = await asgi_request(
        "POST",
        "/auth/register",
        json_body={"email": "USER@example.com", "password": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"ok": True, "message": "registration accepted; verification email sent"}
    assert "access_token" not in payload
    assert sent_emails[0].email == "user@example.com"


@pytest.mark.asyncio
async def test_post_auth_register_validation_error_shape(api_state) -> None:
    response = await asgi_request("POST", "/auth/register", json_body={"email": "not-an-email"})

    assert response.status_code == 422
    payload = response.json()
    assert isinstance(payload["detail"], list)
    assert all("loc" in error and "msg" in error and "type" in error for error in payload["detail"])


@pytest.mark.asyncio
async def test_post_auth_login_unverified_contract(api_state) -> None:
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})

    response = await asgi_request("POST", "/auth/login", json_body={"email": "user@example.com", "password": "secret"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Email is not verified"}


@pytest.mark.asyncio
async def test_get_auth_verify_contract(api_state) -> None:
    _session, sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})

    response = await asgi_request("GET", f"/auth/verify?token={sent_emails[0].token}")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "email verified"}


@pytest.mark.asyncio
async def test_get_auth_verify_invalid_token_contract(api_state) -> None:
    response = await asgi_request("GET", "/auth/verify?token=random-token")

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired token"}


@pytest.mark.asyncio
async def test_post_auth_login_success_contract(api_state) -> None:
    _session, sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})
    await asgi_request("GET", f"/auth/verify?token={sent_emails[0].token}")

    response = await asgi_request("POST", "/auth/login", json_body={"email": "USER@example.com", "password": "secret"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"access_token", "token_type"}
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]


@pytest.mark.asyncio
async def test_post_auth_login_validation_error_shape(api_state) -> None:
    response = await asgi_request("POST", "/auth/login", json_body={"email": "user@example.com"})

    assert response.status_code == 422
    payload = response.json()
    assert isinstance(payload["detail"], list)
    assert any(error["loc"][-1] == "password" for error in payload["detail"])


@pytest.mark.asyncio
async def test_post_auth_resend_verification_contract(api_state) -> None:
    response = await asgi_request("POST", "/auth/resend-verification", json_body={"email": "unknown@example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "if an account exists and is not verified, a verification email has been sent",
    }


@pytest.mark.asyncio
async def test_post_auth_forgot_password_contract(api_state) -> None:
    response = await asgi_request("POST", "/auth/forgot-password", json_body={"email": "unknown@example.com"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "if an account exists, a reset email has been sent"}


@pytest.mark.asyncio
async def test_post_auth_reset_password_contract(api_state) -> None:
    _session, sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "old-password"})
    await asgi_request("GET", f"/auth/verify?token={last_email(sent_emails, 'verify').token}")
    await asgi_request("POST", "/auth/forgot-password", json_body={"email": "user@example.com"})

    response = await asgi_request(
        "POST",
        "/auth/reset-password",
        json_body={"token": last_email(sent_emails, "reset").token, "password": "new-password"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "password has been reset"}

    old_login = await asgi_request(
        "POST",
        "/auth/login",
        json_body={"email": "user@example.com", "password": "old-password"},
    )
    assert old_login.status_code == 401
    assert old_login.json() == {"detail": "Invalid credentials"}

    new_login = await asgi_request(
        "POST",
        "/auth/login",
        json_body={"email": "user@example.com", "password": "new-password"},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


@pytest.mark.asyncio
async def test_post_auth_reset_password_validation_error_shape(api_state) -> None:
    response = await asgi_request("POST", "/auth/reset-password", json_body={"token": "abc"})

    assert response.status_code == 422
    payload = response.json()
    assert isinstance(payload["detail"], list)
    assert any(error["loc"][-1] == "password" for error in payload["detail"])


@pytest.mark.asyncio
async def test_get_users_me_contract_with_bearer_token(api_state) -> None:
    _session, sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})
    await asgi_request("GET", f"/auth/verify?token={sent_emails[0].token}")
    login = await asgi_request("POST", "/auth/login", json_body={"email": "user@example.com", "password": "secret"})
    access_token = login.json()["access_token"]

    response = await asgi_request("GET", "/users/me", headers={"authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 1
    assert payload["email"] == "user@example.com"
    assert payload["is_active"] is True
    assert payload["is_verified"] is True
    assert "email_verified_at" in payload
    assert "roles" in payload
    assert_no_sensitive_fields(payload)


@pytest.mark.asyncio
async def test_get_users_me_missing_token_contract(api_state) -> None:
    response = await asgi_request("GET", "/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_users_me_invalid_token_contract(api_state) -> None:
    response = await asgi_request("GET", "/users/me", headers={"authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


@pytest.mark.asyncio
async def test_get_users_me_unverified_user_is_rejected_contract(api_state) -> None:
    from app.security import create_access_token

    session, _sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})
    access_token = create_access_token(session.users[0].email)

    response = await asgi_request("GET", "/users/me", headers={"authorization": f"Bearer {access_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Email is not verified"}
