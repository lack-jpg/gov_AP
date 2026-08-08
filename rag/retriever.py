"""
rag.retriever - Hybrid Retriever: Milvus vector search + BM25 sparse retrieval

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement hybrid retrieval combining dense and sparse search
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from tools.logger import get_logger

logger = get_logger(__name__)

# 默认 Milvus 集合名（与 knowledge_base.index_documents 保持一致）
DEFAULT_COLLECTION = "gov_policy"


class HybridRetriever:
    """
    混合检索器 — Milvus 密集向量检索 + BM25 稀疏关键词检索。

    检索流程:
        1. Query → EmbeddingEngine.encode_query → 向量
        2. 向量 → Milvus.search → Top-K 密集结果
        3. Query → BM25 → Top-K 稀疏结果
        4. RRF (Reciprocal Rank Fusion) 融合排序 → 最终 Top-K

    Milvus 或 BM25 不可用时自动降级（返回空列表），由调用方处理。

    使用方式:
        retriever = HybridRetriever()
        docs = await retriever.hybrid_search(query, query_embedding, top_k=5)
    """

    def __init__(self, milvus_host: str = "", milvus_port: int = 0):
        # 读配置（MILVUS_HOST / MILVUS_PORT，默认 localhost:19532），空值用默认
        try:
            from backend.config import get_settings
            settings = get_settings()
            self._milvus_host = milvus_host or settings.milvus_host or "localhost"
            self._milvus_port = milvus_port or int(settings.milvus_port) or 19530
        except Exception:
            self._milvus_host = milvus_host or "localhost"
            self._milvus_port = milvus_port or 19530
        self._milvus_client = None  # pymilvus Collection
        self._milvus_connected = False
        self._bm25 = None  # _SimpleBM25
        self._docs: list[dict] = []  # BM25 语料

    def set_corpus(self, documents: list[dict]) -> None:
        """
        设置 BM25 检索语料（从 KnowledgeBase 加载）。

        Args:
            documents: 文档列表 [{title, content, source, ...}]
        """
        self._docs = list(documents)
        try:
            from rag.bm25 import SimpleBM25
            self._bm25 = SimpleBM25(
                [d.get("content", "") for d in documents]
            )
            logger.info("BM25 索引已构建: {} docs", len(documents))
        except Exception as e:
            logger.warning("BM25 构建失败: {}", e)
            self._bm25 = None

    def connect_milvus(self, collection: str = DEFAULT_COLLECTION) -> bool:
        """
        连接 Milvus 并绑定集合。

        Args:
            collection: Milvus 集合名

        Returns:
            是否连接成功
        """
        try:
            from pymilvus import connections, Collection
            connections.connect(
                alias="default",
                host=self._milvus_host,
                port=str(self._milvus_port),
            )
            self._milvus_client = Collection(collection)
            self._milvus_connected = True
            logger.info("Milvus 已连接: {}:{} collection={}", self._milvus_host, self._milvus_port, collection)
            return True
        except Exception as e:
            logger.warning("Milvus 连接失败（将只使用 BM25）: {}", e)
            self._milvus_connected = False
            return False

    async def hybrid_search(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        top_k: int = 5,
        alpha: float = 0.5,
    ) -> list[dict]:
        """
        混合检索（密集 + 稀疏 → RRF 融合）。

        Args:
            query: 原始查询文本
            query_embedding: 查询向量（不传则只做 BM25）
            top_k: 返回数量
            alpha: 密集检索权重（0=纯BM25, 1=纯密集）

        Returns:
            文档列表 [{title, content, score, source}, ...]
        """
        dense_results: list[dict] = []
        sparse_results: list[dict] = []

        # 1. 密集检索
        if query_embedding is not None and self._milvus_connected and self._milvus_client is not None:
            dense_results = await self._dense_search(query_embedding, top_k * 2)

        # 2. 稀疏检索（BM25）
        sparse_results = await self._sparse_search(query, top_k * 2)

        # 3. RRF 融合
        if dense_results and sparse_results:
            return self._rrf_fusion(dense_results, sparse_results, top_k, alpha)
        elif dense_results:
            return dense_results[:top_k]
        else:
            return sparse_results[:top_k]

    async def dense_search(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> list[dict]:
        """仅密集检索"""
        return await self._dense_search(query_embedding, top_k)

    async def sparse_search(self, query: str, top_k: int = 5) -> list[dict]:
        """仅 BM25 稀疏检索"""
        return await self._sparse_search(query, top_k)

    # ── 内部 ──

    async def _dense_search(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> list[dict]:
        """
        Milvus 密集向量检索。
        """
        try:
            import asyncio
            from pymilvus import Collection

            def _search() -> list[dict]:
                nprobe = 10
                try:
                    from backend.config import get_settings
                    nprobe = int(get_settings().milvus_search_nprobe) or 10
                except Exception:
                    pass
                results = self._milvus_client.search(
                    data=[query_embedding.tolist()],
                    anns_field="embedding",
                    param={"metric_type": "COSINE", "params": {"nprobe": nprobe}},
                    limit=top_k,
                    output_fields=["title", "content", "source"],
                )
                docs = []
                for hits in results:
                    for hit in hits:
                        entity = hit.entity
                        docs.append({
                            "title": entity.get("title", ""),
                            "content": entity.get("content", ""),
                            "source": entity.get("source", ""),
                            "score": float(hit.score),
                        })
                return docs

            docs = await asyncio.to_thread(_search)
            logger.debug("Milvus 返回 {} 条结果", len(docs))
            return docs
        except Exception as e:
            logger.warning("Milvus 检索失败: {}", e)
            return []

    async def _sparse_search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        BM25 稀疏检索。
        """
        if self._bm25 is None:
            logger.debug("BM25 未构建索引，跳过稀疏检索")
            return []

        try:
            import asyncio
            def _score() -> list[dict]:
                scores = self._bm25.score(query)
                # 合并文档信息
                ranked = []
                for doc, score in zip(self._docs, scores):
                    if score > 0:
                        ranked.append({
                            **doc,
                            "score": float(score),
                        })
                ranked.sort(key=lambda d: d["score"], reverse=True)
                return ranked[:top_k]

            results = await asyncio.to_thread(_score)
            logger.debug("BM25 返回 {} 条结果", len(results))
            return results
        except Exception as e:
            logger.warning("BM25 检索失败: {}", e)
            return []

    @staticmethod
    def _rrf_fusion(
        dense: list[dict],
        sparse: list[dict],
        top_k: int,
        alpha: float = 0.5,
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion — 融合密集和稀疏结果。

        RRF 公式: score(d) = Σ 1/(k + rank_i(d))
        其中 rank_i(d) 是文档 d 在第 i 个排序列表中的排名。

        Args:
            dense: 密集检索结果
            sparse: 稀疏检索结果
            top_k: 返回数量
            alpha: 密集权重
            k: RRF 平滑参数
        """
        scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}

        # 密集排名贡献
        for rank, doc in enumerate(dense):
            doc_id = doc.get("title", str(rank))
            scores[doc_id] = alpha / (k + rank + 1)
            doc_map[doc_id] = doc

        # 稀疏排名贡献
        for rank, doc in enumerate(sparse):
            doc_id = doc.get("title", str(rank))
            scores[doc_id] = scores.get(doc_id, 0) + (1 - alpha) / (k + rank + 1)
            doc_map[doc_id] = doc

        # 按融合分数降序排列
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        result = [doc_map[doc_id] for doc_id in sorted_ids]

        # 标注融合分数
        for doc_id, doc in zip(sorted_ids, result):
            doc["score"] = scores[doc_id]

        return result
