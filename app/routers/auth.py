from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import secrets, hashlib
from datetime import datetime, timedelta, timezone

from app.deps import get_session
from app.schemas.auth import RegisterIn, TokenOut
from app.models.user import User
from app.models.token import EmailToken
from app.services.mailer import send_verify_email
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenOut)
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)):
    exists = await session.scalar(select(User).where(User.email == data.email))
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        is_verified=False,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # 1) generate a raw token and calculate the hash
    raw_token = secrets.token_urlsafe(32)  # this will go into the link
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)  # TTL optional

    # 2) save ONLY the hash (and TTL, if any)
    token = EmailToken(
        user_id=user.id,
        purpose="verify",
        token_hash=token_hash,
        expires_at=expires_at,  # if the model has this field
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)

    # 3) send a letter with a "raw" token
    send_verify_email(user.email, raw_token)

    # 4) you can return JWT as it was (access to protected handles will still be cut off by get_current_user_verified)
    return TokenOut(access_token=create_access_token(user.email))



@router.get("/verify", response_model=dict)
async def verify_email(token: str, session: AsyncSession = Depends(get_session)):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    dbt = await session.scalar(
        select(EmailToken).where(
            and_(
                EmailToken.token_hash == token_hash,
                EmailToken.purpose == "verify",
                # # if expires_at exists:
                # EmailToken.expires_at > datetime.now(timezone.utc),
            )
        )
    )
    if not dbt or (hasattr(dbt, "is_expired") and dbt.is_expired()):
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await session.get(User, dbt.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.is_verified = True
    # optional: dbt.used_at = datetime.now(timezone.utc)
    await session.delete(dbt)  # или помечайте used_at
    await session.commit()
    return {"status": "verified"}


@router.post("/login", response_model=TokenOut)
async def login(payload: RegisterIn, session: AsyncSession = Depends(get_session)):
    user = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(user.email))

