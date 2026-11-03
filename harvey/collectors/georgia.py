"""Georgia — the statistical business register as a discovery source.

Why this exists at all: every provider Harvey shipped with is American or
global. OpenStreetMap maps premises (thin in Georgia), DataForSEO and Serper
are paid and shallow here, and neither knows a company's identification code,
its legal form, its declared size, or who its director is. Georgia's public
registers do, and Geostat's business register exposes them over an open JSON
API — no key, no account, no credit.

The reverse-engineered contract (endpoint shape, field names, NACE filter,
rate limits, personal-data warning) comes from `sitechfromgeorgia/ordo-mcp`,
the MCP server the legal lane uses. This provider does not import it: a fork
that cannot start because a sibling checkout moved is a bad fork. The API is
plain JSON, so it is called directly, and ordo-mcp stays the reference and the
source for the sources this provider does *not* cover (NAPR extracts, liens,
companyinfo financials, court practice).

Two facts shape the mapping below:

* **A company in this register has no "category", it has a NACE code.** The
  ICP is written in human words ("სასტუმრო", "hotel"), so terms are mapped to
  NACE codes here. An unmapped term is a loud error, never a zero-result run —
  a silent empty list is the one failure mode this project refuses.
* **The register's `web` field is empty far more often than it is wrong.** So
  an empty field is recorded as `GE_WEB_MISSING` at 0.6 confidence, not as the
  `NO_WEBSITE` signal at 1.0. Selling a website to someone who already has one
  is the most expensive mistake this pipeline can make, and the profile stage
  can still confirm it for free.

Rate limit: the register answers ~50 requests/minute, so this provider
serialises its page requests with a 1.2s gap, exactly as ordo-mcp does.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import httpx

from harvey.collectors.discover import Business, DiscoveryProvider, DiscoveryQuery, \
    normalize_domain

# ── The register's own vocabulary ────────────────────────────────────────

BASE = "https://br-api.geostat.ge/api"
SOURCE_URL = "https://br.geostat.ge/"
CITE = "წყარო: საქსტატი — ბიზნეს რეგისტრი (br.geostat.ge)"

REGIONS: dict[str, str] = {
    "11": "ქ. თბილისი",
    "12": "აფხაზეთი",
    "15": "აჭარა",
    "23": "გურია",
    "26": "იმერეთი",
    "29": "კახეთი",
    "32": "მცხეთა-მთიანეთი",
    "35": "რაჭა-ლეჩხუმი და ქვემო სვანეთი",
    "38": "სამეგრელო-ზემო სვანეთი",
    "41": "სამცხე-ჯავახეთი",
    "44": "ქვემო ქართლი",
    "47": "შიდა ქართლი",
}

# City → (region code, the substring the register writes in a legal address).
# Region alone is too coarse: "აჭარა" spans Batumi, Kobuleti and Keda. The
# address filter is what makes "ბათუმი" mean Batumi rather than Adjara.
CITIES: dict[str, tuple[str, str]] = {
    "ბათუმი": ("15", "ბათუმი"),
    "batumi": ("15", "ბათუმი"),
    "ქობულეთი": ("15", "ქობულეთი"),
    "kobuleti": ("15", "ქობულეთი"),
    "თბილისი": ("11", "თბილისი"),
    "tbilisi": ("11", "თბილისი"),
    "ქუთაისი": ("26", "ქუთაისი"),
    "kutaisi": ("26", "ქუთაისი"),
    "ზუგდიდი": ("38", "ზუგდიდი"),
    "zugdidi": ("38", "ზუგდიდი"),
    "ფოთი": ("38", "ფოთი"),
    "poti": ("38", "ფოთი"),
    "რუსთავი": ("44", "რუსთავი"),
    "rustavi": ("44", "რუსთავი"),
    "გორი": ("47", "გორი"),
    "gori": ("47", "გორი"),
    "თელავი": ("29", "თელავი"),
    "telavi": ("29", "თელავი"),
    "ოზურგეთი": ("23", "ოზურგეთი"),
    "ozurgeti": ("23", "ოზურგეთი"),
    "ახალციხე": ("41", "ახალციხე"),
    "akhaltsikhe": ("41", "ახალციხე"),
    "მცხეთა": ("32", "მცხეთა"),
    "mtskheta": ("32", "მცხეთა"),
    "ამბროლაური": ("35", "ამბროლაური"),
    "ambrolauri": ("35", "ამბროლაური"),
}

# Industry words → NACE rev.2 code (the section letter is stripped by the API).
# Every entry is a real code in the register; Georgian and English aliases sit
# side by side because the ICP may be written either way.
NACE: dict[str, str] = {
    # hospitality
    "სასტუმრო": "55.10", "სასტუმროები": "55.10", "hotel": "55.10", "hotels": "55.10",
    "guesthouse": "55.20", "გესთჰაუსი": "55.20", "საოჯახო სასტუმრო": "55.20",
    "რესტორანი": "56.10", "restaurant": "56.10", "restaurants": "56.10",
    "კაფე": "56.30", "ბარი": "56.30", "cafe": "56.30", "bar": "56.30",
    "ტურისტული სააგენტო": "79.11", "travel agency": "79.11",
    # retail
    "მაღაზია": "47.19", "shop": "47.19", "retail": "47.19",
    "სუპერმარკეტი": "47.11", "supermarket": "47.11",
    "აფთიაქი": "47.73", "pharmacy": "47.73",
    # services
    "სილამაზის სალონი": "96.02", "beauty salon": "96.02", "barbershop": "96.02",
    "სპორტული დარბაზი": "93.13", "fitness": "93.13", "gym": "93.13",
    "სარემონტო": "43.39", "construction": "41.20", "მშენებლობა": "41.20",
    "უძრავი ქონება": "68.31", "real estate": "68.31",
    "იურიდიული": "69.10", "law firm": "69.10", "legal": "69.10",
    "ბუღალტრული": "69.20", "accounting": "69.20",
    "კლინიკა": "86.21", "clinic": "86.21", "სამედიცინო": "86.21",
    "სტომატოლოგია": "86.23", "dentist": "86.23",
    "ავტო": "45.11", "car dealer": "45.11", "ავტომობილების ქირაობა": "77.11",
    "car rental": "77.11",
    "ტრანსპორტი": "49.41", "transport": "49.41", "logistics": "52.29",
    "IT": "62.01", "პროგრამირება": "62.01", "software": "62.01",
    "მარკეტინგი": "73.11", "marketing": "73.11", "რეკლამა": "73.11",
    "განათლება": "85.59", "education": "85.59", "სასწავლო ცენტრი": "85.59",
}

LEGAL_FORMS: dict[str, str] = {
    "შპს": "LLC (შპს)",
    "სს": "JSC (სს)",
    "ინდივიდუალური მეწარმე": "Individual entrepreneur (IE)",
    "ი/მ": "Individual entrepreneur (IE)",
    "კოოპერატივი": "Cooperative",
    "ა(ა)იპ": "Non-profit (N(N)LE)",
    "ფიზიკური პირი": "Natural person",
}

MIN_INTERVAL = 1.2          # seconds between page requests (~50/min)
NEW_REGISTRATION_DAYS = 365  # "recently registered" window for the trigger signal


def region_for(city: str) -> tuple[str, str]:
    """City → (region code, address filter). Unknown city is an error, not silence."""
    key = (city or "").strip().lower()
    if key in CITIES:
        return CITIES[key]
    for name, pair in CITIES.items():
        if name and name in key:
            return pair
    raise ValueError(
        f"unknown Georgian city '{city}' — add it to georgia.CITIES with its "
        f"region code and the address substring the register writes")


def nace_for(term: str) -> str:
    """Industry word → NACE code. Unmapped is an explicit error."""
    key = (term or "").strip()
    if key in NACE:
        return NACE[key]
    low = key.lower()
    if low in NACE:
        return NACE[low]
    for name, code in NACE.items():
        if len(name) > 3 and name in low:
            return code
    raise ValueError(
        f"no NACE code for '{term}' — add it to georgia.NACE (see "
        f"https://br.geostat.ge for the rev.2 code of the activity)")


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _date(value) -> date | None:
    raw = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def to_business(item: dict, *, query: DiscoveryQuery) -> Business:
    """One register row → a Business, with the registry facts as extra signals.

    Pure and offline: this is the function the tests exercise, because it is
    where every mapping decision lives.
    """
    web = (item.get("web") or "").strip()
    domain = normalize_domain(web) if web else ""
    registered = _date(item.get("registered"))
    name = (item.get("name") or "").strip()
    extra: dict[str, tuple[float | None, str, float]] = {}

    def add(code: str, text: str = "", num: float | None = None, conf: float = 1.0) -> None:
        if text or num is not None:
            extra[code] = (num, text, conf)

    id_code = _digits(item.get("id_code"))
    add("GE_ID_CODE", id_code)
    add("GE_LEGAL_FORM", (item.get("legal_form") or "").strip())
    add("GE_SIZE", (item.get("size") or "").strip())
    add("GE_ACTIVITY", (item.get("activity") or "").strip())
    add("GE_HEAD", (item.get("head") or "").strip())
    add("GE_PHONE", (item.get("phone") or "").strip())
    add("GE_EMAIL", (item.get("email") or "").strip())
    if registered:
        add("GE_REGISTERED", registered.isoformat())
        age = (date.today() - registered).days
        if 0 <= age <= NEW_REGISTRATION_DAYS:
            add("GE_NEW_REGISTRATION", f"{age}d old, registered {registered.isoformat()}", num=1.0)
    if not web:
        # Honest confidence: an empty field is not proof of no site.
        add("GE_WEB_MISSING", "register has no web field for this entity", num=1.0, conf=0.6)

    return Business(
        name=name,
        domain=domain,
        website=f"https://{domain}" if domain else "",
        phone=(item.get("phone") or "").strip(),
        address=(item.get("legal_address") or item.get("actual_address") or "").strip(),
        location=query.location,
        category=(item.get("activity") or "").strip(),
        # None, not False: the profile stage decides. See the module docstring.
        has_website=True if domain else None,
        external_id=f"geostat:{id_code or item.get('stat_id')}",
        source_url=SOURCE_URL,
        provider="georgia_registry",
        extra_signals=extra,
    )


class GeorgiaRegistry(DiscoveryProvider):
    """Geostat business register — free, no key, and the only source here that
    knows a company's identification code, legal form, declared size and
    director."""

    key = "georgia_registry"
    label = "Georgia — Geostat business register"
    kind = "listings"
    needs_coordinates = False
    blurb = (
        "საქართველოს საქსტატის ბიზნეს რეგისტრი: ~1.15 მლნ სუბიექტი NACE "
        "საქმიანობით, ზომით, იურიდიული მისამართით, ხელმძღვანელით და "
        "რეგისტრაციის თარიღით. უფასო, გასაღების გარეშე."
    )
    cost_note = "free (open API, ~50 requests/minute)"
    free_tier = "unlimited, rate-limited to 1 page / 1.2s"
    signup_url = "https://br.geostat.ge/"
    env_keys = ()
    caveat = (
        "Statistical register, not the legal one: no website/e-mail for most "
        "small entities (recorded as GE_WEB_MISSING, 0.6 confidence, never as "
        "NO_WEBSITE), and a person's data may only be used for a legitimate "
        "purpose under the Law on Personal Data Protection. Only an official "
        "NAPR extract has legal force. Cite the source."
    )

    PAGE_SIZE = 100

    def estimate(self, queries: list[DiscoveryQuery]) -> float:
        return 0.0

    async def fetch(self, client: httpx.AsyncClient, env: dict,
                    query: DiscoveryQuery) -> list[Business]:
        nace = nace_for(query.term)
        region, address_filter = region_for(query.location)
        out: list[Business] = []
        page = 1
        total_pages = 1
        while len(out) < query.limit and page <= total_pages:
            params = {
                "lang": "ge", "page": page,
                "limit": min(self.PAGE_SIZE, query.limit),
                "activityCode": nace,
                "legalAddressRegion": region,
                "isActive": "true",
            }
            resp = await client.get(f"{BASE}/documents", params=params,
                                    headers={"Accept": "application/json"},
                                    timeout=httpx.Timeout(connect=10.0, read=45.0,
                                                          write=10.0, pool=10.0))
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") or []
            pagination = payload.get("pagination") or {}
            total_pages = int(pagination.get("totalPages") or 1)
            for raw in data:
                item = {
                    "stat_id": raw.get("Stat_ID"), "id_code": raw.get("Legal_Code"),
                    "name": raw.get("Full_Name"), "legal_form": raw.get("Legal_Form"),
                    "active": raw.get("ISActive") == 1, "size": raw.get("Zoma"),
                    "activity": f"{raw.get('Activity_2_Code') or ''} "
                                f"{raw.get('Activity_2_Name') or ''}".strip(),
                    "legal_address": raw.get("Address"),
                    "legal_region": raw.get("Region_name"),
                    "actual_address": raw.get("Address2"),
                    "head": raw.get("Head"),
                    "email": raw.get("Email"), "phone": raw.get("mob"),
                    "web": raw.get("web"),
                    "registered": str(raw.get("Init_Reg_date") or "")[:10],
                    "last_change": str(raw.get("Reg_Date") or "")[:10],
                }
                address = (item.get("legal_address") or "") + " " + \
                          (item.get("actual_address") or "")
                if address_filter and address_filter not in address:
                    continue        # the region matched, the city did not
                out.append(to_business(item, query=query))
                if len(out) >= query.limit:
                    break
            if not data:
                break
            page += 1
            if page <= total_pages:
                import asyncio
                await asyncio.sleep(MIN_INTERVAL)   # register etiquette
        return out
