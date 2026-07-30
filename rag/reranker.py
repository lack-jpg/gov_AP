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
        self._model = None  # TODO: FlagEmbedding FlagReranker

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

        if self._model is not None:
            return await self._model_rerank(query, documents, top_k)

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

        TODO: 接入 FlagEmbedding
        pairs = [[query, doc["content"]] for doc in documents]
        scores = self._model.compute_score(pairs)
        """
        return documents[:top_k]

    def load_model(self, model_name: Optional[str] = None, model_path: Optional[str] = None) -> None:
        """加载 Reranker 模型"""
        if model_name:
            self._model_name = model_name
        if model_path:
            self._model_path = model_path

        load_from = self._model_path or self._model_name
        logger.info("Reranker 模型已加载（stub）: {}", load_from)

    # ── 内部 ──

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
