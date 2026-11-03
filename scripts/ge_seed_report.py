"""How much do the seed layers actually add? Join them on the identification code."""

import collections
import sqlite3

db = sqlite3.connect("data/harvey.db")
db.row_factory = sqlite3.Row

rows = [dict(r) for r in db.execute(
    "SELECT company_id, signal_code, value_text FROM observations "
    "WHERE signal_code IN ('GE_ID_CODE','GE_PHONE','GE_EMAIL')")]
by_company = collections.defaultdict(dict)
for r in rows:
    by_company[r["company_id"]][r["signal_code"]] = r["value_text"] or ""

companies = {c["id"]: dict(c) for c in db.execute("SELECT * FROM companies")}
id_codes = collections.defaultdict(list)
for cid, sig in by_company.items():
    code = sig.get("GE_ID_CODE", "").strip()
    if code:
        id_codes[code].append(cid)

seeded = [cid for cid, c in companies.items() if (c.get("source") or "") == "seed:compania"]
matched, unmatched = 0, 0
new_phones = 0
for cid in seeded:
    code = by_company[cid].get("GE_ID_CODE", "")
    others = [o for o in id_codes.get(code, []) if o != cid]
    if others:
        matched += 1
    else:
        unmatched += 1
    if by_company[cid].get("GE_PHONE"):
        new_phones += 1

print(f"seeded companies: {len(seeded)}")
print(f"  with a phone: {new_phones}")
print(f"  joined to another row by id code: {matched}")
print(f"  seed-only (no register match): {unmatched}")

by_source = collections.Counter(c.get("source", "") for c in companies.values())
print("\nsources:", dict(by_source))

reachable = sum(1 for cid, c in companies.items()
                if (c.get("phone") or "").strip() or by_company[cid].get("GE_PHONE"))
print(f"companies with a phone anywhere: {reachable}")
with_email = sum(1 for cid, c in companies.items() if by_company[cid].get("GE_EMAIL"))
print(f"companies with a registry e-mail: {with_email}")
