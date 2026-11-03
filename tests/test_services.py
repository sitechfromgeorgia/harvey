"""Service fit: which of our services the evidence supports.

The point of these tests is the rule that keeps the pitch honest — no evidence,
no offer — and that a company WITH a site is still a prospect (SEO, booking,
payments, chatbot), which is the whole reason this module exists.
"""

from harvey.services import SERVICE_BY_KEY, primary_service, service_fits, summarise


def obs(**codes):
    """Observation rows from code=(value_num, value_text) pairs."""
    rows, i = [], 0
    for code, value in codes.items():
        num, text = value if isinstance(value, tuple) else (value, "")
        rows.append({"signal_code": code, "value_num": num, "value_text": text,
                     "observed_at": f"2026-11-03T10:00:{i:02d}", "confidence": 1.0})
        i += 1
    return rows


HOTEL = {"name": "სასტუმრო გოგა", "industry": "55.10.2 სასტუმროები",
         "location": "ბათუმი", "domain": "", "website": ""}
HOTEL_WITH_SITE = {**HOTEL, "domain": "goga.ge", "website": "https://goga.ge"}


def test_no_site_small_company_gets_the_business_site():
    fits = service_fits(HOTEL, obs(GE_WEB_MISSING=(1.0, ""), GE_SIZE=(None, "მცირე")))
    assert fits[0]["key"] == "business_site"
    assert fits[0]["score"] >= 80
    assert "GE_WEB_MISSING" in fits[0]["evidence"]


def test_brand_new_business_gets_the_landing_first():
    fits = service_fits(HOTEL, obs(GE_NEW_REGISTRATION=(1.0, "40d old"),
                                   GE_WEB_MISSING=(1.0, "")))
    assert fits[0]["key"] == "landing"
    assert fits[0]["score"] >= 90


def test_running_ads_without_a_site_is_the_strongest_landing_case():
    fits = service_fits(HOTEL, obs(GE_WEB_MISSING=(1.0, ""), RUNNING_META_ADS=(1.0, "")))
    assert fits[0]["key"] == "landing"


def test_company_with_a_site_is_still_a_prospect():
    """The bug this module exists to prevent: "has a site" → drop the company."""
    fits = service_fits(HOTEL_WITH_SITE, obs(SERP_RANK=(22.0, "სასტუმრო ბათუმი")))
    assert fits, "a company ranking #22 must still have an offer"
    assert fits[0]["key"] == "seo"
    assert "#22" in fits[0]["pitch"]


def test_booking_sector_without_online_booking_gets_the_webapp():
    fits = service_fits(HOTEL_WITH_SITE, obs(NO_ONLINE_BOOKING=(1.0, ""),
                                              GE_ACTIVITY=(None, "55.10.2 სასტუმროები")))
    assert fits[0]["key"] == "complex_webapp"


def test_retail_without_payments_gets_the_payment_integration():
    shop = {"name": "მაღაზია", "industry": "47.19", "domain": "shop.ge", "website": "https://shop.ge"}
    fits = service_fits(shop, obs(GE_ACTIVITY=(None, "47.19 სხვა საცალო ვაჭრობა")))
    assert any(f["key"] == "payments" for f in fits)


def test_it_company_gets_saas_mvp():
    it = {"name": "კოდი", "industry": "62.01", "domain": "code.ge", "website": "https://code.ge"}
    fits = service_fits(it, obs(GE_ACTIVITY=(None, "62.01 კომპიუტერული პროგრამირება")))
    assert fits[0]["key"] == "saas_mvp"


def test_ai_blocked_site_gets_the_chatbot():
    fits = service_fits(HOTEL_WITH_SITE, obs(BLOCKS_AI_CRAWLERS=(1.0, "")))
    assert any(f["key"] == "ai_chatbot" for f in fits)


def test_blog_stale_is_an_age_in_days_not_a_flag():
    """BLOG_STALE carries the age of the newest content: 6 days is healthy,
    982 days is abandoned. Reading it as a boolean would sell SEO to everyone."""
    fresh = service_fits(HOTEL_WITH_SITE, obs(BLOG_STALE=(6.0, "newest content 2026-10-28")))
    assert not any(f["key"] == "seo" for f in fresh)

    stale = service_fits(HOTEL_WITH_SITE, obs(BLOG_STALE=(982.0, "newest content 2024-02-25")))
    seo = [f for f in stale if f["key"] == "seo"]
    assert seo and seo[0]["score"] >= 80


def test_ads_flag_zero_is_not_running_ads():
    fits = service_fits({"name": "x", "domain": "x.ge", "website": "https://x.ge", "industry": ""},
                        obs(RUNNING_GOOGLE_ADS=(0.0, "")))
    assert not any(f["key"] == "landing" for f in fits)


def test_no_evidence_means_no_offer():
    """A company we know nothing about gets a question, not a pitch."""
    fits = service_fits({"name": "უცნობი", "industry": "", "domain": "",
                         "website": ""}, [])
    # The one honest exception: a company with no site at all does have a site offer.
    assert fits[0]["key"] in {"business_site", "landing"}
    assert primary_service({"name": "x", "industry": "", "domain": "",
                            "website": ""}, []) is not None

    # But a company with a site and no observations has nothing to sell on evidence.
    assert service_fits({"name": "x", "industry": "", "domain": "x.ge",
                         "website": "https://x.ge"}, []) == []
    assert primary_service({"name": "x", "domain": "x.ge", "website": "https://x.ge"}, []) is None


def test_scores_are_bounded_and_sorted():
    fits = service_fits(HOTEL, obs(GE_WEB_MISSING=(1.0, ""), GE_SIZE=(None, "მცირე"),
                                   GE_NEW_REGISTRATION=(1.0, "10d"), RUNNING_GOOGLE_ADS=(1.0, "")))
    assert all(0 <= f["score"] <= 100 for f in fits)
    assert [f["score"] for f in fits] == sorted((f["score"] for f in fits), reverse=True)


def test_summary_lists_prices_for_the_register():
    line = summarise(HOTEL, obs(GE_WEB_MISSING=(1.0, ""), GE_SIZE=(None, "მცირე")))
    assert "ბიზნეს საიტი" in line and "₾" in line


def test_every_service_has_a_price_and_a_reason():
    for key, svc in SERVICE_BY_KEY.items():
        assert svc["label"] and svc["price"] and svc["why"], key
