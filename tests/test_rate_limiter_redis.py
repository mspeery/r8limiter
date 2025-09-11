import time
import math
import os
import pytest
import redis
from app.settings import settings
from app.main import LUA_SOURCE, bucket_key

r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
SCRIPT = r.register_script(LUA_SOURCE)

SCALE = settings.SUBTOKEN_SCALE

def run(user="u", res="r", cost=1, cap=4, rate=2.0, ttl=60, idem=None):
    keys = [bucket_key(user, res)]
    if idem:
        keys.append(f"idem:{user}:{res}:{idem}")
    args = [
        str(cap),
        str(int(rate * SCALE)),
        str(cost),
        str(SCALE),
        str(ttl),
        "15",
    ]
    allowed, retry_after_str, remaining_str, used_idem = SCRIPT(keys=keys, args=args)
    return int(allowed) == 1, float(retry_after_str), float(remaining_str)

def test_single_user_steady_rate():
    user, res = "u1", "r1"
    r.delete(bucket_key(user, res))
    # cap=4, rate=2 tps
    # Start full: consume 4
    for _ in range(4):
        ok, ra, rem = run(user, res, cap=4, rate=2.0)
        assert ok and ra == 0.0
    # Next should fail ~0.5s
    ok, ra, rem = run(user, res, cap=4, rate=2.0)
    assert not ok and 0.4 <= ra <= 0.6
    # Sleep 0.5s to allow 1 token
    time.sleep(0.5)
    ok, ra, rem = run(user, res, cap=4, rate=2.0)
    assert ok and ra == 0.0

def test_burst_capacity_then_throttle():
    user, res = "u2", "read"
    r.delete(bucket_key(user, res))
    # cap=3, rate=1 tps
    for _ in range(3):
        assert run(user, res, cap=3, rate=1.0)[0]
    ok, ra, _ = run(user, res, cap=3, rate=1.0)
    assert not ok and 0.9 <= ra <= 1.2
    time.sleep(1.0)
    assert run(user, res, cap=3, rate=1.0)[0]

def test_starvation_recovery():
    user, res = "u3", "write"
    r.delete(bucket_key(user, res))
    # cap=5, rate=2 tps
    for _ in range(5):
        assert run(user, res, cap=5, rate=2.0)[0]
    assert not run(user, res, cap=5, rate=2.0)[0]
    # Long sleep to ensure refill to cap (not beyond)
    time.sleep(2.8)  # > 5/2 = 2.5s
    # Spend 5 again
    for _ in range(5):
        assert run(user, res, cap=5, rate=2.0)[0]

def test_idempotency_avoids_double_spend():
    user, res = "u4", "pay"
    r.delete(bucket_key(user, res))
    # First call with Idempotency-Key should spend once
    ok1, ra1, rem1 = run(user, res, idem="abc123", cap=2, rate=1.0)
    assert ok1
    # Second call replays result without spending again
    ok2, ra2, rem2 = run(user, res, idem="abc123", cap=2, rate=1.0)
    assert ok2
    assert rem2 == rem1  # unchanged since cached
