import os
import asyncio
import pytest
import redis.asyncio as aioredis

APP_URL = os.getenv("APP_URL")  # e.g., http://app:8000 in docker-compose tester
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session")
async def redis_client():
    r = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    try:
        await r.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable at {REDIS_URL}: {e}")
    # Clean slate
    await r.flushdb()
    yield r
    await r.close()

@pytest.fixture(scope="session")
def base_url():
    return APP_URL  # may be None → tests will use in-process ASGI

@pytest.fixture(scope="session")
async def asgi_app():
    if APP_URL:
        return None
    # Import your FastAPI app when running in-process
    from app.app_async import app  # adjust if your module path differs
    return app

@pytest.fixture
async def client(base_url, asgi_app):
    import httpx
    if base_url:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as c:
            yield c
    else:
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=5.0) as c:
            yield c