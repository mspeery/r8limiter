from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    DEFAULT_CAPACITY: int = 10
    DEFAULT_REFILL_RATE_PER_SEC: float = 5.0
    SUBTOKEN_SCALE: int = 10_000
    BUCKET_TTL_SECONDS: int = 3600          # 1 hour idle cleanup
    IDEMPOTENCY_TTL_SECONDS: int = 30       # 30s to de-dup client retries

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
