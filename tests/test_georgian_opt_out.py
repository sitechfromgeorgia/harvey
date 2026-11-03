"""Georgian opt-out recognition, on both sides of the conversation.

Sending a Georgian cold email with an English "Reply no thanks" footer is the
same bug as not having a footer: the prospect answers in Georgian, Harvey
doesn't recognise it, and keeps writing. These tests pin the two places that
decision is made — the config validator that approves the footer wording, and
the handler that reads the reply.
"""

import pytest
from pydantic import ValidationError

from harvey.agents.handler import _opt_out_reason
from harvey.config import ComplianceConfig


# ── The footer Harvet writes ────────────────────────────────────────────

def test_georgian_footer_is_accepted():
    cfg = ComplianceConfig(
        opt_out_line='არ გაინტერესებთ? უპასუხეთ "ნუ მწერთ" და მეტს აღარ მოგწერთ.')
    assert "ნუ მწერთ" in cfg.opt_out_line


def test_georgian_footer_with_a_guillemet_is_accepted():
    ComplianceConfig(opt_out_line="არ გაინტერესებთ? მოწერეთ «არ მინდა».")


def test_footer_that_asks_for_nothing_recognised_is_rejected():
    with pytest.raises(ValidationError):
        ComplianceConfig(opt_out_line="არ გაინტერესებთ? უპასუხეთ რამეს.")


def test_english_and_spanish_footers_still_work():
    ComplianceConfig(opt_out_line='Not interested? Reply "no thanks".')
    ComplianceConfig(opt_out_line='¿No le interesa? Responda BAJA.')


# ── What the prospect writes back ───────────────────────────────────────

@pytest.mark.parametrize("reply", [
    "ნუ მწერთ",
    "ნუ მოგვწერთ მეტს",
    "აღარ მომწეროთ, გთხოვთ",
    "მოხსენით სიიდან",
    "გააუქმეთ გამოწერა",
    "შეწყვიტეთ გამოგზავნა",
    "შემაწყვიტეთ ეს მეილები",
    "ნუ შემაწუხებთ",
    "არ მაინტერესებს",
    "ამ შემოთავაზებით არ გვაინტერესებს",
])
def test_georgian_opt_out_is_recognised(reply):
    reason = _opt_out_reason(reply, "")
    assert reason is not None, reply
    assert reason["rule"] == "phrase"


@pytest.mark.parametrize("reply", [
    "არა, საინტერესოა — მოვისმინოთ",
    "ჯერ არ მაინტერესებს, სექტემბერში დამიკავშირდით",
    "არ მინდა პრემიუმ პაკეტი, ბაზისური მაწყობს",
    "რა ღირს?",
    "გამარჯობა, დიახ, მაინტერესებს",
])
def test_georgian_non_opt_outs_are_not_mistaken(reply):
    assert _opt_out_reason(reply, "") is None, reply


def test_english_opt_out_still_recognised():
    assert _opt_out_reason("Please unsubscribe me", "") is not None
