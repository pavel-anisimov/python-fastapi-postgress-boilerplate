from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..schemas.item import ItemIn, ItemOut
from ..models.item import Item
from ..deps import get_db, get_current_user

router = APIRouter(prefix="/items", tags=["items"])

@router.post("", response_model=ItemOut)
async def create_item(data: ItemIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    item = Item(owner_id=user.id, title=data.title, description=data.description)
    db.add(item); await db.commit(); await db.refresh(item)
    return item

@router.get("", response_model=list[ItemOut])
async def list_items(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    rows = (await db.execute(select(Item).where(Item.owner_id == user.id))).scalars().all()
    return rows

@router.put("/{item_id}", response_model=ItemOut)
async def update_item(item_id: int, data: ItemIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    item = (await db.execute(select(Item).where(Item.id == item_id, Item.owner_id == user.id))).scalar_one_or_none()
    if not item: raise HTTPException(404, "Not found")
    item.title, item.description = data.title, data.description
    await db.commit(); await db.refresh(item)
    return item

@router.delete("/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    item = (await db.execute(select(Item).where(Item.id == item_id, Item.owner_id == user.id))).scalar_one_or_none()
    if not item: raise HTTPException(404, "Not found")
    await db.delete(item); await db.commit()
    return {"ok": True}

