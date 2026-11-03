"""Diagnostic: run the Georgia provider end to end against the live register.

An empty list must never be mistaken for an empty market, so this prints the
count, the page count and three sample rows with the registry facts attached.

    .venv/bin/python scripts/ge_check_registry.py --city ბათუმი --industry სასტუმრო
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from harvey.collectors.discover import DiscoveryQuery
from harvey.collectors.georgia import GeorgiaRegistry, nace_for, region_for


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="ბათუმი")
    ap.add_argument("--industry", default="სასტუმრო")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    provider = GeorgiaRegistry()
    query = DiscoveryQuery(term=args.industry, location=args.city, limit=args.limit)
    print(f"query: {query.term} / {query.location} → "
          f"NACE {nace_for(query.term)}, region {region_for(query.location)[0]}, "
          f"filter '{region_for(query.location)[1]}'")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            rows = await provider.fetch(client, {}, query)
        except Exception as exc:            # noqa: BLE001 — a diagnostic prints, never crashes
            print(f"ERROR: {type(exc).__name__}: {exc}")
            return 1

    print(f"found: {len(rows)} (limit {args.limit})")
    if not rows:
        print("EMPTY — check the NACE code and the city filter before reading this "
              "as 'nobody is there'")
        return 2

    for biz in rows[:3]:
        print(json.dumps({
            "name": biz.name,
            "external_id": biz.external_id,
            "phone": biz.phone,
            "domain": biz.domain,
            "has_website": biz.has_website,
            "address": biz.address[:70],
            "signals": {k: v[1] if v[1] else v[0] for k, v in biz.extra_signals.items()},
        }, ensure_ascii=False, indent=1))

    with_site = sum(1 for b in rows if b.domain)
    missing = sum(1 for b in rows if "GE_WEB_MISSING" in b.extra_signals)
    fresh = sum(1 for b in rows if "GE_NEW_REGISTRATION" in b.extra_signals)
    print(f"\nsummary: {len(rows)} entities · {with_site} with a site in the register · "
          f"{missing} with none (0.6 conf) · {fresh} registered in the last year")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
