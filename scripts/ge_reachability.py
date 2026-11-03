"""One number that matters: how many companies can we actually reach."""

import collections
import sqlite3

db = sqlite3.connect("data/harvey.db")
db.row_factory = sqlite3.Row
q = lambda s: [dict(r) for r in db.execute(s)]

companies = {c["id"]: dict(c) for c in q("SELECT * FROM companies")}
phones: dict[str, str] = {}
emails: dict[str, str] = {}
for o in q("SELECT company_id, signal_code, value_text FROM observations "
           "WHERE signal_code IN ('GE_PHONE','GE_EMAIL')"):
    target = phones if o["signal_code"] == "GE_PHONE" else emails
    if (o["value_text"] or "").strip():
        target.setdefault(o["company_id"], o["value_text"])

for cid, c in companies.items():
    if (c.get("phone") or "").strip():
        phones.setdefault(cid, c["phone"])

reachable = {cid for cid in companies if cid in phones or cid in emails}
print(f"companies: {len(companies)}")
print(f"  with a phone: {len(phones)}")
print(f"  with an e-mail: {len(emails)}")
print(f"  reachable at all: {len(reachable)} ({len(reachable) * 100 // max(1, len(companies))}%)")

by_source = collections.Counter(c.get("source", "") for c in companies.values())
for source, count in by_source.most_common():
    src_ids = [cid for cid, c in companies.items() if c.get("source") == source]
    src_reach = sum(1 for cid in src_ids if cid in reachable)
    print(f"  {source:28s} {count:5d} companies · {src_reach:5d} reachable")
