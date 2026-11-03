"""madloba.info cards: the phone is on the listing page, so no detail fetch.

Measured shape: one page holds 16 organisations, each in
``<article id="organization-NNN">`` with a title, an address and a phones line.
The test pins the three fields that make a row worth keeping — and that a card
without a name is skipped rather than stored as an empty company.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ge_seed", Path(__file__).resolve().parents[1] / "scripts" / "ge_seed.py")
ge_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ge_seed)

PAGE = """
<div class="grid-col">
  <article id="organization-10917">
    <a class="organization-item" href="/ka/batumi/construction-companies/stroycom/">
      <div class="organization-item__content">
        <h3 class="organization-item__title">STROYCOM</h3>
        <address class="organization-item__address">ბათუმი, გამსახურდიას ქ. 36</address>
        <div class="organization-item__contacts">
          <p class="organization-item__phones"><strong>ტელეფონები:</strong>
             +995 555 12 34 56, +995 577 98 76 54</p>
          <p class="organization-item__hours"><strong>სამუშაო საათები:</strong> 09:00–18:00</p>
        </div>
        <div class="organization-item__description"><p>რემონტი ბათუმში.</p></div>
      </div>
    </a>
  </article>
  <article id="organization-10918">
    <a class="organization-item" href="/ka/batumi/construction-companies/anon/">
      <h3 class="organization-item__title"> </h3>
    </a>
  </article>
</div>
"""


def test_card_fields_are_read():
    cards = ge_seed.madloba_cards(PAGE)
    assert len(cards) == 1                      # the unnamed card is skipped
    card = cards[0]
    assert card["ident"] == "10917"
    assert card["name"] == "STROYCOM"
    assert card["address"].startswith("ბათუმი")
    assert card["phone"].startswith("+995 555")


def test_first_phone_wins_when_a_card_lists_several():
    card = ge_seed.madloba_cards(PAGE)[0]
    assert "12 34 56" in card["phone"]
    assert "98 76 54" not in card["phone"]


def test_category_and_city_slugs_map_to_georgian():
    assert ge_seed.MADLOBA_CITY["batumi"] == "ბათუმი"
    assert ge_seed.MADLOBA_CATEGORY["construction-companies"] == "მშენებლობა"
    assert ge_seed.MADLOBA_CATEGORY["hotels"] == "სასტუმრო"


def test_an_empty_page_is_empty_not_an_error():
    assert ge_seed.madloba_cards("<html><body>nothing</body></html>") == []
