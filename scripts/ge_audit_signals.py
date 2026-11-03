import sqlite3

db = sqlite3.connect('data/harvey.db')
db.row_factory = sqlite3.Row
rows = [dict(r) for r in db.execute("""
SELECT c.name, c.domain, o.signal_code, o.value_num, o.value_text, o.confidence, o.evidence_url
FROM observations o JOIN companies c ON c.id = o.company_id
WHERE o.signal_code IN ('ACCELERATOR','FUNDING_ROUND','BLOCKS_AI_CRAWLERS','NO_ONLINE_BOOKING','NO_SCHEMA_MARKUP','SITE_PAGE_COUNT','BLOG_STALE')
ORDER BY o.signal_code, c.domain LIMIT 40
""")]
for r in rows:
    print(f"{r['signal_code']:20s} {str(r['domain'])[:28]:28s} num={r['value_num']} text={(r['value_text'] or '')[:40]!r} conf={r['confidence']}")
