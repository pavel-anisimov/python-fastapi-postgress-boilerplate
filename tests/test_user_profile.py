from __future__ import annotations

from typing import Any

import pytest

from app.routers import auth, users
from app.schemas.auth import RegisterIn
from tests.test_auth_flow import FakeSession, SentEmail, sent_emails  # noqa: F401  (fixture)
from tests.test_auth_api_contract import api_state, asgi_request  # noqa: F401  (fixture)


# fields that must never appear anywhere in profile responses:
# credentials/tokens plus future domains (security metadata, login history,
# IPs, user agent, preferences, consents, external accounts)
FORBIDDEN_FIELDS = {
    "hashed_password",
    "password",
    "token",
    "token_hash",
    "access_token",
    "refresh_token",
    "last_login",
    "last_login_at",
    "last_login_ip",
    "signup_ip",
    "ip",
    "ip_address",
    "user_agent",
    "preferences",
    "consents",
    "external_accounts",
    "login_history",
    "security",
}


def assert_no_forbidden_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        assert FORBIDDEN_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_fields(item)


async def register_and_login(sent_emails: list[SentEmail]) -> str:
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})
    await asgi_request("GET", f"/auth/verify?token={sent_emails[0].token}")
    login = await asgi_request("POST", "/auth/login", json_body={"email": "user@example.com", "password": "secret"})
    return login.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


# --- profile row creation -------------------------------------------------


@pytest.mark.asyncio
async def test_register_creates_empty_profile_row(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    assert len(session.profiles) == 1
    profile = session.profiles[0]
    assert profile.user_id == session.users[0].id
    assert profile.language == "en"
    for field in (
        "display_name", "first_name", "last_name", "bio", "avatar_url",
        "phone_number", "date_of_birth", "location_city", "location_state",
        "location_country", "location_zip", "timezone",
    ):
        assert getattr(profile, field) is None


@pytest.mark.asyncio
async def test_default_profile_has_profile_completed_false(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()

    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)

    assert session.profiles[0].profile_completed is False


@pytest.mark.asyncio
async def test_get_profile_defensively_creates_missing_profile_row(sent_emails: list[SentEmail]) -> None:
    session = FakeSession()
    await auth.register(RegisterIn(email="user@example.com", password="secret"), session)
    await auth.verify_email(sent_emails[0].token, session)
    session.profiles.clear()  # simulate a user created before profiles existed

    payload = await users.my_profile(session, session.users[0])

    assert len(session.profiles) == 1
    assert session.profiles[0].user_id == session.users[0].id
    assert payload["profile_completed"] is False
    assert payload["profile"]["language"] == "en"


# --- /users/me ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_users_me_includes_profile_completed(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    response = await asgi_request("GET", "/users/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["profile_completed"] is False


# --- GET /users/me/profile -----------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_requires_auth(api_state) -> None:
    response = await asgi_request("GET", "/users/me/profile")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_profile_rejects_unverified_user(api_state) -> None:
    from app.security import create_access_token

    session, _sent_emails = api_state
    await asgi_request("POST", "/auth/register", json_body={"email": "user@example.com", "password": "secret"})
    token = create_access_token(session.users[0].email)

    response = await asgi_request("GET", "/users/me/profile", headers=bearer(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "Email is not verified"}


@pytest.mark.asyncio
async def test_get_profile_returns_safe_dto_for_verified_user(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    response = await asgi_request("GET", "/users/me/profile", headers=bearer(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "id": 1,
        "email": "user@example.com",
        "profile_completed": False,
        "profile": {
            "display_name": None,
            "first_name": None,
            "last_name": None,
            "bio": None,
            "avatar_url": None,
            "phone_number": None,
            "date_of_birth": None,
            "location": {"city": None, "state": None, "country": None, "zip": None},
            "language": "en",
            "timezone": None,
        },
    }
    assert_no_forbidden_fields(payload)


@pytest.mark.asyncio
async def test_get_profile_contract_defensively_creates_missing_row(api_state) -> None:
    session, sent_emails = api_state
    token = await register_and_login(sent_emails)
    session.profiles.clear()

    response = await asgi_request("GET", "/users/me/profile", headers=bearer(token))

    assert response.status_code == 200
    assert len(session.profiles) == 1
    assert response.json()["profile"]["language"] == "en"


# --- PATCH /users/me/profile -----------------------------------------------


FULL_PATCH = {
    "display_name": "Pavel",
    "first_name": "Pavel",
    "last_name": "Anisimov",
    "bio": "Short bio",
    "avatar_url": "https://example.com/avatar.png",
    "phone_number": "+1-202-555-0100",
    "date_of_birth": "1982-01-01",
    "location": {"city": "Pleasant Hill", "state": "CA", "country": "USA", "zip": "94523"},
    "language": "en",
    "timezone": "America/Los_Angeles",
}


@pytest.mark.asyncio
async def test_patch_profile_updates_allowed_fields(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    response = await asgi_request("PATCH", "/users/me/profile", json_body=FULL_PATCH, headers=bearer(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"] == FULL_PATCH
    assert_no_forbidden_fields(payload)


@pytest.mark.asyncio
async def test_patch_profile_does_not_overwrite_omitted_fields_with_null(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)
    await asgi_request("PATCH", "/users/me/profile", json_body=FULL_PATCH, headers=bearer(token))

    response = await asgi_request(
        "PATCH",
        "/users/me/profile",
        json_body={"bio": "Updated bio", "location": {"city": "Walnut Creek"}},
        headers=bearer(token),
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["bio"] == "Updated bio"
    assert profile["location"]["city"] == "Walnut Creek"
    # omitted fields keep previous values
    assert profile["display_name"] == "Pavel"
    assert profile["first_name"] == "Pavel"
    assert profile["last_name"] == "Anisimov"
    assert profile["date_of_birth"] == "1982-01-01"
    assert profile["location"]["state"] == "CA"
    assert profile["location"]["country"] == "USA"
    assert profile["location"]["zip"] == "94523"
    assert profile["timezone"] == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_patch_profile_sets_profile_completed_when_display_name_provided(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    response = await asgi_request(
        "PATCH", "/users/me/profile", json_body={"display_name": "Pavel"}, headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json()["profile_completed"] is True

    me = await asgi_request("GET", "/users/me", headers=bearer(token))
    assert me.json()["profile_completed"] is True


@pytest.mark.asyncio
async def test_patch_profile_without_display_name_keeps_profile_incomplete(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    response = await asgi_request(
        "PATCH", "/users/me/profile", json_body={"bio": "just a bio"}, headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json()["profile_completed"] is False


@pytest.mark.asyncio
async def test_patch_profile_requires_auth(api_state) -> None:
    response = await asgi_request("PATCH", "/users/me/profile", json_body={"display_name": "X"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_responses_contain_no_sensitive_or_future_domain_fields(api_state) -> None:
    _session, sent_emails = api_state
    token = await register_and_login(sent_emails)

    got = await asgi_request("GET", "/users/me/profile", headers=bearer(token))
    patched = await asgi_request("PATCH", "/users/me/profile", json_body=FULL_PATCH, headers=bearer(token))
    me = await asgi_request("GET", "/users/me", headers=bearer(token))

    for response in (got, patched, me):
        assert response.status_code == 200
        assert_no_forbidden_fields(response.json())
