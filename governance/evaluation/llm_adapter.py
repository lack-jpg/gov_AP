"""
governance.evaluation.llm_adapter - LLM judge adapter for evaluation metrics

将 LangChain BaseChatModel 转换为评估指标需要的 (prompt) -> str 回调。

Author: le
Date: 2026/8/4
"""
from __future__ import annotations

from typing import Any, Callable

from tools.logger import get_logger

logger = get_logger(__name__)


def create_llm_judge(llm: Any) -> Callable[[str], str]:
    """
    将 LLM 实例封装为同步 (prompt) -> score_string 回调。

    评估指标 (metrics.py) 期望 llm_call 签名为:
        def llm_call(prompt: str) -> str:
            # 返回 float 字符串，如 "0.85"

    Args:
        llm: LangChain BaseChatModel 实例（已配置 API key/model）

    Returns:
        (prompt: str) -> str 回调

    Usage:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="deepseek-v4-flash", ...)
        judge = create_llm_judge(llm)
        score = judge("请评估以下回答的忠实度...")  # → "0.85"
    """
    def judge(prompt: str) -> str:
        try:
            response = llm.invoke(prompt)
            content: str = response.content if hasattr(response, "content") else str(response)
            return content.strip()
        except Exception as e:
            logger.warning("LLM judge 调用失败，返回 0.0: {}", e)
            return "0.0"

    return judge


def create_llm_judge_async(llm: Any) -> Callable[[str], str]:
    """
    异步版本：使用 ainvoke。

    注意：metrics.py 中的 llm_call 是同步调用，但可以在 async 上下文中
    asyncio.run() 包装。此函数返回的 judge 内部使用 asyncio.run()。
    """
    import asyncio

    def judge(prompt: str) -> str:
        async def _call() -> str:
            try:
                response = await llm.ainvoke(prompt)
                content: str = response.content if hasattr(response, "content") else str(response)
                return content.strip()
            except Exception as e:
                logger.warning("LLM judge 异步调用失败，返回 0.0: {}", e)
                return "0.0"

        try:
            _ = asyncio.get_running_loop()
            # 已有运行中的 loop → 创建新 loop
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(_call())
            finally:
                new_loop.close()
        except RuntimeError:
            return asyncio.run(_call())

    return judge
