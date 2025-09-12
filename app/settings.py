from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    BUCKET_KEY_FMT: str = Field(default="rl:{user}:{resource}")

    OFFENDERS_ZSET: str = Field(default="rate:top_offenders")
    OFFENDERS_BUCKET_PREFIX: str = Field(default="rate:top_offenders")

    DEFAULT_CAPACITY: int = 10
    DEFAULT_RATE_TOKENS_PER_SEC: float = 5.0
    SCALE: int = 10_000
    TTL_SECONDS: int = 3600          # 1 hour idle cleanup
    IDEM_TTL_SECONDS: int = 60       # 60s to de-dup client retries

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
