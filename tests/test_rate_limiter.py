# test_rate_limiter.py
import math
import pytest
from app.core.rate_limiter import RateLimiter

class FakeClock:
    def __init__(self, start_ns: int = 0):
        self._now = start_ns
    def now_ns(self) -> int:
        return self._now
    def advance(self, seconds: float) -> None:
        self._now += int(seconds * 1_000_000_000)

def test_single_user_steady_rate():
    # 2 tokens/sec, capacity 4
    clk = FakeClock()
    rl = RateLimiter(4, 2.0, now_ns=clk.now_ns)

    # Start full: spend 4
    for _ in range(4):
        ok, wait = rl.allow("u1", "r1")
        assert ok and wait == 0.0

    # Next should fail; ~0.5s to accrue 1 token at 2 tps
    ok, wait = rl.allow("u1", "r1")
    assert not ok
    assert 0.4 <= wait <= 0.6

    # Advance 0.5s -> 1 token accrued -> allow
    clk.advance(0.5)
    ok, wait = rl.allow("u1", "r1")
    assert ok and wait == 0.0

def test_burst_capacity_then_throttle():
    # cap 3, 1 token/sec
    clk = FakeClock()
    rl = RateLimiter(3, 1.0, now_ns=clk.now_ns)

    # Burst 3
    for _ in range(3):
        ok, _ = rl.allow("uX", "read")
        assert ok

    # One more should be denied; ~1s to refill 1 token
    ok, wait = rl.allow("uX", "read")
    assert not ok
    assert 0.9 <= wait <= 1.1

    # After 1s, should pass
    clk.advance(1.0)
    ok, _ = rl.allow("uX", "read")
    assert ok

def test_starvation_recovery():
    # cap 5, 2 tps
    clk = FakeClock()
    rl = RateLimiter(5, 2.0, now_ns=clk.now_ns)

    # Drain fully
    for _ in range(5):
        assert rl.allow("u2", "write")[0]

    # Next should fail
    assert not rl.allow("u2", "write")[0]

    # Advance a long time -> should recover to full, not exceed capacity
    clk.advance(60.0)

    # We should be able to spend 5 again
    for _ in range(5):
        assert rl.allow("u2", "write")[0]

def test_isolation_by_key():
    clk = FakeClock()
    rl = RateLimiter(2, 1.0, now_ns=clk.now_ns)

    # Same user, different resource -> separate bucket
    assert rl.allow("uA", "r1")[0]
    assert rl.allow("uA", "r2")[0]
    # Reuse r1 bucket capacity
    assert rl.allow("uA", "r1")[0]
    # Next on r1 should fail now
    assert not rl.allow("uA", "r1")[0]
