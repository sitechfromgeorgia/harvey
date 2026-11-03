"""Seed the database from Georgian business directories.

The register knows who exists and almost never how to reach them. Directories
know the opposite. This script harvests the directories into Harvey's own
database, so the two layers join on the identification code.

First source: **compania.ge** — ~48,000 companies, and every company page
publishes schema.org JSON-LD with the identification code (taxID), the founder's
name, the phone and the address. That is a seed worth having: taxID joins the row
to the register, the founder is the decision maker, the phone is the contact.

Only public pages, one request every 1.2s, with a User-Agent that names us.
Politeness is not decoration: a directory that blocks us costs more than the
data is worth.

    python scripts/ge_seed.py --city ბათუმი --limit 80
    python scripts/ge_seed.py --city ბათუმი --limit 400 --pages 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from harvey.models import Company
from harvey.state import StateManager

UA = "harvey-ge/0.1 (SiTech sales research; hello@sitech.ge)"
TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)
BASE = "https://compania.ge"
PAUSE = 1.2
LINK_RE = re.compile(r'href="(/(\d{6,})/[a-z0-9-]+)"')


def parse_company(html: str) -> dict | None:
    """The schema.org Organization block, or None when the page has none."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            types = item.get("@type") if isinstance(item, dict) else None
            types = types if isinstance(types, list) else [types]
            if not isinstance(item, dict):
                continue
            if any(t in {"Organization", "LocalBusiness"} for t in types if t):
                return item
    return None


def to_company(org: dict, url: str, city: str) -> tuple[Company, dict[str, str]] | None:
    tax_id = re.sub(r"\D", "", str(org.get("taxID") or ""))
    name = (org.get("name") or "").strip()
    if not name:
        return None
    # The directory is national; keep a row only when its own text places it.
    blob = " ".join(str(org.get(k) or "") for k in ("description", "taxID", "name"))
    addr = org.get("address") or {}
    if isinstance(addr, dict):
        blob += " " + " ".join(str(addr.get(k) or "") for k in
                               ("streetAddress", "addressLocality", "addressRegion"))
    if city and city.lower() not in blob.lower() and city not in url:
        return None

    founder = org.get("founder") or {}
    if isinstance(founder, list):
        founder = founder[0] if founder else {}
    head = (founder.get("name") if isinstance(founder, dict) else "") or ""
    phone = (org.get("telephone") or "").strip()
    company = Company(
        name=name,
        phone=phone,
        description=(org.get("description") or "")[:400],
        location=city,
        source="seed:compania",
        source_url=url,
        external_id=f"compania:{tax_id or name}",
    )
    signals = {
        "GE_ID_CODE": tax_id,
        "GE_HEAD": head,
        "GE_PHONE": phone,
    }
    return company, {k: v for k, v in signals.items() if v}


async def run(city: str, limit: int, pages: int, db: str) -> int:
    store = StateManager(db)
    await store.init_db()

    seen: set[str] = set()
    links: list[str] = []
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "ka,en"},
                                 follow_redirects=True, timeout=TIMEOUT) as client:
        for page in range(1, pages + 1):
            if len(links) >= limit:
                break
            params = httpx.QueryParams({"search": city, "page": page})
            resp = await client.get(f"{BASE}/companies?{params}")
            if resp.status_code != 200:
                print(f"listing page {page}: HTTP {resp.status_code} — stopping")
                break
            found = [href for href, _ in LINK_RE.findall(resp.text)]
            new = [h for h in found if h not in seen]
            for href in new:
                seen.add(href)
                links.append(href)
            print(f"listing page {page}: {len(found)} links ({len(new)} new)")
            if not found:
                break
            await asyncio.sleep(PAUSE)

        inserted = 0
        rows: list[dict] = []
        for href in links[:limit]:
            url = BASE + href
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                print(f"  ! {href}: {type(exc).__name__}")
                continue
            await asyncio.sleep(PAUSE)
            if resp.status_code != 200:
                continue
            org = parse_company(resp.text)
            if not org:
                continue
            parsed = to_company(org, url, city)
            if not parsed:
                continue
            company, signals = parsed
            before = company.id
            cid = await store.add_company(company)
            if not before:
                inserted += 1
            for code, text in signals.items():
                rows.append({
                    "company_id": cid, "signal_code": code, "collector": "seed",
                    "value_text": text, "confidence": 1.0, "evidence_url": url,
                })
            print(f"  + {company.name[:34]:34s} {company.phone[:16]:16s} {signals.get('GE_ID_CODE', '')}")

        if rows:
            await store.add_observations(rows)
    print(f"\nseeded: {len(links[:limit])} pages read · {inserted} new companies · "
          f"{len(rows)} observations")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="ბათუმი")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--db", default="data/harvey.db")
    args = ap.parse_args()
    return asyncio.run(run(args.city, args.limit, args.pages, args.db))


if __name__ == "__main__":
    raise SystemExit(main())
