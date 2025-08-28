from fastapi import APIRouter, Depends
from app.deps import require_roles

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/ping", dependencies=[Depends(require_roles("admin"))])
async def ping():
    return {"ok": True}