#!/usr/bin/env python
"""Elevate demo/test simulation suite — CLI.

Drives synthetic customer activity through the REAL pipeline (record_event →
anomaly detection → run_decision_cycle → guard → interceptor → ledger). No mocks:
the only thing faked is that a human isn't the one browsing. Dev/demo only — this
is why the merchant terminal carries no "simulate" button.

Run inside the api container (so it shares the server's DB + Redis):

  docker compose exec api python scripts/demo_sim.py --list
  docker compose exec api python scripts/demo_sim.py --store burger-blitz --scenario velocity_spike --customers 20
  docker compose exec api python scripts/demo_sim.py --store burger-blitz --proactive review
  docker compose exec api python scripts/demo_sim.py --store burger-blitz --all   # every trigger; seeds demo state

Note: this runs OUT of the server process, so a newly-created card won't push over
an already-open terminal's WebSocket — refresh the terminal to see it.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # so a cp1252 console can print the arrows in scenario text
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app.services.simulation import (  # noqa: E402
    SCENARIOS,
    PROACTIVE,
    run_reactive_scenario,
    run_proactive,
)


async def _drive(db_factory, redis, store, *, scenario=None, proactive=None, customers=30):
    async with db_factory() as db:
        if proactive:
            res = await run_proactive(store, proactive, db, redis)
        else:
            res = await run_reactive_scenario(store, scenario, customers, db, redis)
        await db.commit()
    return res


async def _main_async(args):
    from app.core.database import get_session_factory
    from app.core.redis import get_redis

    factory = get_session_factory()
    redis = await get_redis()
    try:
        if args.all:
            results = []
            for sc in SCENARIOS:
                print(f"-> {sc} ...", flush=True)
                results.append(await _drive(factory, redis, args.store, scenario=sc, customers=args.customers))
                await asyncio.sleep(1.0)  # let each decision settle before the next signal
            for pk in PROACTIVE:
                print(f"-> proactive:{pk} ...", flush=True)
                results.append(await _drive(factory, redis, args.store, proactive=pk))
                await asyncio.sleep(1.0)
            return results
        if args.proactive:
            return await _drive(factory, redis, args.store, proactive=args.proactive)
        return await _drive(factory, redis, args.store, scenario=args.scenario, customers=args.customers)
    finally:
        # Close Redis explicitly so its connection isn't GC'd after the loop
        # closes (which prints a harmless-but-ugly "Event loop is closed").
        try:
            await redis.aclose()
        except AttributeError:  # older redis-py
            try:
                await redis.close()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass


def main():
    p = argparse.ArgumentParser(
        description="Elevate demo simulation suite — real pipeline, no mocks."
    )
    p.add_argument("--store", help="store slug, e.g. burger-blitz")
    p.add_argument("--scenario", choices=list(SCENARIOS), help="reactive scenario to fire")
    p.add_argument("--proactive", choices=list(PROACTIVE), help="proactive check to fire")
    p.add_argument("--customers", type=int, default=30, help="simulated customer count (default 30)")
    p.add_argument("--all", action="store_true",
                   help="fire every scenario in sequence — seeds the state screenshots need")
    p.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = p.parse_args()

    if args.list:
        print("Reactive scenarios (customer activity -> the right specialist):")
        for k, v in SCENARIOS.items():
            print(f"  {k:20} {v}")
        print("\nProactive scenarios (no customer needed - Qwen looks for a problem):")
        for k, v in PROACTIVE.items():
            print(f"  {k:20} {v}")
        return

    if not args.store:
        p.error("--store is required (or use --list)")
    if not (args.all or args.proactive or args.scenario):
        p.error("pick one of --scenario, --proactive, or --all (or --list)")

    res = asyncio.run(_main_async(args))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
