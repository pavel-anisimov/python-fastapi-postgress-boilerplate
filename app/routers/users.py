from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.profile import UserProfile
from app.schemas.user import UserProfileOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])

# UserProfileUpdate.location keys -> UserProfile column names
_LOCATION_COLUMNS = {
    "city": "location_city",
    "state": "location_state",
    "country": "location_country",
    "zip": "location_zip",
}


async def _get_or_create_profile(db: AsyncSession, user: User) -> UserProfile:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        # defensive: users created before profiles existed get an empty one
        profile = UserProfile(user_id=user.id, language="en", profile_completed=False)
        db.add(profile)
        await db.commit()
    return profile


def _profile_payload(user: User, profile: UserProfile) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "profile_completed": bool(profile.profile_completed),
        "profile": {
            "display_name": profile.display_name,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "bio": profile.bio,
            "avatar_url": profile.avatar_url,
            "phone_number": profile.phone_number,
            "date_of_birth": profile.date_of_birth,
            "location": {
                "city": profile.location_city,
                "state": profile.location_state,
                "country": profile.location_country,
                "zip": profile.location_zip,
            },
            "language": profile.language,
            "timezone": profile.timezone,
        },
    }


@router.get("/me")
async def me(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "email_verified_at": user.email_verified_at,
        "roles": [ur.role.name for ur in user.roles],
        "profile_completed": bool(profile.profile_completed) if profile else False,
    }


@router.get("/me/profile", response_model=UserProfileOut)
async def my_profile(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    profile = await _get_or_create_profile(db, user)
    return _profile_payload(user, profile)


@router.patch("/me/profile", response_model=UserProfileOut)
async def update_my_profile(
    data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    profile = await _get_or_create_profile(db, user)

    # apply only the fields the client actually sent
    updates = data.model_dump(exclude_unset=True)
    location = updates.pop("location", None)
    for field, value in updates.items():
        setattr(profile, field, value)
    if location:
        for key, value in location.items():
            setattr(profile, _LOCATION_COLUMNS[key], value)

    if profile.display_name:
        profile.profile_completed = True

    await db.commit()
    return _profile_payload(user, profile)
