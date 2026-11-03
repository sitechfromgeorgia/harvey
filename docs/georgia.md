# Georgia — the register is the prospecting database

Harvey's shipped providers are American or global. In Georgia they are close to
useless: OSM maps premises only, DataForSEO and Serper are paid and thin, and
none of them know a company's identification code, its legal form, its
declared size, or who its director is.

The state already publishes all of that. This fork reads it.

## What was added

| Piece | Where | What it does |
|---|---|---|
| `GeorgiaRegistry` discovery provider | `harvey/collectors/georgia.py` | Enumerates active businesses by NACE activity + region from the Geostat statistical register (open JSON API, no key, ~50 req/min) |
| `GeorgiaOSM` discovery provider | `harvey/collectors/georgia_osm.py` | OSM objects by Georgian tag inside a city bounding box — the mirror image of the register: fewer businesses, but many with a website to audit |
| Service fit | `harvey/services.py` | Maps the evidence to which of SiTech's services to sell (site, SEO, booking, payments, chatbot, SaaS, UI/UX, automation), with the price band and a quotable line |
| Ten registry signals | `harvey/signals.py` | `GE_ID_CODE`, `GE_LEGAL_FORM`, `GE_SIZE`, `GE_ACTIVITY`, `GE_REGISTERED`, `GE_NEW_REGISTRATION`, `GE_HEAD`, `GE_PHONE`, `GE_EMAIL`, `GE_WEB_MISSING`, `GE_SOCIAL_ONLY` |
| Georgian ICP preset | `harvey.local.yaml` (gitignored) | Batumi/Kobuleti — 14 sectors, any service |
| Georgian outreach playbook | `skills/georgian_outreach.md` | Subject lines, tone, banned phrases, follow-up cadence, channel choice |
| Georgian opt-out recognition | `harvey/config.py`, `harvey/agents/handler.py` | The footer can ask for «ნუ მწერთ», and a Georgian reply saying it stops Harvey |
| End-to-end diagnostics | `scripts/ge_check_registry.py`, `scripts/ge_report.py` | Prove the live API path and the service distribution in one command |

## Why the register beats a listings database here

A Google Business Profile tells you a business exists and has a phone. The
register tells you:

- **the legal entity** — შპს or an individual entrepreneur, which predicts both
  budget and who signs;
- **the identification code** — the identifier that survives a rename, and the
  key into every other Georgian register;
- **the director's name as the state records it** — not scraped from a team
  page, not guessed from a pattern;
- **the declared size band** — მცირე / საშუალო / მსხვილი;
- **the registration date** — a two-month-old entity is assembling its whole
  stack right now;
- **the NACE activity** — the register's own words for what they do, usable in
  the first line of an email.

Measured on the live API (2026-11, `scripts/ge_check_registry.py`):

```
სასტუმრო / ბათუმი  → 467 active entities (NACE 55.10, region 15)
                     50 read: 3 with a site in the register, 47 without
ქობულეთი           → present, same shape
```

## Honesty rules this provider follows

1. **`GE_WEB_MISSING` is not `NO_WEBSITE`.** An empty `web` field means the
   business never told the state, not that no site exists. It is recorded at
   0.6 confidence and the free profile stage confirms it before it appears in
   an email. Selling a website to someone who has one is the most expensive
   mistake this pipeline can make.
2. **An unmapped industry word is an error, not an empty result.** `nace_for()`
   raises. A silent zero-row run is indistinguishable from an empty market.
3. **The region filter is not the city filter.** Adjara (region 15) spans
   Batumi, Kobuleti and Keda, so the legal address is filtered too.
4. **Personal data.** A head's name is a person's data. It is used for a
   legitimate business contact only, never profiled, never shared. The
   register is statistical, not the legal register: only a NAPR extract has
   legal force, and the source must be cited (საქსტატი).

## Two sources, one database

| | `georgia_registry` | `georgia_osm` |
|---|---|---|
| Knows | every legal entity, id code, director, size, registration date | businesses with a website tag, phone, address |
| Blind to | websites (sparse `web` field) | many legal entities, most small ones |
| Offer it makes possible | a site, a landing, a booking flow | SEO, redesign, chatbot, payments — because there is a site to audit |

Neither is enough alone. A pipeline fed only by the register sells websites to
everyone (measured: 93 of 94 leads came out as "business_site"). A pipeline fed
only by OSM skips the majority of the market. Run both:

```bash
harvey discover --provider georgia_registry --city ბათუმი --limit 50
harvey discover --provider georgia_osm      --city ბათუმი --limit 30
harvey profile        # free: reads the sites, records SITE_PAGE_COUNT, BLOG_STALE, NO_SCHEMA_MARKUP, SERP_RANK evidence
harvey export         # now each row carries its service + price band
```

Then `harvey/services.py` decides the offer per company from the evidence — and
says nothing when there is no evidence, which is why `harvey profile` has to
run before the outbox is worth reading.

## How this relates to `ordo-mcp`

`sitechfromgeorgia/ordo-mcp` is the MCP server the legal lane uses. It
reverse-engineered these Georgian sources and exposes them as 78 tools. This
fork does **not** import it — a sales tool that cannot start because a sibling
checkout moved is a bad tool — but it is the reference for the contract, and
the source for everything not yet wired here.

Wired today: Geostat register (discovery).
Not yet wired, and the reason each one is interesting:

| ordo-mcp tool | Signal it could become | Why it sells |
|---|---|---|
| `registry_liens`, `registry_movable_pledges` | `GE_PLEDGE_RECENT` | They just pledged an asset or took secured credit — an investment cycle, money is moving |
| `tax_dispute_search`, `rs_dispute_search` | `GE_TAX_DISPUTE` | An active dispute means a specific, urgent need (accounting, legal, documents) |
| `registry_procurement_list` | `GE_BLACKLISTED` | Disqualified from public tenders — and a hard disqualifier for outreach |
| `court_search_decisions` | `GE_LITIGATION` | A company in litigation is buying professional services |
| `companyinfo_company` | `GE_FINANCIALS`, `GE_SANCTIONS` | Declared revenue says whether 1,500 GEL is a decision or a purchase order |
| `registry_company_search` | `GE_STATUS` | NAPR status and liquidation applications — the legal register, not the statistical one |

Each one needs the same three things: a collector, a catalog entry, and a test
that pins the mapping. That is the roadmap, in that order.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Confirm the live register path before touching config
python scripts/ge_check_registry.py --city ბათუმი --industry სასტუმრო --limit 50

# Configure the product and ICP (gitignored), then seed the signal catalog
cp harvey.yaml harvey.local.yaml     # if you do not have one yet
harvey signals --confirm free        # nothing is collected until you confirm it
harvey discover --providers          # the menu now includes Georgia, at $0.00
harvey discover                      # NACE + region, city-filtered
harvey status
```

Sending stays off (`channels.email.enabled: false`) until a dedicated sending
domain is warmed: cold volume from the company's primary mailbox damages the
domain clients answer on.

## Tests

```bash
pytest tests/test_georgia_registry.py tests/test_georgian_opt_out.py -q
```

Offline by design. `scripts/ge_check_registry.py` is the live check — a suite
that needs the Georgian state register up to pass fails for the wrong reason.
