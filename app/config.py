import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# HS256 needs a key of at least 32 bytes (RFC 7518 section 3.2)
MIN_JWT_SECRET_LENGTH = 32


def _require_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET must be set and at least {MIN_JWT_SECRET_LENGTH} characters long. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return secret


class Settings(BaseModel):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app")

    # JWT
    jwt_secret: str = _require_jwt_secret()
    jwt_alg: str = os.getenv("JWT_ALG", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

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
