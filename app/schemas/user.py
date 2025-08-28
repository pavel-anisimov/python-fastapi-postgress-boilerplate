from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_active: bool

