from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
from .config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str: return pwd.hash(p)
def verify_password(p: str, hp: str) -> bool: return pwd.verify(p, hp)

def create_access_token(sub: str, minutes: int = 60) -> str:
    now = datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])

