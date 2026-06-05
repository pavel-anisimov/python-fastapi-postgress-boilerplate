from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import secrets, hashlib
from datetime import datetime, timedelta, timezone

from app.deps import get_current_user, get_session
from app.schemas.auth import EmailIn, MessageOut, RefreshIn, RefreshOut, RegisterIn, ResetPasswordIn, TokenOut
from app.models.user import User
from app.models.token import EmailToken
from app.models.role import Role, UserRole
from app.services.mailer import send_reset_password_email, send_verify_email
from app.security import decode_token, hash_password, verify_password, create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])

VERIFY_TOKEN_TTL_HOURS = 24
RESET_TOKEN_TTL_HOURS = 1


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _now()


async def _create_email_token(
    session: AsyncSession,
    user_id: int,
    purpose: str,
    ttl_hours: int,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=_token_hash(raw_token),
            expires_at=_now() + timedelta(hours=ttl_hours),
        )
    )
    return raw_token


async def _delete_email_tokens(
    session: AsyncSession,
    user_id: int,
    purpose: str,
) -> None:
    while db_token := await session.scalar(
        select(EmailToken).where(
            and_(
                EmailToken.user_id == user_id,
                EmailToken.purpose == purpose,
            )
        )
    ):
        await session.delete(db_token)


async def _get_valid_email_token(
    session: AsyncSession,
    raw_token: str,
    purpose: str,
) -> EmailToken:
    db_token = await session.scalar(
        select(EmailToken).where(
            and_(
                EmailToken.token_hash == _token_hash(raw_token),
                EmailToken.purpose == purpose,
            )
        )
    )
    if not db_token or db_token.used_at or _is_expired(db_token.expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return db_token


@router.post("/register", response_model=MessageOut)
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)):
    email = _normalize_email(data.email)
    exists = await session.scalar(select(User).where(User.email == email))
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        is_verified=False,
        is_active=True,
        email_verified_at=None,
    )
    session.add(user)
    await session.flush()

    default_role = await session.scalar(select(Role).where(Role.name == "user"))
    if default_role:
        session.add(UserRole(user_id=user.id, role_id=default_role.id))

    raw_token = await _create_email_token(session, user.id, "verify", VERIFY_TOKEN_TTL_HOURS)
    await session.commit()

    send_verify_email(user.email, raw_token)

    return MessageOut(ok=True, message="registration accepted; verification email sent")



@router.get("/verify", response_model=MessageOut)
async def verify_email(token: str, session: AsyncSession = Depends(get_session)):
    dbt = await _get_valid_email_token(session, token, "verify")

    user = await session.get(User, dbt.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.is_verified = True
    user.email_verified_at = _now()
    dbt.used_at = _now()
    await session.delete(dbt)
    await session.commit()
    return MessageOut(ok=True, message="email verified")


@router.post("/login", response_model=TokenOut)
async def login(payload: RegisterIn, session: AsyncSession = Depends(get_session)):
    email = _normalize_email(payload.email)
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email is not verified")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    return TokenOut(
        access_token=create_access_token(user.email),
        refresh_token=create_refresh_token(user.email),
    )


@router.post("/refresh", response_model=RefreshOut)
async def refresh(payload: RefreshIn, session: AsyncSession = Depends(get_session)):
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    email = token_payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = (
        await session.execute(select(User).where(User.email == _normalize_email(email)))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email is not verified")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return RefreshOut(access_token=create_access_token(user.email))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)):
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(data: EmailIn, session: AsyncSession = Depends(get_session)):
    email = _normalize_email(data.email)
    user = await session.scalar(select(User).where(User.email == email))
    if user and not user.is_verified:
        # invalidate previously issued verify tokens so only the latest one works
        await _delete_email_tokens(session, user.id, "verify")
        raw_token = await _create_email_token(session, user.id, "verify", VERIFY_TOKEN_TTL_HOURS)
        await session.commit()
        send_verify_email(user.email, raw_token)

    return MessageOut(
        ok=True,
        message="if an account exists and is not verified, a verification email has been sent",
    )


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(data: EmailIn, session: AsyncSession = Depends(get_session)):
    email = _normalize_email(data.email)
    user = await session.scalar(select(User).where(User.email == email))
    if user:
        raw_token = await _create_email_token(session, user.id, "reset", RESET_TOKEN_TTL_HOURS)
        await session.commit()
        send_reset_password_email(user.email, raw_token)

    return MessageOut(ok=True, message="if an account exists, a reset email has been sent")


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(data: ResetPasswordIn, session: AsyncSession = Depends(get_session)):
    dbt = await _get_valid_email_token(session, data.token, "reset")
    user = await session.get(User, dbt.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.hashed_password = hash_password(data.password)
    dbt.used_at = _now()
    await session.delete(dbt)
    await session.commit()
    return MessageOut(ok=True, message="password has been reset")
