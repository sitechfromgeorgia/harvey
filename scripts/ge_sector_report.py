"""Per-sector picture of the pipeline: volume, reachability, and the offer mix.

Answers the question a sales lead actually asks — "where do I spend the next
two hours?" — from the database rather than from instinct.

    python scripts/ge_sector_report.py
"""

from __future__ import annotations

import collections
import sqlite3
import sys

from harvey.services import primary_service


def main(db_path: str = "data/harvey.db") -> int:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    companies = [dict(r) for r in db.execute("SELECT * FROM companies")]
    obs: dict[str, dict[str, dict]] = {}
    for o in db.execute("SELECT company_id, signal_code, value_text, value_num, observed_at "
                        "FROM observations"):
        obs.setdefault(o["company_id"], {})[o["signal_code"]] = dict(o)

    rows = []
    for c in companies:
        o = obs.get(c["id"], {})
        activity = (o.get("GE_ACTIVITY", {}).get("value_text") or c.get("industry") or "")
        sector = activity.split(".")[0] if activity[:2].isdigit() else "?"
        primary = primary_service(c, list(o.values()))
        rows.append({
            "id": c["id"], "sector": sector, "activity": activity,
            "has_site": bool((c.get("domain") or "").strip()),
            "phone": bool((o.get("GE_PHONE", {}).get("value_text") or c.get("phone") or "").strip()),
            "email": bool((o.get("GE_EMAIL", {}).get("value_text") or "").strip()),
            "service": primary["key"] if primary else "",
            "fit": 0,
            "source": (c.get("source") or "").split(":")[-1],
            "city": c.get("location") or "",
        })

    by_sector = collections.defaultdict(list)
    for r in rows:
        by_sector[r["activity"] or "unknown"].append(r)

    print(f"total companies: {len(rows)}")
    print(f"{'sector':52s} {'n':>5s} {'site':>5s} {'phone':>6s} {'email':>6s}  services")
    ordered = sorted(by_sector.items(), key=lambda kv: len(kv[1]), reverse=True)
    for activity, items in ordered[:20]:
        n = len(items)
        site = sum(1 for i in items if i["has_site"])
        phone = sum(1 for i in items if i["phone"])
        email = sum(1 for i in items if i["email"])
        svc = collections.Counter(i["service"] or "none" for i in items).most_common(2)
        label = (activity or "unknown")[:50]
        print(f"{label:52s} {n:5d} {site:5d} {phone:6d} {email:6d}  "
              + ", ".join(f"{k}:{v}" for k, v in svc))

    print("\nreachability (all):")
    print(f"  with a site:   {sum(1 for r in rows if r['has_site'])}")
    print(f"  with a phone:  {sum(1 for r in rows if r['phone'])}")
    print(f"  with an email: {sum(1 for r in rows if r['email'])}")
    print(f"  contactable at all: {sum(1 for r in rows if r['phone'] or r['email'])}")
    print("\nprimary service mix:")
    for k, v in collections.Counter(r["service"] or "none" for r in rows).most_common():
        print(f"  {k or 'none':16s} {v}")
    print("\nsource mix:", dict(collections.Counter(r["source"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:2] or [])))
