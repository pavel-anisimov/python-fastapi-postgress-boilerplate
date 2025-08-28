import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev")
    jwt_alg: str = os.getenv("JWT_ALG", "HS256")

settings = Settings()
