from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db, get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
async def me(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "roles": [ur.role.name for ur in user.roles],
    }