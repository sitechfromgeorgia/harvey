"""Which of SiTech's services this company actually needs — and the reason.

The ICP fit in `fit.py` answers "is this a company worth talking to". This
answers the question the first email depends on: **what do we offer them, and
why that one**. A company with no site and a company with a WordPress site that
ranks #22 need different emails, different prices and different proof — and
they are both good prospects, which is the whole point: SiTech sells eight
services, not one.

Deterministic on purpose. Every rule below reads an observation Harvey already
paid for (mostly free), and names it in the evidence, so the claim in the email
is one a human can check. The model's job is to write the sentence, not to
decide the offer.

Scores are 0-100 and readable: 80+ means the evidence is strong and specific,
50-79 means one signal points that way, below 50 is a guess and is not shown.
Nothing here is stored — the fit follows the observations the moment they land.
"""

from __future__ import annotations

# price_band: what we quote. Bands, never a single number: the exact price is a
# proposal, and a band keeps the first email from becoming a price list.
SERVICES: list[dict] = [
    {
        "key": "landing",
        "label": "ლენდინგი (one-page)",
        "price": "300–500 ₾",
        "why": "ერთი გვერდი, ერთი მიზანი — სწრაფი სტარტი ან რეკლამის დანამატი.",
    },
    {
        "key": "business_site",
        "label": "ბიზნეს საიტი",
        "price": "500–1,500 ₾",
        "why": "3–5 გვერდი, სერვისების კატალოგი, ბლოგი, SEO, Google Maps.",
    },
    {
        "key": "seo",
        "label": "SEO ოპტიმიზაცია",
        "price": "თვიური, შეთავაზებით",
        "why": "ხილვადობა Google-ში: საკვანძო სიტყვები, ტექნიკური SEO, ანგარიში.",
    },
    {
        "key": "complex_webapp",
        "label": "კომპლექსური საიტი/აპი",
        "price": "1,000–3,000 ₾",
        "why": "Dashboard, მომხმარებლების მართვა, API ინტეგრაციები, ჯავშანი.",
    },
    {
        "key": "payments",
        "label": "გადახდის ინტეგრაცია",
        "price": "300–800 ₾ დანამატი",
        "why": "E-commerce და საბანკო სისტემების შეერთება.",
    },
    {
        "key": "saas_mvp",
        "label": "SaaS MVP",
        "price": "2,000–5,000 ₾",
        "why": "პროდუქტის MVP თვეებში, არა წლებში.",
    },
    {
        "key": "uiux",
        "label": "UI/UX დიზაინი",
        "price": "400–1,200 ₾",
        "why": "ინტერფეისი, რომელიც ხალხს არ აბრკოლებს.",
    },
    {
        "key": "ai_chatbot",
        "label": "AI ჩატბოტი",
        "price": "500–2,000 ₾",
        "why": "კითხვებზე პასუხი 24/7, ღამის მოთხოვნების დაჭერა.",
    },
    {
        "key": "cli_tools",
        "label": "CLI/ავტომატიზაცია",
        "price": "შეთავაზებით",
        "why": "გამეორებადი საქმის სკრიპტად გადაქცევა.",
    },
]

SERVICE_BY_KEY = {s["key"]: s for s in SERVICES}

# BLOG_STALE is the age of the newest content in days, not a boolean: 6 days is
# a healthy blog, 982 days is an abandoned one. Six months is the line.
BLOG_STALE_DAYS = 180


# Observation codes this module reads. The register's own query has to fetch
# them, or the fit is computed against a truncated set and every company looks
# like it has no evidence (this was a real bug: 17 site-bearing companies came
# out empty because the query only pulled the ICP-fit codes).
SERVICE_SIGNALS = (
    "SERP_RANK", "IN_LOCAL_PACK", "MAPS_RANK", "NO_WEBSITE",
    "GE_WEB_MISSING", "GE_SOCIAL_ONLY", "GE_SIZE", "GE_ACTIVITY",
    "GE_NEW_REGISTRATION", "SITE_PAGE_COUNT", "BLOG_STALE",
    "NO_SCHEMA_MARKUP", "NO_ONLINE_BOOKING", "RUNNING_GOOGLE_ADS",
    "RUNNING_META_ADS", "BLOCKS_AI_CRAWLERS", "TECH_STACK",
)


def _obs_map(observations: list[dict]) -> dict[str, dict]:
    """Latest observation per signal code (observations arrive newest-last)."""
    out: dict[str, dict] = {}
    for o in sorted(observations or [], key=lambda o: o.get("observed_at") or ""):
        code = o.get("signal_code")
        if code:
            out[code] = o
    return out


def _text(obs: dict, code: str) -> str:
    o = obs.get(code)
    return (o.get("value_text") or "").strip() if o else ""


def _num(obs: dict, code: str) -> float | None:
    o = obs.get(code)
    if not o:
        return None
    try:
        return float(o.get("value_num"))
    except (TypeError, ValueError):
        return None


def _has_site(company: dict, obs: dict) -> bool:
    """A site we have seen, not one we assumed: a domain from a provider that
    gave one, or a profile that read HTML."""
    if (company.get("website") or "").strip() or (company.get("domain") or "").strip():
        return True
    pages = _num(obs, "SITE_PAGE_COUNT")
    return bool(pages and pages > 0)


def _activity(company: dict, obs: dict) -> str:
    return (_text(obs, "GE_ACTIVITY") or company.get("industry") or "").lower()


# Which activities can take a booking/ordering flow, by NACE prefix.
BOOKING_ACTIVITIES = ("55.10", "55.20", "56.10", "56.30", "86.21", "86.23",
                      "96.02", "93.13", "77.11")
ECOMMERCE_ACTIVITIES = ("47.11", "47.19", "47.73", "45.11")
PRODUCT_ACTIVITIES = ("62.01", "73.11")


def service_fits(company: dict, observations: list[dict]) -> list[dict]:
    """Every service the evidence supports, strongest first.

    Each entry: {key, label, price, why, score, evidence[], pitch}. ``pitch`` is
    the one line the writer may use — it states only what was observed.
    """
    obs = _obs_map(observations)
    site = _has_site(company, obs)
    activity = _activity(company, obs)
    new_registration = _num(obs, "GE_NEW_REGISTRATION") == 1.0
    web_missing = bool(obs.get("GE_WEB_MISSING"))
    social_only = bool(obs.get("GE_SOCIAL_ONLY"))
    rank = _num(obs, "SERP_RANK")
    pages = _num(obs, "SITE_PAGE_COUNT")
    blog_age = _num(obs, "BLOG_STALE")       # days since the newest content
    blog_stale = blog_age is not None and blog_age >= BLOG_STALE_DAYS
    no_schema = _num(obs, "NO_SCHEMA_MARKUP") == 1.0
    running_ads = (_num(obs, "RUNNING_GOOGLE_ADS") == 1.0 or _num(obs, "RUNNING_META_ADS") == 1.0)
    no_booking = _num(obs, "NO_ONLINE_BOOKING") == 1.0
    blocks_ai = _num(obs, "BLOCKS_AI_CRAWLERS") == 1.0
    size = (_text(obs, "GE_SIZE") or "").lower()

    out: list[dict] = []

    def add(key: str, score: int, evidence: list[str], pitch: str) -> None:
        s = SERVICE_BY_KEY[key]
        out.append({"key": key, "label": s["label"], "price": s["price"],
                    "why": s["why"], "score": min(score, 100),
                    "evidence": evidence, "pitch": pitch})

    # ── No site at all: the site is the offer, and the trigger decides which ──
    if not site:
        if social_only:
            add("business_site", 92, ["GE_SOCIAL_ONLY"],
                "Facebook გვერდი გაქვთ, საიტი არა — ჯავშანი, ფასები და მისამართი "
                "ერთ ადგილას რომ იყოს, სჭირდება.")
        elif new_registration:
            add("landing", 95,
                ["GE_NEW_REGISTRATION", "GE_WEB_MISSING"],
                "ახლად დარეგისტრირებული ბიზნესი ხართ და საიტი ჯერ არ არის — "
                "ერთი გვერდი საკმარისია პირველი კლიენტებისთვის.")
        elif running_ads:
            add("landing", 92,
                ["RUNNING_GOOGLE_ADS", "GE_WEB_MISSING"],
                "რეკლამას ხართ, მაგრამ ბმული საიტზე არ მიდის — ბიუჯეტი იკარგება.")
        else:
            add("business_site", 88 if size in {"მცირე", "small"} else 80,
                ["GE_WEB_MISSING"] + (["GE_SIZE"] if size else []),
                "თქვენი ბიზნესი რეესტრშია, საიტი კი ვერ ვიპოვე — სად გიჩნდებათ "
                "ონლაინ მოთხოვნა?")
        if web_missing:
            add("landing", 70, ["GE_WEB_MISSING"],
                "ერთი გვერდი, ერთი მიზანი: დარეკვის ნაცვლად ფორმა.")

    # ── Has a site: SEO, structure, design, booking, payments ──────────────
    if site:
        if rank is not None and 10 < rank <= 30:
            add("seo", 90, [f"SERP_RANK={int(rank)}"],
                f"«{_text(obs, 'SERP_RANK') or 'თქვენს ძირითად შეკითხვაზე'}» პირველ "
                f"გვერდზე არ ხართ (#{int(rank)}) — ეს გამოსწორებადია.")
        if blog_stale:
            add("seo", 82, ["BLOG_STALE"],
                "ბლოგი შეჩერდა — კონტენტი, რომელიც უკვე გაქვთ, ვერ მუშაობს.")
        if no_schema:
            add("seo", 75, ["NO_SCHEMA_MARKUP"],
                "საიტს სტრუქტურირებული მონაცემები აკლია — Google-ს ვერ ეუბნებით, "
                "რა გაქვთ.")
        if pages is not None and 0 < pages <= 3:
            add("business_site", 85, [f"SITE_PAGE_COUNT={int(pages)}"],
                "საიტი 3 გვერდამდეა — სერვისების გვერდი და ბლოგი აკლია.")
        if no_booking and any(activity.startswith(p) for p in BOOKING_ACTIVITIES):
            add("complex_webapp", 88, ["NO_ONLINE_BOOKING", "GE_ACTIVITY"],
                "ჯავშანი ტელეფონით ხდება — ღამის მოთხოვნა იკარგება.")
        if any(activity.startswith(p) for p in ECOMMERCE_ACTIVITIES):
            add("payments", 72, ["GE_ACTIVITY"],
                "ონლაინ გაყიდვა ბარათით — გადახდის ინტეგრაცია აკლია.")
        if size in {"საშუალო", "მსხვილი", "medium", "large"}:
            add("uiux", 62, ["GE_SIZE"],
                "გუნდი გაზრდილია — ინტერფეისი ხშირად რჩება ერთი ადამიანის "
                "ლოგიკაზე.")

    # ── Activity-based, works with or without a site ───────────────────────
    if any(activity.startswith(p) for p in PRODUCT_ACTIVITIES):
        add("saas_mvp", 78 if site else 70, ["GE_ACTIVITY"],
            "პროგრამულ პროდუქტს აკეთებთ — MVP-ის ვადა თვეებში იზომება, არა წლებში.")
    if blocks_ai:
        add("ai_chatbot", 74, ["BLOCKS_AI_CRAWLERS"],
            "საიტი AI-კრავლერებს ბლოკავს — AI ჩეთში თქვენზე პასუხი არ არსებობს.")
    if any(activity.startswith(p) for p in BOOKING_ACTIVITIES):
        add("ai_chatbot", 68 if not site else 60, ["GE_ACTIVITY"],
            "სტუმრის კითხვები დღის განმავლობაში მეორდება — ჩატბოტი 24/7 პასუხობს.")

    out.sort(key=lambda f: (-f["score"], f["key"]))
    return out


def primary_service(company: dict, observations: list[dict]) -> dict | None:
    """The one service the first email is about, or None when nothing fits."""
    fits = [f for f in service_fits(company, observations) if f["score"] >= 50]
    return fits[0] if fits else None


def summarise(company: dict, observations: list[dict], limit: int = 3) -> str:
    """One line for the register/CSV: the strongest fits with their prices."""
    fits = [f for f in service_fits(company, observations) if f["score"] >= 50][:limit]
    return "; ".join(f"{f['label']} ({f['price']})" for f in fits)
