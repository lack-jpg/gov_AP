"""
governance.pii - PII desensitization: mask phone, ID card, email fields in output

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement PII detection and masking (138****1234, 110***********1234, u***@domain.com)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================
# PII 类型枚举
# ============================================================


class PIIType(str, Enum):
    """PII 类型标识"""
    PHONE = "phone"           # 手机号
    ID_CARD = "id_card"       # 身份证号
    EMAIL = "email"           # 邮箱
    BANK_CARD = "bank_card"   # 银行卡号
    ADDRESS = "address"       # 地址（模糊匹配）
    NAME = "name"             # 姓名（模糊匹配）


# ============================================================
# PII 检测结果
# ============================================================


@dataclass
class PIIMatch:
    """单个 PII 匹配结果"""
    pii_type: PIIType
    original: str           # 原始文本
    masked: str             # 脱敏后文本
    start: int              # 在原文中的起始位置
    end: int                # 在原文中的结束位置

    def __repr__(self) -> str:
        return f"<PIIMatch type={self.pii_type.value} original={self.original!r} masked={self.masked!r}>"


@dataclass
class PIIResult:
    """PII 检测与脱敏的完整结果"""
    original_text: str
    masked_text: str
    matches: list[PIIMatch] = field(default_factory=list)
    has_pii: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_text": self.original_text,
            "masked_text": self.masked_text,
            "has_pii": self.has_pii,
            "match_count": len(self.matches),
            "matches": [
                {
                    "type": m.pii_type.value,
                    "original": m.original,
                    "masked": m.masked,
                    "start": m.start,
                    "end": m.end,
                }
                for m in self.matches
            ],
        }


# ============================================================
# 正则模式（编译一次，全局复用）
# ============================================================

# 手机号：1[3-9]xxxxxxxxx
_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")

# 身份证号：18位（最后一位可能是X）或 15位（旧版）
# 18位掩码: 前3 + 11星 + 后4  → 110***********1234
# 15位掩码: 前3 + 8星  + 后4  → 110********1234
_ID_CARD_18_PATTERN = re.compile(
    r"(?<!\d)(\d{3})\d{11}(\d{3}[\dXx])(?!\d)"
)
_ID_CARD_15_PATTERN = re.compile(
    r"(?<!\d)(\d{3})\d{8}(\d{4})(?!\d)"
)

# 邮箱：user@domain.com
_EMAIL_PATTERN = re.compile(
    r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
)

# 银行卡号：16-19位数字（简单匹配）
_BANK_CARD_PATTERN = re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)")


# ============================================================
# 脱敏函数
# ============================================================


def mask_phone(text: str) -> str:
    """
    手机号脱敏：保留前3位和后4位，中间4位替换为 ****。

    Example:
        >>> mask_phone("我的手机是13812341234")
        '我的手机是138****1234'

    Args:
        text: 含手机号的文本

    Returns:
        脱敏后文本
    """
    return _PHONE_PATTERN.sub(r"\1****\2", text)


def mask_id_card(text: str) -> str:
    """
    身份证号脱敏：保留前6位和后4位，中间替换为 **********。

    - 18位身份证：110101199001011234 → 110101********1234
    - 15位身份证：110101900101123   → 110101******123

    Example:
        >>> mask_id_card("身份证号110101199001011234")
        '身份证号110101********1234'

    Args:
        text: 含身份证号的文本

    Returns:
        脱敏后文本
    """
    # 先处理18位，再处理15位
    result = _ID_CARD_18_PATTERN.sub(r"\1***********\2", text)
    result = _ID_CARD_15_PATTERN.sub(r"\1********\2", result)
    return result


def mask_email(text: str) -> str:
    """
    邮箱脱敏：用户名保留首字符，其余替换为 ***。

    Example:
        >>> mask_email("联系邮箱user@domain.com")
        '联系邮箱u***@domain.com'

    Args:
        text: 含邮箱的文本

    Returns:
        脱敏后文本
    """

    def _email_replacer(match: re.Match) -> str:
        username = match.group(1)
        domain = match.group(2)
        masked_user = username[0] + "***"
        return f"{masked_user}@{domain}"

    return _EMAIL_PATTERN.sub(_email_replacer, text)


def mask_bank_card(text: str) -> str:
    """
    银行卡号脱敏：保留前4位和后4位，中间替换为 ****。

    Example:
        >>> mask_bank_card("卡号6222021234567890123")
        '卡号6222****0123'

    Args:
        text: 含银行卡号的文本

    Returns:
        脱敏后文本
    """
    return _BANK_CARD_PATTERN.sub(r"\1****\2", text)


def mask_pii(text: str) -> str:
    """
    对所有已知 PII 类型进行脱敏处理（一站式）。

    处理顺序：手机号 → 身份证 → 银行卡 → 邮箱
    先处理长模式避免短模式误匹配。

    Example:
        >>> mask_pii("手机13812341234，身份证110101199001011234，邮箱user@domain.com")
        '手机138****1234，身份证110101********1234，邮箱u***@domain.com'

    Args:
        text: 原始文本

    Returns:
        脱敏后文本
    """
    result = text
    result = mask_phone(result)
    result = mask_id_card(result)
    result = mask_bank_card(result)
    result = mask_email(result)
    return result


# ============================================================
# 检测函数
# ============================================================


def detect_phones(text: str) -> list[PIIMatch]:
    """
    检测文本中的手机号。

    Args:
        text: 待检测文本

    Returns:
        PIIMatch 列表
    """
    matches: list[PIIMatch] = []
    for m in _PHONE_PATTERN.finditer(text):
        original = m.group(0)
        masked = f"{m.group(1)}****{m.group(2)}"
        matches.append(PIIMatch(
            pii_type=PIIType.PHONE,
            original=original,
            masked=masked,
            start=m.start(),
            end=m.end(),
        ))
    return matches


def detect_id_cards(text: str) -> list[PIIMatch]:
    """
    检测文本中的身份证号（18位和15位）。

    Args:
        text: 待检测文本

    Returns:
        PIIMatch 列表
    """
    matches: list[PIIMatch] = []
    # 18位
    for m in _ID_CARD_18_PATTERN.finditer(text):
        original = m.group(0)
        masked = f"{m.group(1)}{'*' * 11}{m.group(2)}"
        matches.append(PIIMatch(
            pii_type=PIIType.ID_CARD,
            original=original,
            masked=masked,
            start=m.start(),
            end=m.end(),
        ))
    # 15位
    for m in _ID_CARD_15_PATTERN.finditer(text):
        original = m.group(0)
        masked = f"{m.group(1)}{'*' * 8}{m.group(2)}"
        matches.append(PIIMatch(
            pii_type=PIIType.ID_CARD,
            original=original,
            masked=masked,
            start=m.start(),
            end=m.end(),
        ))
    return matches


def detect_emails(text: str) -> list[PIIMatch]:
    """
    检测文本中的邮箱地址。

    Args:
        text: 待检测文本

    Returns:
        PIIMatch 列表
    """
    matches: list[PIIMatch] = []
    for m in _EMAIL_PATTERN.finditer(text):
        original = m.group(0)
        username = m.group(1)
        domain = m.group(2)
        masked_user = username[0] + "***"
        masked = f"{masked_user}@{domain}"
        matches.append(PIIMatch(
            pii_type=PIIType.EMAIL,
            original=original,
            masked=masked,
            start=m.start(),
            end=m.end(),
        ))
    return matches


def detect_bank_cards(text: str) -> list[PIIMatch]:
    """
    检测文本中的银行卡号。

    Args:
        text: 待检测文本

    Returns:
        PIIMatch 列表
    """
    matches: list[PIIMatch] = []
    for m in _BANK_CARD_PATTERN.finditer(text):
        original = m.group(0)
        masked = f"{m.group(1)}****{m.group(2)}"
        matches.append(PIIMatch(
            pii_type=PIIType.BANK_CARD,
            original=original,
            masked=masked,
            start=m.start(),
            end=m.end(),
        ))
    return matches


def detect_pii(text: str) -> PIIResult:
    """
    检测文本中所有类型的 PII 并返回详细结果。

    Args:
        text: 待检测文本

    Returns:
        PIIResult 包含原始文本、脱敏文本和所有匹配项
    """
    all_matches: list[PIIMatch] = []
    all_matches.extend(detect_phones(text))
    all_matches.extend(detect_id_cards(text))
    all_matches.extend(detect_bank_cards(text))
    all_matches.extend(detect_emails(text))

    # 按位置排序
    all_matches.sort(key=lambda m: m.start)

    # 生成脱敏文本
    masked_text = mask_pii(text)

    return PIIResult(
        original_text=text,
        masked_text=masked_text,
        matches=all_matches,
        has_pii=len(all_matches) > 0,
    )


def detect_and_mask(text: str) -> str:
    """
    检测并脱敏文本中的所有 PII（快捷方法，只返回脱敏后文本）。

    Args:
        text: 原始文本

    Returns:
        脱敏后文本
    """
    return mask_pii(text)


def batch_detect_and_mask(texts: list[str]) -> list[str]:
    """
    批量检测并脱敏多条文本。

    Args:
        texts: 原始文本列表

    Returns:
        脱敏后文本列表
    """
    return [mask_pii(t) for t in texts]


# ============================================================
# Smoke Test
# ============================================================

if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(name: str, actual: Any, expected: Any) -> None:
        global passed, failed
        if actual == expected:
            passed += 1
            print(f"  [OK] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected={expected!r}, got={actual!r}")

    print("=== governance.pii smoke test ===")

    # ── Phone masking ──
    print("--- Phone ---")
    check("phone_standard", mask_phone("手机13812341234"), "手机138****1234")
    check("phone_multi", mask_phone("13812341234和13956785678"),
          "138****1234和139****5678")
    check("phone_no_match", mask_phone("号码12345678901"), "号码12345678901")
    check("phone_in_text", mask_phone("请联系客服13800009999获取帮助"),
          "请联系客服138****9999获取帮助")

    # ── ID Card masking ──
    print("--- ID Card ---")
    check("id_card_18", mask_id_card("110101199001011234"),
          "110***********1234")
    check("id_card_18_X", mask_id_card("11010119900101123X"),
          "110***********123X")
    check("id_card_15", mask_id_card("110101900101123"),
          "110********1123")
    check("id_card_in_text", mask_id_card("身份证号110101199001011234请查收"),
          "身份证号110***********1234请查收")

    # ── Email masking ──
    print("--- Email ---")
    check("email_standard", mask_email("邮箱user@domain.com"),
          "邮箱u***@domain.com")
    check("email_short", mask_email("a@domain.com"), "a***@domain.com")
    check("email_single", mask_email("x@test.org"), "x***@test.org")
    check("email_multi", mask_email("user@foo.com和admin@bar.org"),
          "u***@foo.com和a***@bar.org")

    # ── Bank card masking ──
    print("--- Bank Card ---")
    check("bank_16", mask_bank_card("6222021234567890"),
          "6222****7890")
    check("bank_19", mask_bank_card("6222021234567890123"),
          "6222****0123")

    # ── Combined mask_pii ──
    print("--- Combined ---")
    check("combined_all", mask_pii("手机13812341234 身份证110101199001011234 邮箱user@domain.com"),
          "手机138****1234 身份证110***********1234 邮箱u***@domain.com")
    check("no_pii", mask_pii("这是普通文本"), "这是普通文本")
    check("empty", mask_pii(""), "")

    # ── Detection ──
    print("--- Detection ---")
    phones = detect_phones("手机13812341234和13956785678")
    check("detect_phones_count", len(phones), 2)
    check("detect_phones_type", phones[0].pii_type, PIIType.PHONE)
    check("detect_phones_mask", phones[0].masked, "138****1234")

    id_cards = detect_id_cards("110101199001011234和110101900101123")
    check("detect_id_cards_count", len(id_cards), 2)

    emails = detect_emails("user@domain.com和admin@bar.org")
    check("detect_emails_count", len(emails), 2)
    check("detect_emails_mask", emails[0].masked, "u***@domain.com")

    # ── detect_pii (full) ──
    print("--- Full Detection ---")
    result = detect_pii("手机13812341234 邮箱user@domain.com")
    check("full_has_pii", result.has_pii, True)
    check("full_match_count", len(result.matches), 2)
    check("full_masked", result.masked_text,
          "手机138****1234 邮箱u***@domain.com")

    result_empty = detect_pii("这是普通文本")
    check("full_no_pii", result_empty.has_pii, False)
    check("full_no_match_count", len(result_empty.matches), 0)

    # ── to_dict ──
    print("--- to_dict ---")
    d = result.to_dict()
    check("dict_has_pii", d["has_pii"], True)
    check("dict_match_count", d["match_count"], 2)
    check("dict_keys", set(d.keys()),
          {"original_text", "masked_text", "has_pii", "match_count", "matches"})

    # ── batch ──
    print("--- Batch ---")
    batch_result = batch_detect_and_mask([
        "手机13812341234",
        "邮箱user@domain.com",
        "普通文本",
    ])
    check("batch_len", len(batch_result), 3)
    check("batch_0", batch_result[0], "手机138****1234")
    check("batch_1", batch_result[1], "邮箱u***@domain.com")
    check("batch_2", batch_result[2], "普通文本")

    # ── Summary ──
    total = passed + failed
    print(f"\n=== {passed}/{total} passed, {failed} failed ===")
    if failed > 0:
        raise SystemExit(1)
