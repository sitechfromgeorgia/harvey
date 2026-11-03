"""Merge the same legal entity recorded by two sources — joined on the id code.

A register row and a seeded directory row are the same company when their
`GE_ID_CODE` agrees. Keeping both means two e-mails to one business and a
pipeline that looks bigger than the market.

What a merge does, in this order:

1. The **register row survives** (it holds the legal form, the size band, the
   registration date, the director). A seeded row survives only when there is no
   register row.
2. Missing contact fields move to the survivor: phone, website, description.
3. Observations follow their company to the survivor, except a duplicate of a
   signal the survivor already has (the survivor's value wins).
4. The absorbed row is deleted, and the merge is logged.

Dry run by default. `--apply` writes, and prints every merge so a wrong join is
visible immediately.

    python scripts/ge_merge.py            # show what would merge
    python scripts/ge_merge.py --apply
"""

from __future__ import annotations

import argparse
import collections
import sqlite3
import sys

PREFERRED = ("discover:georgia_registry", "seed:compania", "discover:georgia_osm")


def rank(company: dict) -> int:
    source = company.get("source") or ""
    return PREFERRED.index(source) if source in PREFERRED else len(PREFERRED)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/harvey.db")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    q = lambda s, *a: [dict(r) for r in db.execute(s, a)]

    companies = {c["id"]: c for c in q("SELECT * FROM companies")}
    codes: dict[str, list[str]] = collections.defaultdict(list)
    for r in q("SELECT company_id, value_text FROM observations WHERE signal_code = 'GE_ID_CODE'"):
        code = (r["value_text"] or "").strip()
        if code:
            codes[code].append(r["company_id"])

    obs_by_company = collections.defaultdict(list)
    for o in q("SELECT * FROM observations"):
        obs_by_company[o["company_id"]].append(o)

    merges = 0
    absorbed_total = 0
    for code, ids in codes.items():
        ids = [i for i in dict.fromkeys(ids) if i in companies]
        if len(ids) < 2:
            continue
        ids.sort(key=lambda i: rank(companies[i]))
        survivor, absorbed = ids[0], ids[1:]
        merges += 1
        for other in absorbed:
            a, s = companies[other], companies[survivor]
            print(f"  {code}: keep {s['name'][:28]:28s} ({s.get('source')}) "
                  f"← drop {a['name'][:28]:28s} ({a.get('source')})")
            absorbed_total += 1
            if not args.apply:
                continue
            # Contact fields the survivor lacks.
            for field in ("phone", "website", "domain", "description"):
                if not (s.get(field) or "").strip() and (a.get(field) or "").strip():
                    db.execute(f"UPDATE companies SET {field} = ? WHERE id = ?",
                               (a[field], survivor))
                    s[field] = a[field]
            have = {o["signal_code"] for o in obs_by_company[survivor]}
            for o in obs_by_company[other]:
                if o["signal_code"] in have:
                    continue
                db.execute("UPDATE observations SET company_id = ? WHERE id = ?",
                           (survivor, o["id"]))
                have.add(o["signal_code"])
            db.execute("DELETE FROM companies WHERE id = ?", (other,))
            companies.pop(other, None)

    if merges == 0:
        print("nothing to merge: every id code belongs to one row")
        return 0
    if args.apply:
        db.commit()
        print(f"\nmerged {merges} groups · absorbed {absorbed_total} rows · written")
    else:
        print(f"\n{merges} groups, {absorbed_total} rows would be absorbed "
              f"(dry run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
