"""Company fit: one 0-100 number per company, with the reasons behind it.

Worked out on read from what Harvey already holds (the company's industry,
its contacts and their email status, and its observations), weighed against
the ICP in the config. Nothing is stored, so the score follows the config
the moment it changes.

    sector match      20  the company's industry is one of icp.industries
    decision maker    30  a contact whose title matches icp.titles
                          (15 for another named person, 5 for a general inbox)
    reachable         25  best email: verified 25, risky 12, guess 5;
                          a contact form alone is 5
    buying signal     25  an open role matching icp.hiring_signals
                          (5 for a careers page with no matching role)

A company on the do-not-contact list scores 0.
"""

from __future__ import annotations

import re

from harvey.collectors.people import title_matches
from harvey.gate import do_not_contact_match

SECTOR, DECISION_MAKER, REACHABLE, BUYING = 20, 30, 25, 25
EMAIL_POINTS = {"verified": 25, "risky": 12, "guess": 5}
DEAD_STATUSES = {"lost", "opted_out"}


def _hiring_terms(icp) -> list[str]:
    return [t.strip().lower() for t in (getattr(icp, "hiring_signals", None) or []) if t.strip()]


def _nace_for(term: str) -> str:
    """NACE code an ICP word means, when Georgia's mapping knows it."""
    try:
        from harvey.collectors.georgia import nace_for
        return nace_for(term)
    except Exception:            # noqa: BLE001 — a missing mapping is not a crash
        return ""


def sector_matches(industry: str, industries: set[str]) -> bool:
    """Does this company's industry answer to one of the ICP's words?

    Three ways, cheapest first: the word appears in the industry string
    ("სასტუმრო" in "55.10.2 სასტუმროები და განთავსების…"), or the industry
    string appears in the word, or the word's NACE code is the industry's
    prefix ("სასტუმრო" → 55.10 → "55.10.2 …").
    """
    low = (industry or "").lower()
    if not low:
        return False
    code = low[:5] if low[:2].isdigit() else ""
    for term in industries:
        if not term:
            continue
        if term in low or (len(low) >= 6 and low in term):
            return True
        if code and _nace_for(term).startswith(code):
            return True
    return False


def _role_matches(text: str, terms: list[str]) -> str:
    """The first hiring term found in ``text`` as whole words, or ""."""
    low = (text or "").lower()
    for term in terms:
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", low):
            return term
    return ""


def current_roles(observations: list[dict]) -> list[dict]:
    """HIRING_ROLE rows still current: those after the latest "board lists
    nothing relevant" row (num 0, no text), which closes earlier roles."""
    roles = sorted((o for o in observations if o.get("signal_code") == "HIRING_ROLE"),
                   key=lambda o: o.get("observed_at") or "")
    closed = [i for i, o in enumerate(roles)
              if o.get("value_num") == 0 and not (o.get("value_text") or "").strip()]
    return roles[closed[-1]:] if closed else roles


def company_fit(company: dict, prospects: list[dict], observations: list[dict],
                config, dnc: list[str] | None = None) -> tuple[int, list[str]]:
    """(score, reasons) for one company. ``prospects`` and ``observations``
    are that company's rows, as dicts. ``dnc`` is the do-not-contact list
    (default: the config's)."""
    icp = config.icp
    if dnc is None:
        dnc = getattr(getattr(config, "compliance", None), "do_not_contact", None) or []
    domain = (company.get("domain") or "").lower()
    if domain and dnc and do_not_contact_match(f"x@{domain}", dnc):
        return 0, ["on the do-not-contact list"]

    score, reasons = 0, []

    industries = {i.strip().lower() for i in (icp.industries or [])}
    industry = (company.get("industry") or "").strip()
    if industry.lower() in industries:
        score += SECTOR
        reasons.append(f"sector: {industry}")
    elif sector_matches(industry, industries):
        # The register answers with a NACE string ("55.10.2 სასტუმროები…"),
        # the ICP is written in words ("სასტუმრო"). Without this every Georgian
        # lead scored zero on sector and the ranking was decided by phone number
        # luck alone.
        score += SECTOR
        reasons.append(f"sector: {industry[:48]}")

    # Someone who opted out or is on the list won't be written to: they
    # don't make the company reachable.
    live = [p for p in prospects if (p.get("status") or "") not in DEAD_STATUSES
            and not (dnc and p.get("email") and do_not_contact_match(p["email"], dnc))]
    named = [p for p in live if (p.get("first_name") or "").strip()]
    makers = [p for p in named if icp.titles and title_matches(p.get("title") or "", icp.titles)]
    if not makers:
        # Names the site lists that Harvey didn't turn into contacts.
        for o in observations:
            if o.get("signal_code") == "DECISION_MAKER_TITLE":
                title = (o.get("value_text") or "").split("—", 1)[-1].strip(" ~()")
                if icp.titles and title_matches(title, icp.titles):
                    makers.append({"title": title, "first_name": ""})
                    break
    if makers:
        score += DECISION_MAKER
        reasons.append(f"decision maker: {makers[0].get('title')}")
    elif named:
        score += DECISION_MAKER // 2
        reasons.append("named contact (not a target title)")
    elif live:
        score += 5
        reasons.append("general inbox only")

    best = max((EMAIL_POINTS.get((p.get("email_status") or "").lower(), 0) for p in live), default=0)
    if best:
        score += best
        label = {25: "verified email", 12: "risky email", 5: "guessed email"}[best]
        reasons.append(label)
    elif any(o.get("signal_code") == "CONTACT_FORM_URL" for o in observations):
        score += 5
        reasons.append("contact form only")
    else:
        reasons.append("no way to reach yet")

    terms = _hiring_terms(icp)
    roles = current_roles(observations)
    hit = next((t for o in roles if (t := _role_matches(o.get("value_text"), terms))), "")
    if hit:
        score += BUYING
        reasons.append(f"hiring: {hit}")
    elif roles:
        score += 5
        reasons.append("careers page, no matching role")

    return min(score, 100), reasons

