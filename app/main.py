from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .core.rate_limiter import RateLimiter

app = FastAPI(title="Token Bucket Rate Limiter")


limiter = RateLimiter(default_capacity=10, default_refill_rate_per_sec=5.0)

@app.post("/allow")
def allow(user_id: str, resource: str = "default", cost: int = 1):
    allowed, retry_after = limiter.allow(user_id, resource, cost=cost)
    if allowed:
        return {"allowed": True, "retry_after": 0.0}
    retry_after_hdr = f"{max(0.0, round(retry_after, 3))}"
    return JSONResponse(
        status_code=429,
        content={"allowed": False, "retry_after": retry_after},
        headers={"Retry-After": retry_after_hdr},
    )

@app.get("/")
async def root():
    return {"message": "Hello World"}