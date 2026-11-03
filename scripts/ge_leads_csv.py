"""Write the company register to CSV — the sales list, with its service.

`harvey export` writes *prospects* (people with verified addresses). This
writes *companies*: who they are, which service the evidence supports, the price
band, the phone, and the registry e-mail when one exists. That is the list a
human works by phone or WhatsApp, which is how Batumi small business actually
answers.

    python scripts/ge_leads_csv.py --out data/leads.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harvey.config import load_config
from harvey.register import build_register, sqlite_query
from harvey.services import primary_service  # noqa: F401  (kept for CLI parity)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="harvey.local.yaml")
    ap.add_argument("--db", default="data/harvey.db")
    ap.add_argument("--out", default="data/leads.csv")
    args = ap.parse_args()

    config = load_config(args.config)
    rows = await build_register(sqlite_query(args.db), config)

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    obs: dict[str, dict[str, str]] = {}
    for o in db.execute("SELECT company_id, signal_code, value_text FROM observations "
                        "WHERE signal_code IN ('GE_HEAD','GE_EMAIL','GE_PHONE','GE_ID_CODE',"
                        "'GE_LEGAL_FORM','GE_SIZE','GE_ACTIVITY','GE_REGISTERED')"):
        obs.setdefault(o["company_id"], {})[o["signal_code"]] = o["value_text"] or ""
    companies = {r["id"]: dict(r) for r in db.execute("SELECT * FROM companies")}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["company", "legal_form", "id_code", "director", "phone", "email",
              "website", "activity", "size", "registered", "primary_service",
              "services", "fit", "found_via", "status"]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            o = obs.get(r["id"], {})
            company = companies.get(r["id"], {})
            w.writerow({
                "company": r["company"], "legal_form": o.get("GE_LEGAL_FORM", ""),
                "id_code": o.get("GE_ID_CODE", ""), "director": o.get("GE_HEAD", ""),
                # Registry phone, then the listing phone OSM gave us.
                "phone": o.get("GE_PHONE") or company.get("phone") or "",
                "email": o.get("GE_EMAIL", ""),
                "website": r["website"], "activity": o.get("GE_ACTIVITY", ""),
                "size": o.get("GE_SIZE", ""), "registered": o.get("GE_REGISTERED", ""),
                "primary_service": r.get("primary_service", ""),
                "services": r.get("services", ""), "fit": r["fit"],
                "found_via": company.get("source", ""), "status": r.get("status", ""),
            })

    with_service = sum(1 for r in rows if r.get("services"))
    print(f"wrote {out_path} — {len(rows)} companies, {with_service} with a service fit")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
