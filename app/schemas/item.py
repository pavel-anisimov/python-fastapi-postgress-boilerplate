from pydantic import BaseModel

class ItemIn(BaseModel):
    title: str
    description: str | None = None

class ItemOut(ItemIn):
    id: int
    owner_id: int

