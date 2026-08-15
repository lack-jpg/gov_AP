"""
rag.pipeline - 常驻化 RAG 管线：进程级单例 + 懒加载

Author: le
Date: 2026/8/15
Task: P1-2 RAG 组件常驻化 — Embedding / Milvus / BM25 / Reranker 只加载一次，
      后续请求复用同一批模型与语料索引，避免每次请求重复构建。

使用方式:
    pipeline = get_pipeline()
    result = await pipeline.retrieve("开餐馆需要什么手续", top_k=5)
    # {"documents": [...], "mode": "rag"|"bm25"|"empty", "retrieved_count": n}

    # 刷新语料索引（知识库更新后调用）
    await pipeline.reload_corpus()
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Optional

from tools.logger import get_logger

logger = get_logger(__name__)

# 政策语料目录（与 agents/policy/agent.py 的 _POLICY_CORPUS_DIR 保持一致）
POLICY_CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "policies")


class RAGPipeline:
    """
    RAG 管线常驻实例。

    聚合 EmbeddingEngine / HybridRetriever / Reranker，
    首次使用懒加载一次（加锁），Milvus 连接与 BM25 索引只构建一次。
    """

    _instance: Optional["RAGPipeline"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._embedding: Optional[object] = None
        self._retriever: Optional[object] = None
        self._reranker: Optional[object] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    # ── 单例 ──

    @classmethod
    def get(cls) -> "RAGPipeline":
        """获取进程级单例。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 初始化 ──

    async def _ensure_loaded(self) -> None:
        """懒加载：模型与语料只构建一次，加载过程加锁。"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            # 1. 语料（内部为文件读取，量小直接 await）
            corpus = await _load_policy_corpus()
            # 2. 模型加载为阻塞操作，放线程池避免卡事件循环
            await asyncio.to_thread(self._load_components, corpus)
            self._initialized = True
            logger.info(
                "RAG 组件常驻化完成: corpus={} bm25={}",
                len(corpus),
                getattr(self._retriever, "_bm25", None) is not None,
            )

    def _load_components(self, corpus: list[dict]) -> None:
        """加载 Embedding / Retriever / Reranker（同步，在线程池中执行）。"""
        from rag.embedding import EmbeddingEngine
        from rag.retriever import HybridRetriever
        from rag.reranker import Reranker

        self._embedding = EmbeddingEngine()
        self._reranker = Reranker()

        retriever = HybridRetriever()
        # 尝试连接 Milvus（失败则只走 BM25，不阻断）
        try:
            retriever.connect_milvus()
        except Exception as e:  # pragma: no cover - 依赖外部服务
            logger.warning("Milvus 连接失败（仅 BM25）: {}", e)
        if corpus:
            try:
                retriever.set_corpus(corpus)
            except Exception as e:
                logger.warning("BM25 语料构建失败: {}", e)
        self._retriever = retriever

    # ── 公开接口 ──

    async def retrieve(self, query: str, top_k: int = 5) -> dict:
        """
        混合检索 + 重排。

        Args:
            query: 用户查询
            top_k: 返回文档数量

        Returns:
            {
                "documents": [{title, content, score, source, ...}, ...],
                "mode": "rag" | "bm25" | "empty",   # 显式标注检索模式
                "retrieved_count": int,
            }
        """
        await self._ensure_loaded()
        assert self._embedding is not None and self._retriever is not None

        # 1. 向量化（模型不可用返回零向量，retriever 会跳过密集检索）
        query_vec = await self._embedding.encode_query(query)

        # 2. 混合检索（Milvus 密集 + BM25 稀疏 → RRF 融合）
        docs = await self._retriever.hybrid_search(query, query_vec, top_k=top_k * 2)

        # 3. 重排（reranker 不可用保持原顺序）
        if docs and self._reranker is not None:
            try:
                docs = await self._reranker.rerank(query, docs, top_k=top_k)
            except Exception as e:
                logger.warning("Reranker 重排失败，保持原顺序: {}", e)

        milvus_connected = bool(getattr(self._retriever, "_milvus_connected", False))
        mode = "empty"
        if docs:
            mode = "rag" if milvus_connected else "bm25"

        return {
            "documents": docs,
            "mode": mode,
            "retrieved_count": len(docs),
        }

    async def reload_corpus(self) -> int:
        """
        重新加载语料并重建 BM25 索引（知识库更新后调用）。

        Returns:
            语料文档数
        """
        corpus = await _load_policy_corpus()
        if self._retriever is not None and corpus:
            await asyncio.to_thread(self._retriever.set_corpus, corpus)
        logger.info("RAG 语料已刷新: {} docs", len(corpus))
        return len(corpus)

    @property
    def is_initialized(self) -> bool:
        """是否已完成常驻化加载。"""
        return self._initialized


# ============================================================
# 全局单例
# ============================================================

_pipeline: Optional[RAGPipeline] = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> RAGPipeline:
    """
    获取全局 RAGPipeline 单例。

    Returns:
        RAGPipeline 实例
    """
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = RAGPipeline.get()
    return _pipeline


# ============================================================
# 政策语料加载
# ============================================================


async def _load_policy_corpus() -> list[dict]:
    """
    从 data/policies/ 目录加载政策文档语料（供 BM25 检索）。

    目录不存在或为空时返回空列表（RAG 自动降级到纯 LLM）。

    Returns:
        文档列表 [{title, content, source}, ...]
    """
    if not os.path.isdir(POLICY_CORPUS_DIR):
        logger.debug("政策语料目录不存在: {}，跳过 RAG 检索", POLICY_CORPUS_DIR)
        return []

    try:
        from rag.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        docs = await kb.load_documents(POLICY_CORPUS_DIR)
        return docs or []
    except Exception as e:
        logger.warning("政策语料加载失败: {}", e)
        return []
