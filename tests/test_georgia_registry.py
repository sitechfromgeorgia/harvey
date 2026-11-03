"""Georgia's statistical business register as a discovery source.

Offline only: the shape of the mapping is what these tests pin down. The live
API is exercised by `scripts/ge_check_registry.py`, which is a diagnostic, not
a test — a suite that needs the Georgian state register up to pass is a suite
that fails for the wrong reason.
"""

import pytest

from harvey.collectors.discover import PROVIDERS, Business, DiscoveryQuery, _observations
from harvey.collectors.georgia import (
    NACE, CITIES, to_business, nace_for, region_for,
)
from harvey.signals import SIGNAL_CATALOG


ROW = {
    "stat_id": 55540077,
    "id_code": "145443856",
    "name": "ჯემალ ვერძაძე",
    "legal_form": "ინდივიდუალური მეწარმე",
    "active": True,
    "size": "მცირე",
    "activity": "55.10.2 სასტუმროები და განთავსების მსგავსი საშუალებები რესტორნების გარეშე",
    "legal_address": "საქართველო, ქალაქი ბათუმი, სტეფანე ზუბალაშვილის ქუჩა, N 4",
    "legal_region": "აჭარა",
    "actual_address": "ზუბალაშვილის N4",
    "head": "ჯემალ ვერძაძე",
    "email": "acc.group@mail.ru",
    "phone": None,
    "web": None,
    "registered": "2019-01-29",
    "last_change": "2019-01-29",
}


def test_city_maps_to_region_and_address_filter():
    assert region_for("ბათუმი") == ("15", "ბათუმი")
    assert region_for("Batumi") == ("15", "ბათუმი")
    # A substring still resolves: "ბათუმი, აჭარა" is how an ICP is often written.
    assert region_for("ბათუმი, აჭარა") == ("15", "ბათუმი")


def test_unknown_city_is_an_error_not_an_empty_run():
    with pytest.raises(ValueError, match="unknown Georgian city"):
        region_for("მარსელი")


def test_industry_maps_to_nace():
    assert nace_for("სასტუმრო") == "55.10"
    assert nace_for("hotel") == "55.10"
    assert nace_for("სასტუმროები") == "55.10"


def test_unmapped_industry_is_an_error():
    with pytest.raises(ValueError, match="no NACE code"):
        nace_for("ზეციური ტაქსი")


def test_every_alias_points_at_a_real_looking_nace_code():
    for alias, code in NACE.items():
        assert code.count(".") == 1, f"{alias} → {code} is not a NACE class"


def test_every_city_region_exists():
    from harvey.collectors.georgia import REGIONS
    for city, (region, needle) in CITIES.items():
        assert region in REGIONS, f"{city} points at unknown region {region}"
        assert needle, f"{city} has no address filter"


def test_row_becomes_a_business_with_its_registry_facts():
    biz = to_business(ROW, query=DiscoveryQuery(term="სასტუმრო", location="ბათუმი"))
    assert biz.name == "ჯემალ ვერძაძე"
    assert biz.external_id == "geostat:145443856"
    assert biz.provider == "georgia_registry"
    assert biz.location == "ბათუმი"
    assert biz.address.startswith("საქართველო, ქალაქი ბათუმი")
    # No web field → has_website stays UNKNOWN, so no NO_WEBSITE row is written.
    assert biz.has_website is None
    assert "GE_WEB_MISSING" in biz.extra_signals
    assert biz.extra_signals["GE_WEB_MISSING"][2] == 0.6
    assert biz.extra_signals["GE_ID_CODE"][1] == "145443856"
    assert biz.extra_signals["GE_HEAD"][1] == "ჯემალ ვერძაძე"
    assert biz.extra_signals["GE_LEGAL_FORM"][1] == "ინდივიდუალური მეწარმე"
    assert biz.extra_signals["GE_SIZE"][1] == "მცირე"
    assert biz.extra_signals["GE_EMAIL"][1] == "acc.group@mail.ru"


def test_website_present_sets_domain_and_no_missing_signal():
    row = dict(ROW, web="https://Hotel-Example.GE/")
    biz = to_business(row, query=DiscoveryQuery(term="hotel", location="ბათუმი"))
    assert biz.domain == "hotel-example.ge"
    assert biz.website == "https://hotel-example.ge"
    assert biz.has_website is True
    assert "GE_WEB_MISSING" not in biz.extra_signals


def test_recent_registration_sets_the_trigger_signal():
    from datetime import date, timedelta
    fresh = (date.today() - timedelta(days=40)).isoformat()
    biz = to_business(dict(ROW, registered=fresh),
                      query=DiscoveryQuery(term="hotel", location="ბათუმი"))
    assert biz.extra_signals["GE_NEW_REGISTRATION"][0] == 1.0

    old = to_business(dict(ROW, registered="2002-05-29"),
                      query=DiscoveryQuery(term="hotel", location="ბათუმი"))
    assert "GE_NEW_REGISTRATION" not in old.extra_signals


def test_registry_facts_become_observations_only_when_confirmed():
    biz = to_business(ROW, query=DiscoveryQuery(term="სასტუმრო", location="ბათუმი"))
    query = DiscoveryQuery(term="სასტუმრო", location="ბათუმი")

    confirmed = {"FOUND_IN_SERP", "GE_ID_CODE", "GE_HEAD", "GE_WEB_MISSING"}
    rows = _observations(biz, "company-1", confirmed, "run-1", query)
    codes = {r["signal_code"] for r in rows}
    assert codes == confirmed
    assert all(r["company_id"] == "company-1" and r["run_id"] == "run-1" for r in rows)
    # No NO_WEBSITE row: the register's silence is not proof.
    assert "NO_WEBSITE" not in codes

    none = _observations(biz, "company-1", set(), "run-1", query)
    assert none == []


def test_provider_is_registered_and_free():
    provider = PROVIDERS["georgia_registry"]
    assert provider.kind == "listings"
    assert provider.env_keys == ()
    assert provider.estimate([DiscoveryQuery(term="hotel", location="ბათუმი")]) == 0.0


def test_every_georgia_signal_is_in_the_catalog():
    codes = {s["code"] for s in SIGNAL_CATALOG}
    for code in ("GE_ID_CODE", "GE_LEGAL_FORM", "GE_SIZE", "GE_ACTIVITY",
                 "GE_REGISTERED", "GE_NEW_REGISTRATION", "GE_HEAD", "GE_PHONE",
                 "GE_EMAIL", "GE_WEB_MISSING"):
        assert code in codes


def test_catalog_categories_stay_inside_the_governed_set():
    allowed = {"discovery", "profile", "people", "verification"}
    for sig in SIGNAL_CATALOG:
        assert sig["category"] in allowed, sig["code"]
        assert sig["value_type"] in {"num", "text", "bool"}, sig["code"]
