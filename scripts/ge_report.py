import collections
import sqlite3

from harvey.services import primary_service, service_fits

db = sqlite3.connect('data/harvey.db')
db.row_factory = sqlite3.Row
q = lambda s: [dict(r) for r in db.execute(s)]

print("companies:", q("SELECT COUNT(*) n FROM companies")[0]['n'])
print("by source:", q("SELECT source, COUNT(*) n FROM companies GROUP BY source ORDER BY n DESC"))
print("signals:", q("SELECT signal_code, COUNT(*) n FROM observations GROUP BY signal_code ORDER BY n DESC LIMIT 14"))

companies = q("SELECT * FROM companies")
obs = collections.defaultdict(list)
for o in q("SELECT company_id, signal_code, value_num, value_text, confidence, observed_at FROM observations"):
    obs[o['company_id']].append(o)

dist = collections.Counter()
for c in companies:
    p = primary_service(c, obs[c['id']])
    dist[p['key'] if p else 'none'] += 1
print("primary service distribution:")
for k, v in dist.most_common():
    print(f"  {k:16s} {v}")

print("\nwith-site companies and their offer:")
for c in companies:
    if (c.get('domain') or '').strip():
        f = service_fits(c, obs[c['id']])
        top = f[0] if f else None
        print(f"- {c['name'][:38]:38s} {c['domain'][:32]:32s} → "
              f"{top['label'] if top else 'no evidence'} ({top['price'] if top else '-'})")
