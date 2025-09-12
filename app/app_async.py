from __future__ import annotations
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from prometheus_client import (
    Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

import redis.asyncio as redis
from app.lua_limiter_async import AsyncLuaLimiter
from app.settings import settings

# Optional per-resource overrides
RESOURCE_CFG: Dict[str, Tuple[int, float]] = {}  # {"read": (10, 5.0)}

# ---------- Logging (JSON) ----------
logger = logging.getLogger("rate_limiter")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)

# ---------- Redis & Lua ----------
r: redis.Redis = redis.from_url(settings.REDIS_URL, decode_responses=False)

with open(os.path.join(os.path.dirname(__file__), "limiter.lua"), "r") as f:
    LUA_SOURCE = f.read()

limiter = AsyncLuaLimiter(r, LUA_SOURCE)

app = FastAPI(title="Redis Lua Token Bucket")

# ---------- Prometheus ----------
registry = CollectorRegistry()
REQ_TOTAL = Counter("requests_total", "Total /allow", ["result"], registry=registry)
ACTIVE_KEYS = Gauge("acitive_keys", "Active rl:* buckets", registry=registry)
REQ_LAT = Histogram(
    "request_latency_seconds",
    "Latency",
    ["endpoint"],
    registry=registry,
    buckets=(0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0),
)

ALLOWED_TOTAL = 0
DENIED_TOTAL = 0

def resource_cfg(resource: str) -> Tuple[int, float]:
    cap, rate = RESOURCE_CFG.get(resource, (settings.DEFAULT_CAPACITY, settings.DEFAULT_RATE_TOKENS_PER_SEC))
    return int(cap), float(rate)

async def count_active_keys() -> int:
    cnt = 0
    cur = 0
    pattern = settings.BUCKET_KEY_FMT.replace("{user}", "*").replace("{resource}", "*").encode("UTF-8")
    while True:
        cur, keys = await r.scan(cursor=cur, match=pattern, count=1000)
        cnt + len(keys)
        if cur == 0:
            break
    return cnt

def floor_time(dt: datetime, bucket: str) -> datetime:
    if bucket == "minute":   return dt.replace(second=0, microsecond=0, tzinfo=timezone.utc)
    if bucket == "hour":     return dt.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    if bucket == "day":      return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return dt.replace(second=0, microsecond=0, tzinfo=timezone.utc)

def bucket_key_for(dt: datetime, bucket: str) -> str:
    dt = dt.astimezone(timezone.utc)
    if bucket == "minute": tag = dt.strftime("%Y%m%d%H%M")
    elif bucket == "hour": tag = dt.strftime("%Y%m%d%H")
    elif bucket == "day":  tag = dt.strftime("%Y%m%d")
    else:                  tag = dt.strftime("%Y%m%d%H%M")
    return f"{settings.OFFENDERS_BUCKET_PREFIX}:{bucket}:{tag}"

def bucket_ttl_seconds(bucket: str) -> int:
    return {"minute": 60*90, "hour": 3600*48, "day": 86400*14}.get(bucket, 60*90)

# ---------- FastAPI ----------
app = FastAPI(title="Redis Lua Token Bucket (Async)")

class ObsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic_ns()
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        try:
            resp = await call_next(request)
            return resp
        finally:
            took_ms = (time.monotonic_ns() - start) / 1_000_000.0
            REQ_LAT.labels(endpoint=request.url.path).observe(took_ms/1000.0)
            logger.info(json.dumps({
                "ts": time.time(),
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": getattr(request.state, "status_code", None),
                "latency_ms": round(took_ms, 3),
            }))

app.add_middleware(ObsMiddleware)

@app.get("/metrics")
async def metrics():
    try:
        ACTIVE_KEYS.set(await count_active_keys())
    except Exception:
        pass
    data = generate_latest(registry)
    return PlainTextResponse(data.decode("UTF-8"), media_type=CONTENT_TYPE_LATEST)

@app.post("/allow")
async def allow(request: Request, 
    user_id: str, 
    resource: str = "default", 
    cost: int = 1, 
    idempotency: Optional[str] = None
):
    global ALLOWED_TOTAL, DENIED_TOTAL
    t0 = time.monotonic_ns()

    cap, rate_tps = resource_cfg(resource)
    rate_sub_per_sec = int(rate_tps * settings.SCALE)

    bucket_key = settings.BUCKET_KEY_FMT.format(user=user_id, resource=resource)
    idem_key = f"idem:{user_id}:{resource}:{idempotency}" if idempotency else ""

    allowed, retry_after, remaining_tokens, used_idem = await limiter.allow(
        bucket_key=bucket_key,
        capacity_tokens=cap,
        rate_subtokens_per_sec=rate_sub_per_sec,
        cost_tokens=cost,
        scale=settings.SCALE,
        ttl_seconds=settings.TTL_SECONDS,
        idem_key=idem_key,
        idempotency_ttl_seconds=settings.IDEM_TTL_SECONDS,
    )

    if allowed:
        ALLOWED_TOTAL += 1
        REQ_TOTAL.labels(result="allow").inc()
    else:
        DENIED_TOTAL += 1
        REQ_TOTAL.labels(result="deny").inc()
        # offenders: global + time bucket
        try:
            await r.zincrby(settings.OFFENDERS_ZSET, 1.0, user_id)
            now = datetime.now(timezone.utc)
            for bucket in ("minute", "hour", "day"):
                zkey = bucket_key_for(floor_time(now, bucket), bucket)
                await r.zincrby(zkey, 1.0, user_id)
                await r.expire(zkey, bucket_ttl_seconds(bucket))
        except Exception:
            pass

    try:
        ACTIVE_KEYS.set(await count_active_keys())
    except Exception:
        pass

    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    took_ms = (time.monotonic_ns() - t0) / 1_000_000.0
    request.state.status_code = 200 if allowed else 429
    logger.info(json.dumps({
        "ts": time.time(),
        "request_id": rid,
        "user_id": user_id,
        "resource": resource,
        "decision": "allow" if allowed else "deny",
        "tokens_left": round(remaining_tokens, 6),
        "latency_ms": round(took_ms, 3),
        "idempotent_cache": bool(used_idem),
    }))

    if allowed:
        return {"allowed": True, "retry_after": 0.0, "tokens_left": remaining_tokens}

    return JSONResponse(
        status_code=429,
        content={"allowed": False, "retry_after": retry_after, "tokens_left": remaining_tokens},
        headers={"Retry-After": f"{max(0.0, round(retry_after, 3))}", "X-Request-ID": rid},
    )

@app.get("/admin/stats")
async def admin_stats(top_n: int = 10):
    try:
        raw = await r.zrevrange(settings.OFFENDERS_ZSET, 0, top_n-1, withscores=True)
        offenders = [{"user_id": (uid.decode() if isinstance(uid, bytes) else uid), "denies": int(score)} for uid, score in raw]
    except Exception:
        offenders = []
    try:
        active = await count_active_keys()
    except Exception:
        active = None
    return {
        "allowed_total": ALLOWED_TOTAL,
        "denied_total": DENIED_TOTAL,
        "active_keys": active,
        "top_offenders": offenders,
    }

@app.get("/admin/top_offenders")
async def top_offenders(window: str = "1h", bucket: str = "minute", top_n: int = 10):
    """
    window: e.g., 15m, 1h, 6h, 24h
    bucket: minute|hour|day
    Aggregates ZSETs within the window via ZUNIONSTORE into a temp key.
    """
    units = {"m": "minutes", "h": "hours", "d": "days"}
    try:
        amount = int(window[:-1]); unit = window[-1]
        kwargs = {units[unit]: amount}
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid window; use 15m|1h|24h"})

    now = datetime.now(timezone.utc)
    start = now - timedelta(**kwargs)

    # build list of ZSET keys for the window
    keys: List[str] = []
    cursor = floor_time(now, bucket)
    step = {"minute": timedelta(minutes=1), "hour": timedelta(hours=1), "day": timedelta(days=1)}.get(bucket, timedelta(minutes=1))
    while cursor >= floor_time(start, bucket):
        keys.append(bucket_key_for(cursor, bucket))
        cursor -= step
    if not keys:
        return {"window": window, "bucket": bucket, "top_offenders": []}

    # union into a temp key
    temp_key = f"{settings.OFFENDERS_BUCKET_PREFIX}:tmp:{uuid.uuid4()}"
    try:
        await r.zunionstore(temp_key, keys=keys)  # sum by default
        await r.expire(temp_key, 30)  # short TTL
        raw = await r.zrevrange(temp_key, 0, top_n-1, withscores=True)
        out = [{"user_id": (u.decode() if isinstance(u, bytes) else u), "denies": int(s)} for u, s in raw]
    finally:
        # let ttl clean it; no hard DEL needed
        pass

    return {"window": window, "bucket": bucket, "top_offenders": out}

@app.get("/admin/user/{user_id}")
async def admin_user(user_id: str):
    pattern = settings.BUCKET_KEY_FMT.format(user=user_id, resource="*").encode("utf-8")
    cur = 0
    resources: List[dict] = []
    while True:
        cur, keys = await r.scan(cursor=cur, match=pattern, count=500)
        for k in keys:
            key_str = k.decode()
            try:
                resource = key_str.split(":", 2)[2]
            except Exception:
                resource = "unknown"

            # Read persisted config + tokens (written by Lua)
            vals = await r.hmget(k, b"tokens", b"capacity_tokens", b"rate_subtokens_per_sec", b"scale")
            tokens_sub = float(vals[0].decode()) if vals[0] else 0.0
            cap_tokens = int(vals[1].decode()) if vals[1] else settings.DEFAULT_CAPACITY
            rate_sub = int(vals[2].decode()) if vals[2] else int(settings.DEFAULT_RATE_TOKENS_PER_SEC * settings.SCALE)
            sc = int(vals[3].decode()) if vals[3] else settings.SCALE

            tokens = tokens_sub / sc
            rate_tps = rate_sub / sc

            next_token = 0.0 if tokens >= 1.0 else (1.0 - tokens) / max(rate_tps, 1e-12)
            full_refill = 0.0 if tokens >= cap_tokens else (cap_tokens - tokens) / max(rate_tps, 1e-12)

            resources.append({
                "resource": resource,
                "capacity": cap_tokens,
                "refill_rate_per_sec": round(rate_tps, 6),
                "tokens": round(tokens, 6),
                "next_token_seconds": max(0.0, round(next_token, 6)),
                "full_refill_seconds": max(0.0, round(full_refill, 6)),
            })
        if cur == 0:
            break
    return {"user_id": user_id, "resources": resources}

@app.get("/readyz")
async def readyz():
    """
    Readiness = Redis reachable and Lua script loadable.
    """
    try:
        pong = await r.ping()
        # Quick sanity: eval a no-op (EVAL will load if SHA missing)
        _ = await r.eval("return 1", 0)
        ok = bool(pong)
    except Exception as e:
        return JSONResponse(status_code=503, content={"ready": False, "error": str(e)})
    return {"ready": ok}

@app.get("/livez")
async def livez():
    """
    Liveness = process is serving requests (cheap OK).
    """
    return {"alive": True}