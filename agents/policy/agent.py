"""
policy.agent - Policy Agent core: hybrid RAG retrieval + LLM generation

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Policy Agent with Milvus + BM25 + Reranker pipeline
"""
from __future__ import annotations

import os
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.policy.schema import PolicyResult, PolicyEvidence
from agents.policy.prompts import POLICY_RAG_PROMPT
from prompts.registry import get_registry
from orchestration.langgraph.state import AgentState
from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# PolicyAgent
# ============================================================


class PolicyAgent:
    """
    Policy Agent — 政策知识检索。

    RAG 管线:
        Query → Embedding → Milvus 密集检索 + BM25 稀疏检索
        → 融合排序 → Reranker 重排序 → LLM 生成带 evidence 的答案

    当前实现: 模板回答（RAG 管线待接入）
    TODO: 接入 rag/ 模块的完整 RAG 管线

    使用方式:
        agent = PolicyAgent(llm=llm)
        result = await agent.search("开餐馆需要什么手续")
        # PolicyResult(answer="...", evidence=[...])

    LangGraph 集成:
        result = await agent.search(state["user_query"])
        state["policy_result"] = result.model_dump()
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Args:
            llm: LLM 实例，用于生成回答（不传则用模板）
        """
        self._llm = llm

    # ── 公开接口 ──

    async def search(self, query: str, top_k: int = 5) -> PolicyResult:
        """
        执行政策检索。

        三级策略（按优先级）:
        1. RAG 管线（Embedding → Milvus/BM25 混合检索 → Reranker → LLM 生成带证据回答）
        2. LLM 生成（RAG 不可用时）
        3. 模板回答（无 LLM 时）

        Args:
            query: 用户查询
            top_k: 返回文档数量

        Returns:
            PolicyResult
        """
        # 1. RAG 管线（真实检索增强）
        rag_result = await self._try_rag(query, top_k)
        if rag_result is not None:
            return rag_result

        # 2. LLM 生成（无 RAG 检索）
        if self._llm is not None:
            return await self._llm_search(query, top_k)

        # 3. 模板兜底
        return self._template_search(query)

    async def _try_rag(self, query: str, top_k: int) -> Optional[PolicyResult]:
        """
        尝试通过 RAG 管线检索并生成回答。

        若 RAG 组件不可用（模型未加载 / Milvus 未连接 / 无语料），
        返回 None 由调用方降级。

        Args:
            query: 用户查询
            top_k: 返回文档数量

        Returns:
            PolicyResult 或 None（不可用时）
        """
        if self._llm is None:
            return None

        try:
            # 惰性加载 RAG 组件，避免启动即失败
            from rag.embedding import EmbeddingEngine
            from rag.retriever import HybridRetriever
            from rag.reranker import Reranker
            from rag.generator import Generator

            # 1. Embedding
            engine = EmbeddingEngine()
            query_vec = await engine.encode_query(query)

            # 2. 混合检索（Milvus + BM25）
            retriever = HybridRetriever()
            # 尝试连接 Milvus（失败则只走 BM25）
            retriever.connect_milvus()
            # 尝试加载本地语料（data/policies/）
            corpus = _load_policy_corpus()
            if corpus:
                retriever.set_corpus(corpus)

            docs = await retriever.hybrid_search(query, query_vec, top_k=top_k * 2)

            # 3. 重排序
            reranker = Reranker()
            if docs:
                docs = await reranker.rerank(query, docs, top_k=top_k)

            if not docs:
                logger.info("RAG 检索无结果，降级到 LLM 生成")
                return None

            # 4. LLM 生成（带证据）
            generator = Generator(llm=self._llm)
            gen_result = await generator.generate(query, docs)
            answer = gen_result.get("answer", "")

            evidence = [
                PolicyEvidence(
                    source=doc.get("source", doc.get("title", "政策文档")),
                    excerpt=doc.get("content", "")[:200],
                    relevance_score=float(doc.get("relevance_score", doc.get("score", 0.5))),
                )
                for doc in docs[:3]
            ]

            logger.info("RAG 管线完成: {} 条证据, confidence={:.2f}", len(evidence), 0.85)
            return PolicyResult(
                answer=answer,
                evidence=evidence,
                confidence=0.85,
                retrieved_count=len(docs),
            )
        except Exception as e:
            logger.warning("RAG 管线不可用，降级到 LLM 生成: {}", e)
            return None

    async def search_with_intent(
        self, query: str, intent: str, top_k: int = 5
    ) -> PolicyResult:
        """
        带意图标签的增强检索（意图标签帮助缩小检索范围）。

        Args:
            query: 用户查询
            intent: 意图标签
            top_k: 返回文档数量

        Returns:
            PolicyResult
        """
        # 用意图丰富 query
        enriched = f"{query} 意图:{intent}"
        return await self.search(enriched, top_k)

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState
        """
        user_query = state.get("user_query", "")
        intent = state.get("intent", "")

        result = await self.search_with_intent(user_query, intent)
        state["policy_result"] = result.model_dump()
        return state

    # ── LLM 检索 ──

    async def _llm_search(self, query: str, top_k: int) -> PolicyResult:
        """使用 LLM 生成回答（无 RAG 库时作为兜底）"""
        assert self._llm is not None

        # Prompt Registry 优先，硬编码常量 fallback
        try:
            registry = get_registry()
            system_content = registry.render("POLICY_RAG_PROMPT", user_query=query, context="")
        except Exception:
            system_content = POLICY_RAG_PROMPT

        system_msg = SystemMessage(content=system_content)
        user_msg = HumanMessage(content=f"查询: {query}\n请基于政策知识回答。")

        response = await self._llm.ainvoke([system_msg, user_msg])
        answer = self._extract_text(response)

        return PolicyResult(
            answer=answer,
            evidence=[],
            confidence=0.7,  # 无 RAG 验证时置信度较低
            retrieved_count=0,
        )

    # ── 模板兜底 ──

    def _template_search(self, query: str) -> PolicyResult:
        """基于模板的静态回答（无 LLM 时兜底）"""
        answer = _get_template_answer(query)
        return PolicyResult(
            answer=answer,
            evidence=[],
            confidence=0.5,
            retrieved_count=0,
        )

    # ── 工具 ──

    @staticmethod
    def _extract_text(response) -> str:
        if hasattr(response, "content"):
            return response.content
        return str(response)


# ============================================================
# 政策语料加载（RAG 检索用）
# ============================================================

_POLICY_CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "policies")


def _load_policy_corpus() -> list[dict]:
    """
    从 data/policies/ 目录加载政策文档语料（用于 BM25 检索）。

    若目录不存在或为空，返回空列表（RAG 自动降级到纯 LLM）。

    Returns:
        文档列表 [{title, content, source}, ...]
    """
    import os

    if not os.path.isdir(_POLICY_CORPUS_DIR):
        logger.debug("政策语料目录不存在: {}，跳过 RAG 检索", _POLICY_CORPUS_DIR)
        return []

    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        docs = kb.load_documents(_POLICY_CORPUS_DIR)
        return docs
    except Exception as e:
        logger.warning("政策语料加载失败: {}", e)
        return []


# ============================================================
# 模板回答（兜底）
# ============================================================


def _get_template_answer(query: str) -> str:
    """关键词匹配的静态政策回答"""
    q = query.lower()

    if any(kw in q for kw in ("餐馆", "餐饮", "饭店", "餐厅", "食品")):
        return (
            "开办餐馆需要以下手续：\n"
            "1. **营业执照** — 到当地市场监管局办理\n"
            "2. **食品经营许可证** — 到食品药品监督管理部门办理\n"
            "3. **消防安全检查合格证** — 到消防部门办理\n"
            "4. **环保审批** — 根据当地环保要求\n\n"
            "基本材料：身份证、经营场所证明、从业人员健康证、食品安全管理制度。"
        )
    elif any(kw in q for kw in ("公司", "企业", "注册", "执照")):
        return (
            "企业注册流程：\n"
            "1. 名称预先核准\n"
            "2. 提交设立登记申请\n"
            "3. 领取营业执照\n\n"
            "所需材料：法人身份证、经营场所证明、公司章程、股东决议。"
        )
    elif any(kw in q for kw in ("公积金", "住房")):
        return (
            "公积金查询方式：\n"
            "1. 登录当地住房公积金管理中心官网\n"
            "2. 拨打 12329 住房公积金热线\n"
            "3. 持身份证到服务大厅自助终端查询"
        )
    elif any(kw in q for kw in ("房产", "不动产", "房屋", "产权")):
        return (
            "不动产登记流程：\n"
            "1. 准备材料（身份证、购房合同、完税证明）\n"
            "2. 到不动产登记中心提交申请\n"
            "3. 缴纳登记费\n"
            "4. 领取不动产权证书"
        )
    else:
        return (
            "根据您的问题，建议准备以下材料：\n"
            "1. 本人有效身份证件\n"
            "2. 相关申请表（可在政务大厅领取或网上下载）\n"
            "3. 根据具体事项可能需要补充材料\n\n"
            "如需详细政策信息，请说明具体办理事项。"
        )
