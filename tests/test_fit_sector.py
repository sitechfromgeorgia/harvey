"""The register's NACE strings must answer to the ICP's words.

A Georgian lead whose industry is written "55.10.2 სასტუმროები და განთავსების
მსგავსი საშუალებები" scored zero sector fit against an ICP that says
"სასტუმრო", so the ranking was decided by which companies happened to have a
phone number. These tests pin the three ways that match is now made.
"""

from harvey.fit import sector_matches

ICP = {"სასტუმრო", "რესტორანი", "სტომატოლოგია", "IT"}


def test_nace_string_matches_the_icp_word():
    assert sector_matches("55.10.2 სასტუმროები და განთავსების მსგავსი საშუალებები", ICP)
    assert sector_matches("86.23.0 სტომატოლოგიური პრაქტიკის საქმიანობები", ICP)


def test_the_word_itself_still_matches():
    assert sector_matches("სასტუმრო", ICP)
    assert sector_matches("Hotel", {"hotel"})


def test_an_unrelated_sector_does_not_match():
    assert not sector_matches("47.73.9 საცალო ვაჭრობა ფარმაცევტული საქონლით", ICP)
    assert not sector_matches("", ICP)
    assert not sector_matches("55.10", set())


def test_a_missing_georgia_mapping_is_not_a_crash():
    # "IT" has a NACE mapping; a word with none must simply not match.
    assert not sector_matches("01.11.0 მარცვლეულის მოყვანა", {"ზეციური ტაქსი"})
