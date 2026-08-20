"""
test_log_masking - P2-3 日志脱敏测试

验证：
1. _mask_pii_filter 对任意 message 应用 mask_pii（sink 级统一脱敏）；
2. log_mcp_call 的参数/错误信息先脱敏再输出（sink 过滤之外的防御）；
3. 异常输入不导致过滤崩溃。
"""
from __future__ import annotations

import io

from loguru import logger as _loguru_logger

from tools.logger import _mask_pii_filter, log_mcp_call


class TestMaskPiiFilter:
    def test_masks_phone(self):
        record = {"message": "用户手机13812341234 已提交"}
        ok = _mask_pii_filter(record)
        assert ok is True
        assert "138****1234" in record["message"]
        assert "13812341234" not in record["message"]

    def test_masks_id_card_and_email(self):
        record = {"message": "身份证110101199001011234 邮箱user@domain.com"}
        _mask_pii_filter(record)
        assert "110***********1234" in record["message"]
        assert "u***@domain.com" in record["message"]
        assert "110101199001011234" not in record["message"]

    def test_bank_card_masked(self):
        record = {"message": "卡号6222021234567890123"}
        _mask_pii_filter(record)
        assert "6222****0123" in record["message"]
        assert "6222021234567890123" not in record["message"]

    def test_non_pii_message_unchanged(self):
        record = {"message": "普通日志内容，无敏感信息"}
        _mask_pii_filter(record)
        assert record["message"] == "普通日志内容，无敏感信息"

    def test_malformed_record_returns_true(self):
        # 异常不应导致过滤失败（sink 崩溃保护）
        ok = _mask_pii_filter({"no_message_key": True})
        assert ok is True


class TestLogMcpCallMasking:
    def test_args_and_error_masked(self):
        buf = io.StringIO()
        sink_id = _loguru_logger.add(
            buf,
            format="{message}",
            filter=lambda r: "MCP调用" in r["message"],
        )
        try:
            log_mcp_call(
                server_name="policy_server",
                tool_name="search_policy",
                input_args={
                    "id_card": "110101199001011234",
                    "phone": "13812341234",
                },
                error="phone 13812341234 invalid",
                status="failed",
                latency_ms=12.3,
            )
        finally:
            _loguru_logger.remove(sink_id)

        text = buf.getvalue()
        assert "MCP调用" in text
        assert "110***********1234" in text
        assert "138****1234" in text
        assert "110101199001011234" not in text
        assert "13812341234" not in text

    def test_plain_args_passthrough(self):
        buf = io.StringIO()
        sink_id = _loguru_logger.add(
            buf,
            format="{message}",
            filter=lambda r: "MCP调用" in r["message"],
        )
        try:
            log_mcp_call(
                server_name="material_server",
                tool_name="extract_entity",
                input_args={"doc_id": "doc-001"},
            )
        finally:
            _loguru_logger.remove(sink_id)

        text = buf.getvalue()
        assert "doc-001" in text
