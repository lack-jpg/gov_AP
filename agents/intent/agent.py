"""
intent.agent - Intent Agent core: natural language -> business intent label

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement BERT-based intent classification with LLM fallback
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.intent.classifier import IntentClassifier
from agents.intent.prompts import INTENT_CLASSIFICATION_PROMPT, FEW_SHOT_EXAMPLES
from prompts.registry import get_registry
from agents.intent.schema import IntentResult
from orchestration.langgraph.state import AgentState
from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# IntentAgent
# ============================================================


class IntentAgent:
    """
    Intent Agent — 用户意图识别。

    三级分类策略（按优先级）：
    1. BERT 分类器（fine-tuned 模型，高置信度直接返回）
    2. 关键词匹配（无模型时兜底）
    3. LLM fallback（BERT 置信度低时）

    使用方式:
        agent = IntentAgent(classifier=classifier, llm=llm)
        result = await agent.classify("我要开一家餐馆")
        # IntentResult(label="restaurant_license", confidence=0.92, source="bert")

    LangGraph 集成:
        # 在 intent_node 中调用
        result = await agent.classify(state["user_query"])
        state = set_intent(state, result)
        return state
    """

    def __init__(
        self,
        classifier: Optional[IntentClassifier] = None,
        llm: Optional[BaseChatModel] = None,
        bert_threshold: float = 0.7,
    ):
        """
        Args:
            classifier: 意图分类器（不传则自动创建关键词匹配版）
            llm: LLM 实例（用于置信度低时的 fallback）
            bert_threshold: BERT 置信度阈值，低于此值触发 LLM fallback
        """
        self._classifier = classifier or IntentClassifier()
        self._llm = llm
        self._bert_threshold = bert_threshold

    # ── 公开接口 ──

    async def classify(self, text: str) -> IntentResult:
        """
        对用户输入进行意图分类。

        分类链: BERT → 关键词 → LLM

        Args:
            text: 用户原始输入

        Returns:
            IntentResult
        """
        # 1. BERT / 关键词分类
        result = await self._classifier.classify(text)

        # 2. 如果 BERT 置信度足够高，直接返回
        if result.confidence >= self._bert_threshold:
            logger.info(
                "意图分类: {} → {} (confidence={:.2f}, source={})",
                text[:40], result.label, result.confidence, result.source,
            )
            return result

        # 3. LLM fallback
        if self._llm is not None:
            logger.info(
                "BERT 置信度不足 ({:.2f} < {:.2f})，触发 LLM fallback",
                result.confidence, self._bert_threshold,
            )
            return await self._llm_classify(text, result)

        logger.warning("无 LLM，使用低置信度结果: {} ({:.2f})", result.label, result.confidence)
        return result

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口 — 处理完整 State。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState（intent 字段已设置）
        """
        user_query = state.get("user_query", "")
        result = await self.classify(user_query)

        from orchestration.langgraph.state import set_intent
        return set_intent(state, result)

    # ── LLM Fallback ──

    async def _llm_classify(
        self,
        text: str,
        fallback_result: IntentResult,
    ) -> IntentResult:
        """使用 LLM 进行意图分类"""
        assert self._llm is not None

        # Prompt Registry 优先，硬编码常量 fallback
        try:
            registry = get_registry()
            prompt = registry.render("INTENT_CLASSIFIER_PROMPT", user_query=text)
        except Exception:
            prompt = INTENT_CLASSIFICATION_PROMPT.format(user_query=text) + "\n" + FEW_SHOT_EXAMPLES

        system_msg = SystemMessage(content=prompt)
        user_msg = HumanMessage(content=text)

        response = await self._llm.ainvoke([system_msg, user_msg])
        raw = self._extract_text(response).strip().lower()

        # 尝试匹配已知标签
        from agents.intent.schema import INTENT_LABELS
        for lbl in INTENT_LABELS:
            if lbl.label_id == raw:
                return IntentResult(
                    label=lbl.label_id,
                    label_name=lbl.label_name,
                    confidence=0.88,
                    source="llm",
                )

        # LLM 输出了未知标签 → 用 fallback
        logger.warning("LLM 输出了未知标签: {}，使用 fallback: {}", raw, fallback_result.label)
        return IntentResult(
            label=fallback_result.label,
            label_name=fallback_result.label_name,
            confidence=0.6,
            source="llm",
        )

    # ── 工具 ──

    @staticmethod
    def _extract_text(response) -> str:
        """从 LLM 响应提取文本"""
        if hasattr(response, "content"):
            return response.content
        return str(response)
