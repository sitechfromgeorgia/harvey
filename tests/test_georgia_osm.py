"""Georgia via OSM: the mapping from an Overpass element to a prospect.

Offline. The live path is `harvey discover --provider georgia_osm --city ბათუმი`,
and `scripts/ge_check_osm.py` proves it without writing to the database.
"""

import pytest

from harvey.collectors.discover import PROVIDERS, DiscoveryQuery
from harvey.collectors.georgia_osm import (
    OSM_TAGS, bbox_for, tag_filter, to_business,
)
from harvey.services import service_fits


def el(tags, typ="node", ident=1):
    return {"type": typ, "id": ident, "tags": tags}


Q = DiscoveryQuery(term="სასტუმრო", location="ბათუმი")


def test_city_bbox_and_unknown_city_is_an_error():
    south, west, north, east = bbox_for("ბათუმი")
    assert south < north and west < east
    assert bbox_for("Batumi") == bbox_for("ბათუმი")
    with pytest.raises(ValueError, match="no bounding box"):
        bbox_for("მარსელი")


def test_every_icp_industry_has_a_tag_filter():
    from harvey.collectors.georgia import NACE
    for term in NACE:
        assert tag_filter(term), term


def test_unknown_tag_term_raises():
    with pytest.raises(ValueError, match="no Overpass tag filter"):
        tag_filter("ზეციური ტაქსი")


def test_element_with_a_website_becomes_a_site_prospect():
    biz = to_business(el({"name:ka": "ჩაო", "website": "https://hotelchao.ge/",
                          "phone": "+995 422 22 24 00",
                          "addr:street": "ნიკო ლორთქიფანიძის", "addr:housenumber": "5"}), query=Q)
    assert biz.name == "ჩაო"
    assert biz.domain == "hotelchao.ge"
    assert biz.website == "https://hotelchao.ge"
    assert biz.phone.startswith("+995")
    assert biz.has_website is True
    assert biz.external_id == "osm:node/1"
    assert "GE_WEB_MISSING" not in biz.extra_signals


def test_facebook_page_is_not_a_website():
    biz = to_business(el({"name": "Mireosi", "website": "https://www.facebook.com/mireosi/"}), query=Q)
    assert biz.domain == ""
    assert biz.has_website is None
    assert biz.extra_signals["GE_SOCIAL_ONLY"][1] == "facebook.com"


def test_missing_website_tag_is_silence_not_proof():
    biz = to_business(el({"name": "გუდვილი"}), query=Q)
    assert biz.has_website is None
    assert biz.extra_signals["GE_WEB_MISSING"][2] == 0.6


def test_unnamed_point_is_not_a_prospect():
    assert to_business(el({"tourism": "hotel"}), query=Q) is None


def test_georgian_name_wins_over_russian():
    biz = to_business(el({"name": "Отель", "name:ka": "სასტუმრო ზღვა"}), query=Q)
    assert biz.name == "სასტუმრო ზღვა"


def test_social_only_company_gets_the_site_offer():
    company = {"name": "Mireosi", "domain": "", "website": "", "industry": "55.10.2"}
    fits = service_fits(company, [{"signal_code": "GE_SOCIAL_ONLY", "value_text": "facebook.com",
                                   "value_num": 1.0, "observed_at": "2026-11-03T10:00:00"}])
    assert fits[0]["key"] == "business_site"
    assert "Facebook" in fits[0]["pitch"]


def test_provider_registered_and_free():
    p = PROVIDERS["georgia_osm"]
    assert p.env_keys == ()
    assert p.estimate([Q]) == 0.0
