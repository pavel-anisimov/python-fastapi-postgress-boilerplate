import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app")

    # JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "dev")
    jwt_alg: str = os.getenv("JWT_ALG", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # CORS / Frontend
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    frontend_origin: str = os.getenv("APP_BASE_URL", "http://localhost:8000")

    # SMTP
    smtp_host: str = os.getenv("SMTP_HOST", "localhost")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")
    smtp_tls: bool = os.getenv("SMTP_TLS", "false").lower() == "true"
    smtp_from: str = os.getenv("SMTP_FROM", "no-reply@example.local")

settings = Settings()
