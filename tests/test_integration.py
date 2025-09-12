import os
import time
import json
import httpx
import pytest

APP_URL = os.getenv("APP_URL", "http://app:8000")  # service name in docker compose

@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{APP_URL}/livez")
        assert r.status_code == 200
        r = await client.get(f"{APP_URL}/readyz")
        assert r.status_code == 200
        assert r.json().get("ready") is True

@pytest.mark.asyncio
async def test_allow_and_deny_and_retry_after_and_request_id():
    uid = "alice"
    rid = "itest-req-123"
    async with httpx.AsyncClient(timeout=5.0, headers={"X-Request-ID": rid}) as client:
        # Drain enough to force denies (defaults: cap=10, 5 rps)
        allowed_count = 0
        for _ in range(15):
            r = await client.post(f"{APP_URL}/allow", params={"user_id": uid, "resource": "read", "cost": 1})
            assert r.status_code in (200, 429)
            if r.status_code == 200:
                allowed_count += 1
            else:
                # Denied should return Retry-After and echo X-Request-ID
                assert "Retry-After" in r.headers
                assert r.headers.get("X-Request-ID") == rid
        assert allowed_count <= 11  # first burst around capacity

@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_text():
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{APP_URL}/metrics")
        assert r.status_code == 200
        text = r.text
        assert "# HELP requests_total" in text
        assert "requests_total{result=" in text
        assert "active_keys" in text
        assert "request_latency_seconds_bucket" in text

@pytest.mark.asyncio
async def test_admin_stats_and_user_and_resources_and_top_offenders():
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Ensure some denies for two users
        for user, n in [("alice", 20), ("bob", 12)]:
            for _ in range(n):
                await client.post(f"{APP_URL}/allow", params={"user_id": user, "resource": "read", "cost": 1})

        # admin/stats
        r = await client.get(f"{APP_URL}/admin/stats", params={"top_n": 5})
        assert r.status_code == 200
        data = r.json()
        assert "allowed_total" in data and "denied_total" in data
        assert "top_offenders" in data and isinstance(data["top_offenders"], list)
        # offender list should contain alice/bob with some denies
        offenders = {o["user_id"]: o["denies"] for o in data["top_offenders"]}
        assert any(u in offenders for u in ("alice", "bob"))

        # admin/user/<id>
        r = await client.get(f"{APP_URL}/admin/user/alice")
        assert r.status_code == 200
        ud = r.json()
        assert ud["user_id"] == "alice"
        assert isinstance(ud["resources"], list)
        if ud["resources"]:
            r0 = ud["resources"][0]
            assert "tokens" in r0
            assert "next_token_seconds" in r0
            assert "full_refill_seconds" in r0

        # admin/resources
        r = await client.get(f"{APP_URL}/admin/resources")
        assert r.status_code == 200
        rs = r.json()["resources"]
        assert isinstance(rs, dict)
        assert "read" in rs  # we used resource=read above
        assert "capacity" in rs["read"]
        assert "refill_rate_per_sec" in rs["read"]

        # windowed top-offenders
        r = await client.get(f"{APP_URL}/admin/top_offenders", params={"window": "15m", "bucket": "minute", "top_n": 5})
        assert r.status_code == 200
        to = r.json()
        assert "top_offenders" in to and isinstance(to["top_offenders"], list)
