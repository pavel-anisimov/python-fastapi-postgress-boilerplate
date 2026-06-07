from datetime import date

from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_active: bool


class ProfileLocation(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip: str | None = None


class UserProfileData(BaseModel):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None
    location: ProfileLocation = ProfileLocation()
    language: str | None = None
    timezone: str | None = None


class UserProfileOut(BaseModel):
    id: int
    email: EmailStr
    profile_completed: bool
    profile: UserProfileData


class UserProfileUpdate(BaseModel):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None
    location: ProfileLocation | None = None
    language: str | None = None
    timezone: str | None = None
