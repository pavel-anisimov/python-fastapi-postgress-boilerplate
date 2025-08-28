from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from ..schemas.auth import RegisterIn, TokenOut
from ..models.user import User, Role, UserRole
from ..security import hash_password, verify_password, create_access_token
from ..db import SessionLocal

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_db():
    async with SessionLocal() as s:
        yield s

@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, "Email already registered")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    # assign a basic role user (created by migration)
    role = (await db.execute(select(Role).where(Role.name == "user"))).scalar_one()
    db.add(UserRole(user=user, role=role))
    await db.commit()
    return TokenOut(access_token=create_access_token(user.email))

@router.post("/login", response_model=TokenOut)
async def login(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    return TokenOut(access_token=create_access_token(user.email))

