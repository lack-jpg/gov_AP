"""
governance.callbacks - LangChain callbacks: LLM token usage tracking for AgentOps cost monitoring

Author: le
Date: 2026/8/2
Version: 0.1
Task: Extract LLM token usage from chat model responses and record into the trace

用法:
    from governance.callbacks import TokenUsageCallback

    llm = ChatOpenAI(
        ...,
        callbacks=[TokenUsageCallback()],
    )

每个通过该 LLM 的调用都会在 on_llm_end 中提取 token 用量，
记录为一条 SpanKind.LLM 的 span（关联当前 trace + 当前 Agent）。
"""
from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from governance.trace import (
    get_current_agent_name,
    record_llm_usage,
)
from tools.logger import get_logger

logger = get_logger(__name__)


class TokenUsageCallback(BaseCallbackHandler):
    """
    LangChain Callback — 提取 LLM token 用量并写入 trace。

    AgentOps 成本追踪：每次 LLM 调用（prompt/completion tokens）
    都会以 SpanKind.LLM 记录到当前 trace，归属到正在执行的 Agent。

    Attributes:
        total_input_tokens: 累计输入 token 数
        total_output_tokens: 累计输出 token 数
        call_count: 已捕获的 LLM 调用次数
    """

    def __init__(self) -> None:
        super().__init__()
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

    # ── LLM 结束回调 ──

    def on_llm_end(
        self,
        response,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        LLM 调用完成时提取 token 用量。

        Args:
            response: LLMResult（含 llm_output.token_usage）
            run_id: 运行 ID
            kwargs: 附加参数（metadata 等）
        """
        input_tokens, output_tokens = self._extract_token_usage(response)

        if input_tokens == 0 and output_tokens == 0:
            return

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1

        # 归属到当前 Agent（默认 'llm'）
        agent_name = get_current_agent_name()

        record_llm_usage(
            agent_name=agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        logger.debug(
            "LLM token usage: agent={} in={} out={}",
            agent_name, input_tokens, output_tokens,
        )

    # ── 工具 ──

    @staticmethod
    def _extract_token_usage(response) -> tuple[int, int]:
        """
        从 LLMResult 提取 (input_tokens, output_tokens)。

        兼容多种格式：
        - llm_output["token_usage"]["prompt_tokens"/"completion_tokens"]
        - llm_output["usage"]["input_tokens"/"output_tokens"]
        - generations[0][0].generation_info["token_usage"]
        """
        input_tokens = 0
        output_tokens = 0

        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if isinstance(usage, dict):
                input_tokens = int(
                    usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                )
                output_tokens = int(
                    usage.get("completion_tokens") or usage.get("output_tokens") or 0
                )

        # generation_info fallback
        if input_tokens == 0 and output_tokens == 0:
            try:
                gen_info = response.generations[0][0].generation_info or {}
                usage = gen_info.get("token_usage") or {}
                if isinstance(usage, dict):
                    input_tokens = int(usage.get("prompt_tokens") or 0)
                    output_tokens = int(usage.get("completion_tokens") or 0)
            except (AttributeError, IndexError, TypeError):
                pass

        return input_tokens, output_tokens

    # ── 统计 ──

    def reset(self) -> None:
        """重置累计计数（测试用）"""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0

    @property
    def total_tokens(self) -> int:
        """累计 token 总数"""
        return self.total_input_tokens + self.total_output_tokens


# ============================================================
# Smoke Test — python -m governance.callbacks
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

    print("=== governance.callbacks smoke test ===")

    # ── 无 token 用量的响应 ──
    class EmptyResponse:
        llm_output = None

    cb = TokenUsageCallback()
    cb.on_llm_end(EmptyResponse())
    check("empty response ignored", (cb.call_count, cb.total_tokens), (0, 0))

    # ── 标准 OpenAI 格式 ──
    class OpenAIResponse:
        llm_output = {
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
            }
        }

    cb2 = TokenUsageCallback()
    cb2.on_llm_end(OpenAIResponse())
    check("openai format input", cb2.total_input_tokens, 120)
    check("openai format output", cb2.total_output_tokens, 80)
    check("call count", cb2.call_count, 1)

    # ── usage 别名格式 ──
    class UsageResponse:
        llm_output = {
            "usage": {
                "input_tokens": 50,
                "output_tokens": 25,
            }
        }

    cb3 = TokenUsageCallback()
    cb3.on_llm_end(UsageResponse())
    check("usage alias input", cb3.total_input_tokens, 50)
    check("usage alias output", cb3.total_output_tokens, 25)

    # ── generation_info fallback ──
    class GenInfo:
        generation_info = {"token_usage": {"prompt_tokens": 30, "completion_tokens": 10}}

    class Gen:
        def __init__(self):
            self.generation_info = GenInfo().generation_info

    class GenResponse:
        generations = [[Gen()]]

    cb4 = TokenUsageCallback()
    cb4.on_llm_end(GenResponse())
    check("generation_info input", cb4.total_input_tokens, 30)
    check("generation_info output", cb4.total_output_tokens, 10)

    # ── reset ──
    cb2.reset()
    check("reset clears", (cb2.call_count, cb2.total_tokens), (0, 0))

    print(f"\n=== {passed}/{passed + failed} passed, {failed} failed ===")
    if failed > 0:
        raise SystemExit(1)
