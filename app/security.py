from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    password_bytes = password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def _create_token(sub: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def create_access_token(sub: str, minutes: int | None = None) -> str:
    expires_in = minutes if minutes is not None else settings.access_token_expire_minutes
    return _create_token(sub, "access", timedelta(minutes=expires_in))


def create_refresh_token(sub: str, days: int | None = None) -> str:
    expires_in = days if days is not None else settings.refresh_token_expire_days
    return _create_token(sub, "refresh", timedelta(days=expires_in))


def decode_token(token: str, expected_type: str | None = None) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Invalid token type")
    return payload
