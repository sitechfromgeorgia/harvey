"""Georgia via OpenStreetMap — the half of the market that already has a site.

The register knows every legal entity and almost never knows a website. OSM is
the mirror image: fewer businesses, but many of them publish a website tag. Put
both in one database and the picture completes — companies with no site at all
(offer: a site) and companies with a site that is invisible or does not take a
booking (offer: SEO, booking, chatbot, design). SiTech sells both, so a lead
engine that only hunts site-less businesses is leaving half the market out.

Harvey's own OSM provider maps US trade names to Overpass categories and cannot
answer "სასტუმრო ბათუმი" at all. This one maps Georgian industry words to OSM
tags and searches a city bounding box, which is the only shape Overpass answers
quickly from a datacenter IP.

Two honesty rules, both learned the hard way:

* A Facebook page is not a website. Many Batumi businesses list
  ``facebook.com/theirpage`` in the website field; that is a social-only
  presence, recorded as `GE_SOCIAL_ONLY`, not as a site to audit.
* A missing ``website`` tag is not proof of no website (the community simply
  never filled it in), so it is `GE_WEB_MISSING` at 0.6 — never `NO_WEBSITE`.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from harvey.collectors.discover import Business, DiscoveryProvider, DiscoveryQuery, \
    normalize_domain

# Batumi's main endpoint 502s from this network; the community mirror answered
# in under two seconds with a full extract. Order matters: try the official one,
# fall back.
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
SOURCE_URL = "https://www.openstreetmap.org/"
CITE = "წყარო: OpenStreetMap (ODbL)"
MIN_INTERVAL = 2.0
HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

# (south, west, north, east) — the city proper, not the municipality.
CITY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "ბათუმი": (41.60, 41.58, 41.70, 41.70),
    "batumi": (41.60, 41.58, 41.70, 41.70),
    "ქობულეთი": (41.78, 41.72, 41.86, 41.84),
    "kobuleti": (41.78, 41.72, 41.86, 41.84),
    "თბილისი": (41.66, 44.72, 41.84, 44.90),
    "tbilisi": (41.66, 44.72, 41.84, 44.90),
    "ქუთაისი": (42.20, 42.63, 42.32, 42.78),
    "kutaisi": (42.20, 42.63, 42.32, 42.78),
}

# Industry word → Overpass tag filter. Only tags that exist in Georgian data;
# a word with no mapping raises, because a silent empty Overpass answer reads
# exactly like a market with nobody in it.
OSM_TAGS: dict[str, str] = {
    "სასტუმრო": '["tourism"~"^(hotel|guest_house|apartment|hostel|motel)$"]',
    "hotel": '["tourism"~"^(hotel|guest_house|apartment|hostel|motel)$"]',
    "რესტორანი": '["amenity"~"^(restaurant|fast_food)$"]',
    "restaurant": '["amenity"~"^(restaurant|fast_food)$"]',
    "კაფე": '["amenity"~"^(cafe|bar|pub)$"]',
    "cafe": '["amenity"~"^(cafe|bar|pub)$"]',
    "სილამაზის სალონი": '["shop"~"^(beauty|hairdresser)$"]',
    "beauty salon": '["shop"~"^(beauty|hairdresser)$"]',
    "სტომატოლოგია": '["amenity"="dentist"]',
    "dentist": '["amenity"="dentist"]',
    "კლინიკა": '["amenity"~"^(clinic|doctors|hospital)$"]',
    "clinic": '["amenity"~"^(clinic|doctors|hospital)$"]',
    "აფთიაქი": '["amenity"="pharmacy"]',
    "pharmacy": '["amenity"="pharmacy"]',
    "სუპერმარკეტი": '["shop"~"^(supermarket|convenience|greengrocer|butcher|bakery)$"]',
    "supermarket": '["shop"~"^(supermarket|convenience|greengrocer|butcher|bakery)$"]',
    "მაღაზია": '["shop"~"^(clothes|shoes|fashion|jewelry|electronics|furniture)$"]',
    "shop": '["shop"~"^(clothes|shoes|fashion|jewelry|electronics|furniture)$"]',
    "უძრავი ქონება": '["office"="estate_agent"]',
    "real estate": '["office"="estate_agent"]',
    "მშენებლობა": '["office"~"^(construction_company|company)$"]["craft"!~"."]',
    "ავტომობილების ქირაობა": '["amenity"="car_rental"]',
    "car rental": '["amenity"="car_rental"]',
    "ტურისტული სააგენტო": '["office"~"^(travel_agent|travel_agency)$"]',
    "travel agency": '["office"~"^(travel_agent|travel_agency)$"]',
    "სპორტული დარბაზი": '["leisure"="fitness_centre"]',
    "fitness": '["leisure"="fitness_centre"]',
    "განათლება": '["amenity"~"^(language_school|driving_school|training)$"]',
    "education": '["amenity"~"^(language_school|driving_school|training)$"]',
    "სასწავლო ცენტრი": '["amenity"~"^(language_school|driving_school|training)$"]',
    "IT": '["office"="it"]',
    # Remaining NACE aliases the register recognises. A sector with no sensible
    # OSM tag would be a silent hole, so each maps to the closest real tag.
    "guesthouse": '["tourism"="guest_house"]',
    "გესთჰაუსი": '["tourism"="guest_house"]',
    "საოჯახო სასტუმრო": '["tourism"="guest_house"]',
    "bar": '["amenity"~"^(cafe|bar|pub)$"]',
    "ბარი": '["amenity"~"^(cafe|bar|pub)$"]',
    "retail": '["shop"~"^(clothes|shoes|fashion|electronics|furniture)$"]',
    "construction": '["office"~"^(construction_company|company)$"]',
    "barbershop": '["shop"="hairdresser"]',
    "gym": '["leisure"="fitness_centre"]',
    "სარემონტო": '["craft"~"^(builder|painter|carpenter|plumber|electrician)$"]',
    "law firm": '["office"="lawyer"]',
    "legal": '["office"="lawyer"]',
    "იურიდიული": '["office"="lawyer"]',
    "accounting": '["office"="accountant"]',
    "ბუღალტრული": '["office"="accountant"]',
    "სამედიცინო": '["amenity"~"^(clinic|doctors)$"]',
    "ავტო": '["shop"~"^(car|car_repair|car_parts)$"]',
    "car dealer": '["shop"="car"]',
    "ტრანსპორტი": '["office"~"^(logistics|moving_company)$"]',
    "transport": '["office"~"^(logistics|moving_company)$"]',
    "logistics": '["office"="logistics"]',
    "პროგრამირება": '["office"="it"]',
    "software": '["office"="it"]',
    "მარკეტინგი": '["office"="advertising_agency"]',
    "marketing": '["office"="advertising_agency"]',
    "რეკლამა": '["office"="advertising_agency"]',
}

SOCIAL_HOSTS = ("facebook.com", "fb.com", "instagram.com", "tiktok.com",
                "t.me", "wa.me", "linktr.ee")


def bbox_for(city: str) -> tuple[float, float, float, float]:
    key = (city or "").strip().lower()
    if key in CITY_BBOX:
        return CITY_BBOX[key]
    for name, box in CITY_BBOX.items():
        if name and name in key:
            return box
    raise ValueError(
        f"no bounding box for '{city}' — add it to georgia_osm.CITY_BBOX "
        f"(south, west, north, east)")


def tag_filter(term: str) -> str:
    key = (term or "").strip()
    for candidate in (key, key.lower(),
                      # Georgian plurals and English plurals: an ICP is written
                      # "სასტუმრო", a person may write "სასტუმროები".
                      re.sub(r"(ები|ებ)$", "", key),
                      re.sub(r"ies$", "y", key.lower()),
                      key.lower().rstrip("s")):
        if candidate in OSM_TAGS:
            return OSM_TAGS[candidate]
    raise ValueError(
        f"no Overpass tag filter for '{term}' — add it to georgia_osm.OSM_TAGS")


def _web(tags: dict) -> str:
    return (tags.get("website") or tags.get("contact:website")
            or tags.get("url") or "").strip()


def _domain_or_social(web: str) -> tuple[str, str]:
    """(domain, social_host). A social page is not a site: domain stays empty."""
    if not web:
        return "", ""
    host = urlparse(web if "//" in web else f"//{web}", scheme="https").hostname or ""
    host = host.lower().lstrip("www.")
    if not host:
        return "", ""
    if any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS):
        return "", host
    return normalize_domain(host), ""


def to_business(el: dict, *, query: DiscoveryQuery) -> Business | None:
    tags = el.get("tags") or {}
    name = (tags.get("name:ka") or tags.get("name") or tags.get("name:en")
            or tags.get("name:ru") or "").strip()
    if not name:
        return None            # an unnamed point is not a prospect
    web = _web(tags)
    domain, social = _domain_or_social(web)
    street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    phone = (tags.get("phone") or tags.get("contact:phone") or "").strip()

    extra: dict[str, tuple] = {}
    if social:
        extra["GE_SOCIAL_ONLY"] = (1.0, social, 1.0)
    if not domain:
        extra["GE_WEB_MISSING"] = (
            1.0, "no website in the OSM listing" if not social else "social page only", 0.6)

    return Business(
        name=name,
        domain=domain,
        website=f"https://{domain}" if domain else "",
        phone=phone,
        address=street,
        location=query.location,
        category=query.term,
        has_website=True if domain else None,   # None: silence is not proof
        external_id=f"osm:{el.get('type', 'node')}/{el.get('id')}",
        source_url=f"{SOURCE_URL}{el.get('type', 'node')}/{el.get('id')}",
        provider="georgia_osm",
        extra_signals=extra,
    )


class GeorgiaOSM(DiscoveryProvider):
    """Overpass, searched by Georgian industry tag inside a city bounding box."""

    key = "georgia_osm"
    label = "Georgia — OpenStreetMap (city bbox)"
    kind = "listings"
    needs_coordinates = False
    blurb = (
        "OpenStreetMap-ის ობიექტები ქალაქის საზღვრებში — ბევრს აქვს საიტი, "
        "ტელეფონი და მისამართი. უფასო, გასაღების გარეშე. ავსებს რეესტრს: "
        "რეესტრმა იცის ვინ არსებობს, OSM-მა — ვის აქვს საიტი."
    )
    cost_note = "free (Overpass, one request per query)"
    free_tier = "unlimited within community etiquette (1 request / 2s)"
    signup_url = "https://www.openstreetmap.org"
    env_keys = ()
    caveat = (
        "Coverage depends on what mappers filled in: a missing website tag is "
        "not proof of no site (GE_WEB_MISSING, 0.6), and a Facebook page is "
        "not a website (GE_SOCIAL_ONLY). Data © OpenStreetMap contributors, ODbL."
    )

    def estimate(self, queries: list[DiscoveryQuery]) -> float:
        return 0.0

    async def fetch(self, client: httpx.AsyncClient, env: dict,
                    query: DiscoveryQuery) -> list[Business]:
        south, west, north, east = bbox_for(query.location)
        ql = (
            "[out:json][timeout:60];\n"
            "(\n"
            f"  nwr{tag_filter(query.term)}({south},{west},{north},{east});\n"
            ");\n"
            f"out tags center {max(1, int(query.limit))};"
        )
        payload = None
        last_error = ""
        for endpoint in ENDPOINTS:
            try:
                resp = await client.post(
                    endpoint, content=ql.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8",
                             "User-Agent": "harvey-ge/0.1 (sales research; hello@sitech.ge)"},
                    timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    payload = resp.json()
                    break
                last_error = f"{endpoint}: HTTP {resp.status_code}"
            except Exception as exc:                 # noqa: BLE001 — try the mirror
                last_error = f"{endpoint}: {type(exc).__name__}"
                continue
        if payload is None:
            raise RuntimeError(f"Overpass unavailable: {last_error}")

        out: list[Business] = []
        for el in payload.get("elements") or []:
            biz = to_business(el, query=query)
            if biz is not None:
                out.append(biz)
                if len(out) >= query.limit:
                    break
        return out
