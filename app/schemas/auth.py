from pydantic import BaseModel, EmailStr

class RegisterIn(BaseModel):
    email: EmailStr
    password: str

class EmailIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class MessageOut(BaseModel):
    ok: bool
    message: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
