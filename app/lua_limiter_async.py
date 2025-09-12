from __future__ import annotations
import hashlib
from typing import Tuple
import redis.asyncio as redis

class AsyncLuaLimiter:
    def __init__(self, r: redis.Redis, script_text: str):
        self.r = r
        self.script_text = script_text
        self.sha = hashlib.sha1(script_text.encode("utf-8")).hexdigest()

    async def allow(
        self,
        *,
        bucket_key: str,
        capacity_tokens: int,
        rate_subtokens_per_sec: int,
        cost_tokens: int,
        scale: int,
        ttl_seconds: int,
        idem_key: str = "",
        idempotency_ttl_seconds: int = 60,
    ) -> Tuple[bool, float, float, bool]:
        keys = [bucket_key, idem_key]
        argv = [
            str(capacity_tokens),
            str(rate_subtokens_per_sec),
            str(cost_tokens),
            str(scale),
            str(ttl_seconds),
            str(idempotency_ttl_seconds),
        ]
        try:
            res = await self.r.evalsha(self.sha, len(keys), *keys, *argv)
        except redis.ResponseError:
            res = await self.r.eval(self.script_text, len(keys), *keys, *argv)
        allowed = bool(int(res[0]))
        retry_after = float(res[1])
        remaining = float(res[2])
        used_idem = bool(int(res[3]))
        return allowed, retry_after, remaining, used_idem
