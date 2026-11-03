"""The directory seed parser: what a compania.ge page gives us, and what it doesn't.

Offline, with a fixture shaped like the real page (schema.org JSON-LD plus the
listing cards). The live crawl is `scripts/ge_seed.py`; this pins the mapping,
because a wrong taxID joins the wrong legal entity and a wrong city filter
silently seeds the wrong town.
"""

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ge_seed", Path(__file__).resolve().parents[1] / "scripts" / "ge_seed.py")
ge_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ge_seed)


LISTING = """
<div class="card">
  <a href="/445547980/batumi-investment">ბათუმი ინვესტმენტ</a>
  <span>ბათუმი / შარტავა ჟიულის ქ. -10 · სამშენებლო მომსახურება</span>
</div>
<div class="card">
  <a href="/406222190/08-treveli">08 თრეველი</a>
  <span>თბილისი / წერეთელი · ტურისტული მომსახურება</span>
</div>
"""

DETAIL = """
<script type="application/ld+json">
{"@context": "https://schema.org",
 "@type": ["Organization", "LocalBusiness"],
 "name": "ბათუმი ინვესტმენტ",
 "taxID": "445547980",
 "telephone": "+995 577 75 25 26",
 "legalName": "შ.პ.ს",
 "founder": {"@type": "Person", "name": "ჯანსუღი ბოჭორიშვილი"},
 "description": "სამშენებლო მომსახურება, ბათუმი"}
</script>
<script type="application/ld+json">{"@type": "BreadcrumbList", "itemListElement": []}</script>
"""


def test_cards_reads_hrefs_and_card_text():
    found = dict(ge_seed.cards(LISTING))
    assert "/445547980/batumi-investment" in found
    assert "ბათუმი" in found["/445547980/batumi-investment"]


def test_card_text_is_what_makes_the_city_filter_possible():
    """Filtering on the listing card is the difference between one request per
    company and one per twenty."""
    kept = [h for h, text in ge_seed.cards(LISTING) if "ბათუმი" in text]
    assert kept == ["/445547980/batumi-investment"]


def test_parse_company_picks_the_organization_block_not_the_breadcrumb():
    org = ge_seed.parse_company(DETAIL)
    assert org["taxID"] == "445547980"
    assert org["name"] == "ბათუმი ინვესტმენტ"


def test_to_company_carries_the_join_key_and_the_decision_maker():
    org = ge_seed.parse_company(DETAIL)
    company, signals = ge_seed.to_company(org, "https://compania.ge/445547980/x",
                                          "ბათუმი", "სასტუმრო")
    assert company.external_id == "compania:445547980"
    assert company.phone.startswith("+995")
    assert company.source == "seed:compania"
    assert signals["GE_ID_CODE"] == "445547980"
    assert signals["GE_HEAD"] == "ჯანსუღი ბოჭორიშვილი"
    assert signals["GE_ACTIVITY"] == "სასტუმრო"


def test_a_page_without_jsonld_yields_nothing():
    assert ge_seed.parse_company("<html><body>no data</body></html>") is None


def test_missing_tax_id_falls_back_to_the_name_not_to_an_empty_key():
    org = {"@type": "Organization", "name": "უცნობი შპს"}
    company, signals = ge_seed.to_company(org, "https://compania.ge/1/x", "ბათუმი", "სასტუმრო")
    assert company.external_id == "compania:უცნობი შპს"
    assert "GE_ID_CODE" not in signals
