import asyncio
import json
import pytest

@pytest.mark.anyio
async def test_metrics_exposes_prometheus_text(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "# HELP requests_total" in text
    assert 'requests_total{result=' in text
    # active_keys gauge should be present (may be 0)
    assert "active_keys" in text

@pytest.mark.anyio
async def test_admin_stats_user_resources_and_offenders(client):
    # Generate some traffic and denials
    for user, n in (("alice", 30), ("bob", 20)):
        for _ in range(n):
            await client.post("/allow", params={"user_id": user, "resource": "read", "cost": 1})

    # /admin/stats
    r = await client.get("/admin/stats", params={"top_n": 5})
    assert r.status_code == 200
    data = r.json()
    assert "allowed_total" in data and "denied_total" in data
    assert "top_offenders" in data and isinstance(data["top_offenders"], list)
    offenders = {o.get("user_id"): o.get("denies", 0) for o in data["top_offenders"]}
    assert any(u in offenders for u in ("alice", "bob"))

    # /admin/user/{id}
    ru = await client.get("/admin/user/alice")
    assert ru.status_code == 200
    ud = ru.json()
    assert ud.get("user_id") == "alice"
    assert isinstance(ud.get("resources", []), list)
    if ud["resources"]:
        r0 = ud["resources"][0]
        assert "tokens" in r0
        assert "next_token_seconds" in r0
        assert "full_refill_seconds" in r0

    # /admin/resources
    rr = await client.get("/admin/resources")
    assert rr.status_code == 200
    rd = rr.json()
    assert "resources" in rd
    # Structure sanity: dict of resource -> object
    assert isinstance(rd["resources"], dict)
