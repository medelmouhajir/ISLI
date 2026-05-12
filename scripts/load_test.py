"""ISLI Load Test — Phase 7 Exit Criteria Validation

Simulates 20 concurrent agents hitting the Core API.
Usage: python scripts/load_test.py --base-url http://localhost:8000
"""

import asyncio
import argparse
import time
from typing import Any

import httpx


async def agent_worker(client: httpx.AsyncClient, agent_id: str, tasks: int) -> dict[str, Any]:
    successes = 0
    failures = 0
    latencies = []
    for i in range(tasks):
        start = time.monotonic()
        try:
            resp = await client.get("/health")
            if resp.status_code == 200:
                successes += 1
            else:
                failures += 1
        except Exception:
            failures += 1
        latencies.append(time.monotonic() - start)
    return {
        "agent_id": agent_id,
        "successes": successes,
        "failures": failures,
        "avg_latency": sum(latencies) / len(latencies),
        "p95_latency": sorted(latencies)[int(len(latencies) * 0.95)],
    }


async def run_load_test(base_url: str, agents: int = 20, tasks_per_agent: int = 100) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        print(f"[load_test] Starting {agents} agents x {tasks_per_agent} tasks against {base_url}")
        start = time.monotonic()
        workers = [
            agent_worker(client, f"agent_{i:03d}", tasks_per_agent)
            for i in range(agents)
        ]
        results = await asyncio.gather(*workers)
        duration = time.monotonic() - start

    total_successes = sum(r["successes"] for r in results)
    total_failures = sum(r["failures"] for r in results)
    all_latencies = [r["avg_latency"] for r in results]
    max_p95 = max(r["p95_latency"] for r in results)
    rps = (total_successes + total_failures) / duration

    print(f"\n[load_test] Completed in {duration:.1f}s")
    print(f"  Total requests: {total_successes + total_failures}")
    print(f"  Successes: {total_successes}")
    print(f"  Failures: {total_failures}")
    print(f"  RPS: {rps:.1f}")
    print(f"  Avg latency: {sum(all_latencies)/len(all_latencies):.3f}s")
    print(f"  Max p95 latency: {max_p95:.3f}s")

    if total_failures == 0 and rps > 50:
        print("[load_test] PASS")
    else:
        print("[load_test] FAIL")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--agents", type=int, default=20)
    parser.add_argument("--tasks", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(run_load_test(args.base_url, args.agents, args.tasks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
