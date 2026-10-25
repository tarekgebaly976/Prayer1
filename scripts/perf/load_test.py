"""Simple concurrent load test against a running API (no external tools needed).

    python scripts/perf/load_test.py --base http://127.0.0.1:8000 --users 20 --seconds 40
Uses demo users; reports per-endpoint p50/p95/p99 latency, throughput and error rate."""

import argparse
import asyncio
import os
import random
import statistics
import time
from collections import defaultdict

import httpx

USERS = ["manager", "planner", "mech.sup", "tech1", "tech2", "reliability", "engineer", "viewer"]


async def session(base: str, who: str, pw: str) -> tuple[httpx.AsyncClient, dict]:
    c = httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=60)
    r = await c.post("/auth/login", json={"email": f"{who}@demo.example.com", "password": pw})
    r.raise_for_status()
    h = {"X-Plant-Id": r.json()["plants"][0]["plant_id"], "Cookie": f"cmms_session={r.cookies['cmms_session']}"}
    return c, h


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=40)
    a = ap.parse_args()
    pw = os.environ.get("E2E_PASSWORD", "Demo-Passw0rd!2026")
    sessions = [await session(a.base, USERS[i % len(USERS)], pw) for i in range(a.users)]
    c0, h0 = sessions[0]
    pm1 = (await c0.get("/assets", params={"q": "PM1", "limit": 1}, headers=h0)).json()["items"][0]["id"]
    some_wo = (await c0.get("/work-orders", params={"limit": 1}, headers=h0)).json()["items"][0]["id"]
    endpoints = {
        "wo_list_page": lambda: ("/work-orders", {"limit": 50, "open_only": True}),
        "wo_search": lambda: ("/work-orders", {"q": f"LT-WO-{random.randint(1, 50000):07d}", "limit": 50}),
        "wo_detail": lambda: (f"/work-orders/{some_wo}/detail", None),
        "asset_search": lambda: ("/assets", {"q": f"LT-{random.randint(1, 100000):06d}", "limit": 50}),
        "asset_children_100k": lambda: ("/assets/tree", {"parent_id": pm1}),
        "dashboard": lambda: ("/dashboard/summary", None),
        "kpis_month": lambda: ("/kpis", None),
    }
    lat: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    forbidden: dict[str, int] = defaultdict(int)  # expected: e.g. technicians have no kpi.view
    stop = time.monotonic() + a.seconds

    async def worker(c: httpx.AsyncClient, h: dict) -> None:
        while time.monotonic() < stop:
            name = random.choice(list(endpoints))
            path, params = endpoints[name]()
            t = time.perf_counter()
            try:
                r = await c.get(path, params=params, headers=h)
                ok = r.status_code in (200, 403)
                forbidden[name] += r.status_code == 403
            except httpx.HTTPError:
                ok = False
            lat[name].append((time.perf_counter() - t) * 1000)
            errors[name] += not ok

    t0 = time.monotonic()
    await asyncio.gather(*(worker(c, h) for c, h in sessions))
    dur = time.monotonic() - t0
    total = sum(len(v) for v in lat.values())
    print(f"users={a.users} duration={dur:.0f}s requests={total} throughput={total / dur:.1f} req/s "
          f"errors={sum(errors.values())} expected_403={sum(forbidden.values())}")
    print(f"{'endpoint':22} {'n':>6} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'err':>4} {'403':>4}")
    for k in endpoints:
        v = sorted(lat[k])
        if not v:
            continue
        q = statistics.quantiles(v, n=100) if len(v) > 1 else [v[0]] * 99
        print(f"{k:22} {len(v):6d} {q[49]:8.0f} {q[94]:8.0f} {q[98]:8.0f} {errors[k]:4d} {forbidden[k]:4d}")
    for c, _ in sessions:
        await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
