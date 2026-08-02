"""
rag.reranker - BGE Reranker: re-rank retrieved documents for improved relevance

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement BGE reranker for search result re-ranking
"""
from __future__ import annotations

import os
from typing import Optional

from tools.logger import get_logger

logger = get_logger(__name__)


class Reranker:
    """
    BGE Reranker — 对检索结果进行精排。

    模型: BAAI/bge-reranker-v2-m3（多语言 Cross-Encoder）
    优先从本地 models/reranker/ 加载，不存在则从 HuggingFace 下载。

    使用方式:
        reranker = Reranker()
        ranked = await reranker.rerank(query, docs, top_k=3)
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"

    def __init__(self, model_name: Optional[str] = None, model_path: Optional[str] = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model_path = model_path or self._resolve_path()
        self._model = None  # FlagEmbedding FlagReranker

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 3,
    ) -> list[dict]:
        """
        对检索结果重新排序。

        Args:
            query: 原始查询
            documents: 文档列表 [{title, content, score}, ...]
            top_k: 返回数量

        Returns:
            按 relevance_score 降序排列的文档列表
        """
        if not documents:
            return []

        try:
            self._ensure_model()
        except Exception as e:
            logger.warning("Reranker 模型不可用，保持原顺序: {}", e)

        if self._model is not None:
            try:
                return await self._model_rerank(query, documents, top_k)
            except Exception as e:
                logger.warning("Reranker 重排失败，回退原顺序: {}", e)

        # Stub: 保持原顺序，标注分数
        logger.debug("rerank (stub): {} docs → top_k={}", len(documents), top_k)
        result = []
        for i, doc in enumerate(documents[:top_k]):
            doc["relevance_score"] = max(0.5, 0.95 - i * 0.1)
            result.append(doc)
        return result

    async def _model_rerank(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """
        使用 BGE Reranker 模型重排序。

        pairs = [[query, doc["content"]] for doc in documents]
        scores = self._model.compute_score(pairs)
        """
        import asyncio

        pairs = [[query, doc.get("content", "")] for doc in documents]

        def _compute() -> list[float]:
            raw = self._model.compute_score(pairs)
            # FlagReranker 返回 float 或 list[float]
            if isinstance(raw, (int, float)):
                return [float(raw)] * len(pairs)
            return [float(s) for s in raw]

        scores = await asyncio.to_thread(_compute)

        # 按分数降序排列
        ranked = sorted(
            zip(documents, scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        result = []
        for doc, score in ranked:
            doc["relevance_score"] = float(score)
            result.append(doc)
        return result

    def load_model(self, model_name: Optional[str] = None, model_path: Optional[str] = None) -> None:
        """加载 Reranker 模型"""
        if model_name:
            self._model_name = model_name
        if model_path:
            self._model_path = model_path

        load_from = self._model_path or self._model_name
        try:
            from FlagEmbedding import FlagReranker
            self._model = FlagReranker(load_from, use_fp16=False)
            logger.info("Reranker 模型已加载: {}", load_from)
        except Exception as e:
            logger.warning("Reranker 模型加载失败（将使用原顺序兜底）: {}", e)
            self._model = None

    # ── 内部 ──

    def _ensure_model(self) -> None:
        """确保模型已加载（惰性加载）"""
        if self._model is None:
            self.load_model()

    @staticmethod
    def _resolve_path() -> Optional[str]:
        """从环境变量解析本地模型路径"""
        path = os.environ.get("RERANKER_MODEL_PATH", "models/reranker/bge-reranker-v2-m3")
        if os.path.isdir(path):
            return path
        return None

    @property
    def model_path(self) -> Optional[str]:
        """本地模型路径"""
        return self._model_path
