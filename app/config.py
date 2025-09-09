import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CAPACITY = int(os.getenv("RL_CAPACITY", "10"))          # tokens
REFILL_RATE = float(os.getenv("RL_REFILL_RATE", "10"))  # tokens/sec
TTL_SECONDS = int(os.getenv("RL_TTL_SECONDS", "120"))   # key ttl
SERVICE_NAME = "r8limiter"
