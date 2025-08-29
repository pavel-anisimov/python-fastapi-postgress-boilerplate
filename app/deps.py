from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from .db import SessionLocal
from .security import decode_token
from .models.user import User
from sqlalchemy import select

bearer = HTTPBearer()

async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

async def get_current_user(token=Depends(bearer), db: AsyncSession = Depends(get_db)) -> User:
    try:
        payload = decode_token(token.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_roles(*names: str):
    async def dep(user: User = Depends(get_current_user)) -> User:
        if not names:
            return user
        have = {ur.role.name for ur in user.roles}
        if not set(names).issubset(have):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dep

# so that old imports like "from app.deps import get_session" work
get_session = get_db

async def get_current_user_verified(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_verified", False):
        raise HTTPException(status_code=403, detail="Email is not verified")
    return user