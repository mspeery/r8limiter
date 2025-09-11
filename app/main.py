from __future__ import annotations
import os
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
import redis
from app.settings import settings


app = FastAPI(title="Redis Lua Token Bucket")

r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

# Load Lua script
with open(os.path.join(os.path.dirname(__file__), "limiter.lua"), "r") as f:
    LUA_SOURCE = f.read()

LUA_SCRIPT = r.register_script(LUA_SOURCE)

def bucket_key(user_id: str, resource: str) -> str:
    return f"rl:{user_id}:{resource}"

def idem_key(user_id: str, resource: str, idem: str | None) -> str | None:
    if not idem:
        return None
    # Keep short to control memory
    return f"idem:{user_id}:{resource}:{idem}"

@app.post("/allow")
def allow(
    user_id: str, 
    resource: str = "default", 
    cost: int = 1,
    idempotency_key: str or None = Header(default=None, alias="Idempotency-Key"),
):
    if cost <= 0:
        return JSONResponse(status_code=400, content={"error": "cost must be > 0"})

    keys = [bucket_key(user_id, resource)]
    idemk = idem_key(user_id, resource, idempotency_key)
    if idemk:
        keys.append(idemk)


    args = [
        str(settings.DEFAULT_CAPACITY),
        str(int(settings.DEFAULT_REFILL_RATE_PER_SEC * settings.SUBTOKEN_SCALE)),
        str(cost),
        str(settings.SUBTOKEN_SCALE),
        str(settings.BUCKET_TTL_SECONDS),
        str(settings.IDEMPOTENCY_TTL_SECONDS),
    ]

    # Lua returns: [allowed, retry_after_seconds(str), remaining_tokens(str), used_idem]
    result = LUA_SCRIPT(keys=keys, args=args)
    allowed = int(result[0]) == 1
    retry_after = float(result[1])
    remaining = float(result[2])

    if allowed:
        return {"allowed": True, "retry_after": 0.0, "remaining": remaining}
    else:
        return JSONResponse(
            status_code=429,
            content={"allowed": False, "retry_after": retry_after, "remaining": remaining},
            headers={"Retry-After": f"{max(0.0, round(retry_after, 3))}"},
        )

@app.get("/")
async def root():
    return {"message": "Hello World"}