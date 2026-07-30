"""
governance.security - Security detection: PII, prompt injection, sensitive content

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement input/output security scanning
"""
from __future__ import annotations

import re

from orchestration.langgraph.state import GuardrailResult
from tools.logger import get_logger

logger = get_logger(__name__)


class SecurityChecker:
    """
    安全检测器 — 输入/输出双向安全检查。

    检测项:
        输入: PII（身份证/手机/邮箱）、Prompt Injection、敏感词
        输出: 信息泄露（内部错误/密钥/系统Prompt）、PII 未脱敏
    """

    # ================================================================
    # PII 正则
    # ================================================================

    _PII_PATTERNS: dict[str, re.Pattern] = {
        "phone": re.compile(
            r"1[3-9]\d{9}",  # 手机号
        ),
        "id_card": re.compile(
            r"\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]",
        ),
        "email": re.compile(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        ),
    }

    # ================================================================
    # Prompt Injection 特征
    # ================================================================

    _INJECTION_PATTERNS: list[str] = [
        "ignore previous instructions",
        "ignore all previous",
        "forget your instructions",
        "system prompt",
        "you are now",
        "new instructions",
        "disregard",
        "bypass",
        "jailbreak",
    ]

    # ================================================================
    # 敏感词（政务场景）
    # ================================================================

    _SENSITIVE_WORDS: list[str] = [
        "反动",
        "颠覆",
        "分裂",
        "暴动",
        "邪教",
        "赌博",
        "色情",
        "毒品",
    ]

    # ── 公开接口 ──

    def check_input(self, text: str) -> GuardrailResult:
        """
        检查用户输入的安全性。

        Args:
            text: 用户输入文本

        Returns:
            GuardrailResult
        """
        if not text:
            return GuardrailResult(passed=True)

        # 1. PII 检测
        pii = self._detect_pii(text)

        # 2. Prompt Injection 检测
        injection = self._detect_injection(text)

        # 3. 敏感词检测
        sensitive = self._detect_sensitive(text)

        # 注入攻击 → 直接拦截
        if injection:
            return GuardrailResult(
                passed=False,
                pii_detected=pii,
                injection_detected=True,
                sensitive_words=sensitive,
                blocked=True,
                reason="检测到 Prompt Injection 攻击",
            )

        # 严重敏感词 → 拦截
        if sensitive:
            return GuardrailResult(
                passed=False,
                pii_detected=pii,
                injection_detected=False,
                sensitive_words=sensitive,
                blocked=True,
                reason=f"检测到敏感内容: {sensitive}",
            )

        # PII 仅警告，不拦截（输入阶段允许）
        return GuardrailResult(
            passed=True,
            pii_detected=pii,
            injection_detected=False,
            sensitive_words=[],
            blocked=False,
        )

    def check_output(self, text: str) -> GuardrailResult:
        """
        检查 Agent 输出的安全性。

        Args:
            text: Agent 输出文本

        Returns:
            GuardrailResult
        """
        if not text:
            return GuardrailResult(passed=True)

        # 1. 内部错误泄露检查
        leaked = self._detect_internal_leak(text)
        if leaked:
            return GuardrailResult(
                passed=False,
                pii_detected=[],
                injection_detected=False,
                sensitive_words=[],
                blocked=True,
                reason=f"检测到内部信息泄露: {leaked}",
            )

        # 2. PII 未脱敏检查
        pii = self._detect_pii(text)
        if pii:
            return GuardrailResult(
                passed=False,
                pii_detected=pii,
                injection_detected=False,
                sensitive_words=[],
                blocked=True,
                reason=f"输出包含未脱敏的个人信息: {pii}",
            )

        return GuardrailResult(passed=True)

    # ── 检测方法 ──

    def _detect_pii(self, text: str) -> list[str]:
        """检测 PII，返回匹配到的类型列表"""
        found: list[str] = []
        for pii_type, pattern in self._PII_PATTERNS.items():
            if pattern.search(text):
                found.append(pii_type)
        return found

    def _detect_injection(self, text: str) -> bool:
        """检测 Prompt Injection 攻击"""
        lower = text.lower()
        return any(pattern in lower for pattern in self._INJECTION_PATTERNS)

    def _detect_sensitive(self, text: str) -> list[str]:
        """检测敏感词"""
        return [w for w in self._SENSITIVE_WORDS if w in text]

    def _detect_internal_leak(self, text: str) -> Optional[str]:
        """检测输出中的内部信息泄露"""
        leak_patterns = {
            "Traceback (most recent call last)": "内部异常 traceback",
            "API_KEY": "API 密钥",
            "SECRET": "密钥信息",
            "SystemMessage": "系统 Prompt",
        }
        for pattern, desc in leak_patterns.items():
            if pattern in text:
                return desc
        return None
