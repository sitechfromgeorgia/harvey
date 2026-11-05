"""Seed the database from Georgian business directories.

The register knows who exists and almost never how to reach them. Directories
know the opposite. This script harvests them into Harvey's own database, so the
two layers join on the identification code.

Source: **compania.ge** — ~48,000 companies, and every company page publishes
schema.org JSON-LD with the identification code (`taxID`), the founder's name,
the phone and the address. That is a legal entity, a decision maker and a phone
in one request.

How the crawl stays cheap and polite:

* The directory is national, so every request is scoped twice —
  ``?search=<city>&category=<category>`` — and that pairing is what surfaces a
  city's businesses (category alone returns Tbilisi first, page after page).
* The listing card already carries the address, so cards that don't name the
  city are dropped **before** any detail request. One listing page (20 cards)
  costs one request; only the matches cost another.
* 1.2s between requests, a User-Agent that names us, no login, no paywall.

    python scripts/ge_seed.py --city ბათუმი --limit 300
    python scripts/ge_seed.py --city ქობულეთი --categories სასტუმრო,რესტორანი
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
CARD_RE = re.compile(r'<a[^>]+href="(/(\d{6,})/[a-z0-9-]+)"[^>]*>(.*?)</a>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def cards(html: str) -> list[tuple[str, str]]:
    """(href, card text) for every company card on a listing page."""
    out, seen = [], set()
    for href, _ident, inner in CARD_RE.findall(html):
        if href in seen:
            continue
        seen.add(href)
        out.append((href, " ".join(TAG_RE.sub(" ", inner).split())))
    return out


def parse_company(html: str) -> dict | None:
    """The schema.org Organization block, or None when the page has none."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(t in {"Organization", "LocalBusiness"} for t in types if t):
                return item
    return None


def to_company(org: dict, url: str, city: str,
               category: str) -> tuple[Company, dict[str, str]] | None:
    tax_id = re.sub(r"\D", "", str(org.get("taxID") or ""))
    name = (org.get("name") or "").strip()
    if not name:
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
        industry=category,
        location=city,
        source="seed:compania",
        source_url=url,
        external_id=f"compania:{tax_id or name}",
    )
    signals = {
        "GE_ID_CODE": tax_id,
        "GE_HEAD": head,
        "GE_PHONE": phone,
        "GE_ACTIVITY": category,
    }
    return company, {k: v for k, v in signals.items() if v}


MADLOBA_BASE = "https://madloba.info"
MADLOBA_CITY = {"batumi": "ბათუმი", "kobuleti": "ქობულეთი", "tbilisi": "თბილისი",
                "kutaisi": "ქუთაისი"}
MADLOBA_CATEGORY = {
    "hotels": "სასტუმრო", "restaurants": "რესტორანი", "construction-companies": "მშენებლობა",
    "beauty-salons": "სილამაზის სალონი", "dentistry": "სტომატოლოგია",
    "medical-centers": "კლინიკა", "pharmacies": "აფთიაქი", "car-rental": "ავტომობილების ქირაობა",
    "travel-agencies": "ტურისტული სააგენტო", "fitness-clubs": "სპორტული დარბაზი",
    "schools": "განათლება", "supermarkets": "სუპერმარკეტი",
    # Real slugs found on the city page (the directory uses Russian
    # transliterations, so the English guesses above mostly 404).
    "sportivnyye-kompleksy": "სპორტული დარბაზი",
    "sports-organizations-batumi": "სპორტული დარბაზი",
    "markets": "სუპერმარკეტი",
}
_ARTICLE_RE = re.compile(r'<article id="organization-(\d+)".*?</article>', re.S)
_FIELD = {
    "name": re.compile(r'organization-item__title">(.*?)</h3>', re.S),
    "address": re.compile(r'organization-item__address">(.*?)</address>', re.S),
    "phones": re.compile(r'organization-item__phones">(.*?)</p>', re.S),
    "description": re.compile(r'organization-item__description">(.*?)</div>', re.S),
    "href": re.compile(r'class="organization-item"\s+href="([^"]+)"'),
}


def _text(raw: str) -> str:
    from html import unescape
    return " ".join(unescape(TAG_RE.sub(" ", raw or "")).split())


def madloba_cards(html: str) -> list[dict]:
    """Cards from a madloba.info category page — no detail fetch needed."""
    out = []
    for match in _ARTICLE_RE.finditer(html):
        ident, block = match.group(1), match.group(0)
        card = {"ident": ident}
        for key, pattern in _FIELD.items():
            m = pattern.search(block)
            card[key] = m.group(1) if m else ""
        card["name"] = _text(card["name"])
        card["address"] = _text(card["address"])
        card["description"] = _text(card["description"])
        phones = re.findall(r"\+?\d[\d\s\-()]{7,}", _text(card["phones"]))
        card["phone"] = phones[0].strip() if phones else ""
        if card["name"]:
            out.append(card)
    return out


async def run_madloba(paths: list[str], pages: int, limit: int, db: str) -> int:
    """Seed from madloba.info: the phone is on the listing card, so one request
    per 16 businesses instead of one per business."""
    store = StateManager(db)
    await store.init_db()
    inserted, rows = 0, []
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "ka,en"},
                                 follow_redirects=True, timeout=TIMEOUT) as client:
        for path in paths[:limit]:
            city_slug, _, cat_slug = path.partition("/")
            city = MADLOBA_CITY.get(city_slug, city_slug)
            category = MADLOBA_CATEGORY.get(cat_slug, cat_slug)
            for page in range(1, pages + 1):
                url = f"{MADLOBA_BASE}/ka/{path}/?page={page}"
                resp = await client.get(url)
                await asyncio.sleep(PAUSE)
                if resp.status_code != 200:
                    print(f"  ! {path} page {page}: HTTP {resp.status_code}")
                    break
                found = madloba_cards(resp.text)
                print(f"  {path[:34]:34s} page {page}: {len(found)} cards")
                if not found:
                    break
                for card in found:
                    company = Company(
                        name=card["name"][:120],
                        phone=card["phone"],
                        description=card["description"][:400],
                        industry=category,
                        location=city,
                        source="seed:madloba",
                        source_url=MADLOBA_BASE + (card["href"] or ""),
                        external_id=f"madloba:{card['ident']}",
                    )
                    new = not company.id
                    cid = await store.add_company(company)
                    if new:
                        inserted += 1
                    for code, text in (("GE_PHONE", card["phone"]),
                                       ("GE_ACTIVITY", category)):
                        if text:
                            rows.append({"company_id": cid, "signal_code": code,
                                         "collector": "seed", "value_text": text,
                                         "confidence": 1.0,
                                         "evidence_url": MADLOBA_BASE + (card["href"] or "")})
    if rows:
        await store.add_observations(rows)
    print(f"\nseed(madloba): {len(paths)} categories · {inserted} new companies · "
          f"{len(rows)} observations")
    return 0


YPPO_BASE = "https://www.yp.com.ge"
_YP_ARTICLE = re.compile(r'<article class="com-content-category-blog__item.*?</article>', re.S)
_YP_FIELDS = {
    "name": re.compile(r'aria-label="Read more:\s*([^"]+)"'),
    "ident": re.compile(r'/en/organizations/org-(\d+)-en'),
    "address": re.compile(r'item-other-content-inner">\s*<p>(.*?)</p>', re.S),
    "phone": re.compile(r'href="tel:([^"]+)"'),
    "website": re.compile(r'Website:\s*<a href="([^"]+)"'),
    "category": re.compile(r'tag-list1"[^>]*>\s*([^<]+?)\s*</li>'),
}


def yp_cards(html: str) -> list[dict]:
    """Cards from a yp.com.ge listing page (Joomla, 20 per page)."""
    out = []
    for block in _YP_ARTICLE.findall(html):
        card = {}
        for key, pattern in _YP_FIELDS.items():
            m = pattern.search(block)
            card[key] = _text(m.group(1)) if m else ""
        if card.get("name") and card.get("ident"):
            out.append(card)
    return out


async def run_yp(city: str, pages: int, db: str) -> int:
    """Seed from yp.com.ge. The listing carries name, address, phone website —
    no detail request, and `?start=` is the whole pagination."""
    store = StateManager(db)
    await store.init_db()
    inserted, rows = 0, []
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "ka,en"},
                                 follow_redirects=True, timeout=TIMEOUT) as client:
        for page in range(pages):
            start = page * 20
            resp = await client.get(f"{YPPO_BASE}/en/organizations",
                                    params={"search": city, "start": start})
            await asyncio.sleep(PAUSE)
            if resp.status_code != 200:
                print(f"  ! page start={start}: HTTP {resp.status_code}")
                break
            found = [c for c in yp_cards(resp.text) if city.lower() in (c["address"] or "").lower()]
            print(f"  yp.com.ge start={start:>3}: {len(found)} in {city}")
            if not found:
                break
            for card in found:
                domain = ""
                site = card.get("website") or ""
                if site:
                    from harvey.collectors.discover import normalize_domain
                    domain = normalize_domain(site)
                company = Company(
                    name=card["name"][:120],
                    phone=card.get("phone", ""),
                    website=site,
                    domain=domain,
                    industry=card.get("category", "") or city,
                    location=city,
                    source="seed:yp.com.ge",
                    source_url=f"{YPPO_BASE}/en/organizations/org-{card['ident']}-en",
                    external_id=f"yppo:{card['ident']}",
                )
                new = not company.id
                cid = await store.add_company(company)
                if new:
                    inserted += 1
                for code, val in (("GE_PHONE", company.phone), ("GE_ACTIVITY", company.industry)):
                    if val:
                        rows.append({"company_id": cid, "signal_code": code,
                                     "collector": "seed", "value_text": val,
                                     "confidence": 1.0, "evidence_url": company.source_url})
    if rows:
        await store.add_observations(rows)
    print(f"\nseed(yp.com.ge): {inserted} new companies · {len(rows)} observations")
    return 0


async def run(city: str, categories: list[str], limit: int, pages: int, db: str) -> int:
    store = StateManager(db)
    await store.init_db()

    queue: list[tuple[str, str]] = []      # (href, category)
    seen: set[str] = set()
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "ka,en"},
                                 follow_redirects=True, timeout=TIMEOUT) as client:
        for category in categories:
            for page in range(1, pages + 1):
                if len(queue) >= limit:
                    break
                params = httpx.QueryParams({"search": city, "category": category, "page": page})
                resp = await client.get(f"{BASE}/companies?{params}")
                await asyncio.sleep(PAUSE)
                if resp.status_code != 200:
                    print(f"  ! {category} page {page}: HTTP {resp.status_code}")
                    break
                page_cards = cards(resp.text)
                keep = [(h, t) for h, t in page_cards if city.lower() in t.lower()]
                for href, _text in keep:
                    if href not in seen:
                        seen.add(href)
                        queue.append((href, category))
                print(f"  {category[:22]:22s} page {page:>2}: {len(page_cards):2d} cards, "
                      f"{len(keep):2d} in {city}")
                if not page_cards:
                    break

        inserted, rows = 0, []
        for href, category in queue[:limit]:
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
            parsed = to_company(org, url, city, category)
            if not parsed:
                continue
            company, signals = parsed
            new = not company.id
            cid = await store.add_company(company)
            if new:
                inserted += 1
            for code, text in signals.items():
                rows.append({
                    "company_id": cid, "signal_code": code, "collector": "seed",
                    "value_text": text, "confidence": 1.0, "evidence_url": url,
                })
            print(f"  + {company.name[:32]:32s} {company.phone[:16]:16s} "
                  f"{signals.get('GE_ID_CODE', ''):>12s}  {category[:18]}")

        if rows:
            await store.add_observations(rows)

    print(f"\nseed: {len(queue[:limit])} company pages read · {inserted} new companies · "
          f"{len(rows)} observations · {city} · {len(categories)} categories")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="compania", choices=("compania", "madloba", "yppo"))
    ap.add_argument("--city", default="ბათუმი")
    ap.add_argument("--categories", default="",
                    help="comma-separated Georgian categories (default: the ICP's industries)")
    ap.add_argument("--paths", default="",
                    help="madloba only: comma-separated city/category slugs, "
                         "e.g. batumi/hotels,batumi/restaurants")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--db", default="data/harvey.db")
    args = ap.parse_args()

    if args.source == "yppo":
        return asyncio.run(run_yp(args.city, args.pages, args.db))

    if args.source == "madloba":
        paths = [p.strip() for p in args.paths.split(",") if p.strip()] or [
            "batumi/hotels", "batumi/restaurants", "batumi/construction-companies"]
        return asyncio.run(run_madloba(paths, args.pages, args.limit, args.db))

    if args.categories:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    else:
        from harvey.config import load_config
        categories = list(load_config("harvey.local.yaml").icp.industries)
    return asyncio.run(run(args.city, categories, args.limit, args.pages, args.db))


if __name__ == "__main__":
    raise SystemExit(main())
