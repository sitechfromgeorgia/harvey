"""Find the same business recorded twice, once per source.

The register knows "ინდივიდუალური მეწარმე ოქსანა არნაუტოვა"; OSM knows "Hotel
Oksana". Same phone, two rows. Emailing both is the most visible mistake this
pipeline can make in a small city, so duplicates are found and reported before
anything is written.

Two deterministic rules, no model:

* **phone** — the last 9 digits of any phone on either row agree. Georgian
  numbers are +995 5XX XXX XXX, so the last 9 are the subscriber number.
* **name** — the OSM name, stripped of legal prefixes and punctuation, is
  contained in the register name (or vice versa) and the city matches.

Writes data/dedupe.csv (group, rule, company_a, company_b, evidence) and prints
a summary. Nothing is merged: a human decides, because a wrong merge loses a
lead and a wrong split costs an e-mail.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

LEGAL_PREFIX = re.compile(
    r"^(შპს|სს|ი/მ|ინდივიდუალური მეწარმე|ა\(ა\)იპ|კოოპერატივი|შპს\.|ltd\.?|llc\.?)\s*",
    re.IGNORECASE)
NOISE = re.compile(r"[^\w\s]", re.UNICODE)
SPACES = re.compile(r"\s+")
HOTEL_WORDS = ("სასტუმრო", "hotel", "guest", "house", "hostel", "apart", "ოტელი")


def norm_name(name: str) -> str:
    n = NOISE.sub(" ", (name or "").lower())
    n = LEGAL_PREFIX.sub("", n).strip()
    n = SPACES.sub(" ", n)
    for w in HOTEL_WORDS:
        n = n.replace(w, " ")
    return SPACES.sub(" ", n).strip()


def phone_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 9 else ""


def load(db_path: str) -> list[dict]:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    companies = [dict(r) for r in db.execute("SELECT * FROM companies")]
    obs: dict[str, dict[str, str]] = {}
    for o in db.execute("SELECT company_id, signal_code, value_text FROM observations "
                        "WHERE signal_code IN ('GE_PHONE','GE_HEAD','GE_WEB_MISSING',"
                        "'GE_SOCIAL_ONLY','GE_ID_CODE')"):
        obs.setdefault(o["company_id"], {})[o["signal_code"]] = o["value_text"] or ""
    for c in companies:
        o = obs.get(c["id"], {})
        c["phone_all"] = " ".join(x for x in (c.get("phone") or "", o.get("GE_PHONE", "")) if x)
        c["director"] = o.get("GE_HEAD", "")
    return companies


def find(companies: list[dict]) -> list[dict]:
    groups: list[dict] = []
    by_phone: dict[str, list[dict]] = {}
    for c in companies:
        key = phone_key(c["phone_all"])
        if key:
            by_phone.setdefault(key, []).append(c)
    for key, items in by_phone.items():
        if len(items) > 1:
            groups.append({"rule": "phone", "evidence": f"+...{key}", "items": items})

    seen = {frozenset((a["id"], b["id"])) for g in groups
            for a, b in combinations(g["items"], 2)}
    named = [c for c in companies if norm_name(c.get("name") or "")]
    for a, b in combinations(named, 2):
        pair = frozenset((a["id"], b["id"]))
        if pair in seen:
            continue
        na, nb = norm_name(a["name"]), norm_name(b["name"])
        if not na or not nb:
            continue
        short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(short) >= 6 and short in long_ and (a.get("location") == b.get("location")):
            groups.append({"rule": "name", "evidence": f"{short!r} ⊂ {long_!r}",
                           "items": [a, b]})
            seen.add(pair)
    return groups


def main() -> int:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/harvey.db"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/dedupe.csv")
    companies = load(db)
    groups = find(companies)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["group", "rule", "evidence", "company_a", "source_a", "phone_a",
                    "website_a", "company_b", "source_b", "phone_b", "website_b"])
        for i, g in enumerate(groups, 1):
            for a, b in combinations(g["items"], 2):
                w.writerow([i, g["rule"], g["evidence"],
                            a.get("name"), a.get("source"), a.get("phone_all"),
                            a.get("website"),
                            b.get("name"), b.get("source"), b.get("phone_all"),
                            b.get("website")])

    by_rule: dict[str, int] = {}
    for g in groups:
        by_rule[g["rule"]] = by_rule.get(g["rule"], 0) + 1
    print(f"companies: {len(companies)} · duplicate groups: {len(groups)} {by_rule}")
    for g in groups[:8]:
        items = g["items"]
        print(f"- [{g['rule']}] {g['evidence'][:40]} → " +
              " | ".join(f"{i.get('name')[:26]} ({i.get('source', '').split(':')[-1]})"
                         for i in items))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
