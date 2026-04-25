from pathlib import Path

from pydantic_settings import BaseSettings

# Project root is two levels up from app/backend/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    EMBEDDINGS_DIR: str = str(_PROJECT_ROOT / "data" / "embeddings")
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


settings = Settings()
