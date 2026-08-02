"""
test_pii - PII detection and masking tests
"""
from __future__ import annotations

from governance.pii import (
    detect_emails,
    detect_id_cards,
    detect_phones,
    mask_bank_card,
    mask_email,
    mask_id_card,
    mask_pii,
    mask_phone,
)


class TestPhone:
    def test_standard(self):
        assert mask_phone("手机13812341234") == "手机138****1234"

    def test_multiple(self):
        assert mask_phone("13812341234和13956785678") == "138****1234和139****5678"

    def test_no_match(self):
        assert mask_phone("号码12345678901") == "号码12345678901"

    def test_detect(self):
        phones = detect_phones("手机13812341234")
        assert len(phones) == 1
        assert phones[0].masked == "138****1234"


class TestIdCard:
    def test_18_digits(self):
        assert mask_id_card("110101199001011234") == "110***********1234"

    def test_18_with_x(self):
        assert mask_id_card("11010119900101123X") == "110***********123X"

    def test_detect(self):
        cards = detect_id_cards("110101199001011234")
        assert len(cards) == 1
        assert cards[0].pii_type.value == "id_card"


class TestEmail:
    def test_standard(self):
        assert mask_email("邮箱user@domain.com") == "邮箱u***@domain.com"

    def test_detect(self):
        emails = detect_emails("user@domain.com")
        assert len(emails) == 1
        assert emails[0].masked == "u***@domain.com"


class TestBankCard:
    def test_16_digits(self):
        assert mask_bank_card("6222021234567890") == "6222****7890"


class TestCombined:
    def test_all_types(self):
        text = "手机13812341234 身份证110101199001011234 邮箱user@domain.com"
        result = mask_pii(text)
        assert "138****1234" in result
        assert "110***********1234" in result
        assert "u***@domain.com" in result

    def test_no_pii(self):
        assert mask_pii("普通文本") == "普通文本"

    def test_empty(self):
        assert mask_pii("") == ""
