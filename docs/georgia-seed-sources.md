# Georgian directory sources — our own seed databases

The register says who exists. These say how to reach them. Everything below was
probed from this server on 2026-11-03 with a plain HTTP client and no cookies;
"HTTP" is what the server actually answered, not what the site claims.

The goal is not a bigger list for its own sake. It is a **seed** that joins the
register on the identification code (`GE_ID_CODE`), because a row with a phone
and no legal entity cannot be qualified, and a row with a legal entity and no
phone cannot be contacted.

## Measured access (2026-11-03)

| Source | What it holds | HTTP | Contacts in the page? | Verdict |
|---|---|---|---|---|
| **compania.ge** | ~48,000 companies, categories with counts (construction 2,071 · schools 2,092 · hotels 956 · restaurants 991) | **200** | **Yes — schema.org JSON-LD: `taxID`, `telephone`, `founder`, address** | **Primary seed. `scripts/ge_seed.py`** |
| **madloba.info** | Batumi categories with phones (construction 270 in Batumi alone), ratings, hours | **200** | Yes, plain HTML (+995 numbers) | Second seed — one page per category, no detail fetch |
| **yp.com.ge** | Organisations directory, address + phone per row | **200** | Yes (`tel:` links) | Third seed |
| **yell.ge** | Classic yellow pages, category × city (`rub=339&SI_1=Batumi` = construction in Batumi) | **200** | Partly (4 numbers in the category page) | Detail pages per company needed |
| **biznesebi.ge** | Batumi: 1,004 businesses, 71 services | 200 | **No — JS-rendered** | Browser only |
| **city24.ge** | Catalogue by category and city | 200 | **No — JS-rendered** | Browser only |
| **2gis.ge** | Map data, best addresses | 302 → browser | JS/API | Browser or paid API key |
| **georgiayp.com** | ~16,860 contacts, table export | **403** | blocked | Datacenter IP refused |
| **bia.ge** | 80,041 companies, 122,000 contact persons, 100+ filters | paid | — | ~7,000 ₾ package; the paid version of what we are building |
| **infoshop.ge** | 77,000 companies, Excel export | paid | — | same family as BIA |
| **data.gov.ge** | open data portal | no route | — | not reachable from here |

## Why compania.ge first

Every company page carries a `schema.org/Organization` JSON-LD block with:

```json
{"@type": ["Organization", "LocalBusiness"],
 "name": "ბათუმი ინვესტმენტ",
 "taxID": "445547980",
 "telephone": "+995…",
 "founder": {"@type": "Person", "name": "…"},
 "legalName": "შ.პ.ს"}
```

That is a legal entity, a decision maker and a phone in one request — the exact
three things the register is missing. `taxID` is the join key to everything else
we hold (NAPR status, liens, court cases through `ordo-mcp`).

The directory is national, so the crawl is scoped by `?search=<city>` and every
row is kept only when its own text names the city.

## Rules this crawl follows

1. **One request every 1.2s**, a User-Agent that names us and an e-mail address.
   A directory that blocks us costs more than its data is worth.
2. **Public pages only.** No login, no paywall, no captcha, no API keys that are
   not ours.
3. **Only the fields a business publishes for contact** — name, phone, address,
   activity, and the identification code that makes them a legal entity. No
   scraping of reviews, no building profiles of private individuals.
4. **Source is recorded per row** (`source: seed:compania`, `source_url`), so any
   row can be traced and removed on request.
5. **Nothing is sent.** Seeding fills the database; sending stays off.

## Joining seeds to the register

`GE_ID_CODE` is the join. After a seed run:

```bash
python scripts/ge_seed.py --city ბათუმი --limit 300
python scripts/ge_merge.py --apply       # one legal entity, one row
python scripts/ge_dedupe.py              # same business, different name
python scripts/ge_sector_report.py       # where the reachable volume now is
python scripts/ge_leads_csv.py           # the list, by priority
```

Measured on the first live seed (2026-11-03, Batumi + Kobuleti, 14 categories):

```
compania.ge   69 pages →  77 companies, 239 observations, 51 with a phone
              26 of them the same legal entity the register already had → merged
madloba.info  36 pages → 288 companies, 562 observations, 274 with a phone
              (12 categories; 4 slugs 404 — the directory uses Russian
               transliterations, recorded rather than skipped)
```

Reachability across the whole database, before and after the seed layer:

```
              companies   reachable
register          1,835         584
OSM                 359          25
compania             51          35
madloba             288         274
                 ──────      ──────
total             2,533         918   (36%, was 27%)
```

The 26 compania rows were merged on their id code (`scripts/ge_merge.py`), so the
register row inherited the phone instead of the database holding the company
twice. `scripts/ge_reachability.py` prints the table above; it is the number that
decides whether prospecting is possible at all.

A seeded row with a phone but no register match is still useful: the phone is
how Batumi answers. A register row with a `taxID` that matches a seeded row
inherits the phone, and the pair is worth more than either half.

## What is deliberately not here

- **No paid databases bought yet.** BIA/Infoshop sell the same thing we are
  assembling from public sources; buy only if the free build stalls.
- **No LinkedIn scraping.** Their terms forbid it, and the Georgian small
  business we sell to is not on it.
- **No personal data beyond a business contact.** The founder's name is a
  business role; anything else about that person is out of scope.
