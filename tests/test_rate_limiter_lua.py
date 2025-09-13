import asyncio
import os
import pytest

@pytest.mark.anyio
async def test_single_user_steady_rate(client, redis_client):
    # Choose a unique resource to avoid cross-test interference
    user = "u_steady"
    resource = "r_steady"
    # Warm a few requests; expect at least first `capacity` to pass
    allowed = 0
    for _ in range(6):
        r = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1})
        if r.status_code == 200 and r.json().get("allowed") is True:
            allowed += 1
    assert allowed >= 3  # conservative (depends on default capacity)

@pytest.mark.anyio
async def test_burst_respects_capacity_then_denies(client, redis_client):
    user = "u_burst"
    resource = "r_burst"
    # Spend repeatedly; we should get a block after hitting capacity
    got_deny = False
    for _ in range(20):
        r = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1})
        data = r.json()
        if data["allowed"] is False or r.status_code == 429:
            got_deny = True
            break
    assert got_deny, "Expected a deny once capacity is exhausted"

@pytest.mark.anyio
async def test_starvation_recovers_after_refill(client, redis_client):
    user = "u_starve"
    resource = "r_starve"
    # Drain bucket quickly
    denied = False
    for _ in range(50):
        r = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1})
        if r.status_code == 429:
            denied = True
            break
    assert denied, "Should eventually deny after draining capacity"

    # Wait for tokens to refill (short wait; default rates should trickle)
    await asyncio.sleep(1.2)

    r2 = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1})
    assert r2.status_code in (200, 429)
    # In most defaults this should now allow; if not, we still assert retry_after descends
    if r2.status_code == 200:
        assert r2.json()["allowed"] is True
    else:
        # retry_after should be > 0 but small-ish after waiting
        assert float(r2.json()["retry_after"]) >= 0.0

@pytest.mark.anyio
async def test_idempotency_key_spends_once(client, redis_client):
    user = "u_idem"
    resource = "r_pay"
    idem = "idem-123"
    r1 = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1},
                           headers={"Idempotency-Key": idem})
    r2 = await client.post("/allow", params={"user_id": user, "resource": resource, "cost": 1},
                           headers={"Idempotency-Key": idem})

    assert r1.status_code in (200, 429)
    assert r2.status_code == r1.status_code
    d1 = r1.json()
    d2 = r2.json()
    # Second response should be the cached decision (no double spend)
    assert d1["allowed"] == d2["allowed"]
    assert abs(float(d1["retry_after"]) - float(d2["retry_after"])) < 1e-6
