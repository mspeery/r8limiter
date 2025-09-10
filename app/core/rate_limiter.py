# rate_limiter.py
from __future__ import annotations
import time
import threading
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Dict, Tuple, Optional

# ------- Core Token Bucket ------- #

@dataclass
class Bucket:
    capacity: int                  # max whole tokens in the bucket
    refill_rate_per_sec: float     # tokens per second
    tokens: float                  # current tokens (float; capped at capacity)
    last_refill_ts: int            # last refill time (monotonic ns)
    lock: threading.Lock           # protects tokens + last_refill_ts


class RateLimiter:
    """
    Per-(user_id, resource) token-bucket rate limiter using a monotonic clock.
    Each bucket tracks: capacity, refill_rate_per_sec, tokens, last_refill_ts.
    """

    def __init__(
        self, 
        default_capacity: int, 
        default_refill_rate_per_sec: float, 
        *, 
        now_ns: Callable[[], int] = time.monotonic_ns
    ):
        if default_capacity < 0:
            raise ValueError("default_capacity must be > 0")
        if default_refill_rate_per_sec <= 0:
            raise ValueError("default_refill_rate_per_sec must be > 0")

        self._default_cap = default_capacity
        self._default_refill = default_refill_rate_per_sec
        self._now_ns = now_ns

        self._buckets: Dict[Tuple[str, str], Bucket] = {}
        self._buckets_lock = threading.Lock()


    def _get_or_create(
        self,
        user_id: str,
        resource: str,
        *,
        capacity: Optional[int] = None,
        refill_rate_per_sec: Optional[float] = None,
    ) -> Bucket:
        key = (user_id, resource)

        # Create lazily
        with self._buckets_lock:
            b = self._buckets.get(key)
            if b is None:
                cap = capacity if capacity is not None else self._default_cap
                rate = (
                    refill_rate_per_sec
                    if refill_rate_per_sec is not None
                    else self._default_refill
                )
                b = Bucket(
                    capacity=cap,
                    refill_rate_per_sec=rate,
                    tokens=float(cap),                 # start full
                    last_refill_ts=self._now_ns(),
                    lock=threading.Lock(),
                )
                self._buckets[key] = b
        return b



    def _refill_locked(self, b: Bucket, now_ns: int) -> None:
        if now_ns <= b.last_refill_ts:
            return
        elapsed_ns = now_ns - b.last_refill_ts
        elapsed_secs = elapsed_ns / 1_000_000_000
        
        if elapsed_ns <= 0.0:
            return

        # Refill by (rate * elapsed), capped at capacity.
        if b.tokens < b.capacity:
            b.tokens = min(b.capacity, b.tokens + b.refill_rate_per_sec * elapsed_secs)
        # Always move the clock forward for correctness.
        b.last_refill_ts = now_ns
    # -------- public API --------

    def allow(
        self,
        user_id: str,
        resource: str = "default",
        *,
        cost: int = 1,
        capacity: Optional[int] = None,
        refill_rate_per_sec: Optional[float] = None,
    ) -> tuple[bool, float]:
        """
        Try to spend `cost` tokens from (user_id, resource).
        Returns (allowed, retry_after_seconds).
        If denied, retry_after_seconds tells the caller when 1 more token will be available.
        """
        if cost <= 0:
            raise ValueError("cost must be > 0")

        b = self._get_or_create(
            user_id,
            resource,
            capacity=capacity,
            refill_rate_per_sec=refill_rate_per_sec,
        )
        now = self._now_ns()

        with b.lock:
            self._refill_locked(b, now)

            if b.tokens >= cost:
                b.tokens -= cost
                return True, 0.0

            # Not enough tokens: compute wait for one token (minimum info required)
            # You could also compute exact wait for `cost`, but 1-token wait is standard.
            deficit = max(0.0, 1.0 - (b.tokens if cost == 1 else 0.0))
            # If cost > 1 and we're short, computing exact time until `cost` tokens:
            need = max(0.0, float(cost) - b.tokens)
            wait = need / b.refill_rate_per_sec
            return False, wait