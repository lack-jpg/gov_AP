"""
rag.embedding - Embedding module: BGE embedding model for document and query vectorization

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement embedding generation using BGE model
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from tools.logger import get_logger

logger = get_logger(__name__)


class EmbeddingEngine:
    """
    文本向量化引擎。

    默认使用 BGE-large-zh-v1.5（中文语义向量）。
    TODO: 接入 sentence-transformers 进行真实推理。

    使用方式:
        engine = EmbeddingEngine()
        vec = await engine.encode_query("开餐馆需要什么手续")
        # ndarray shape=(1024,)
    """

    DEFAULT_MODEL = "BAAI/bge-large-zh-v1.5"
    DEFAULT_DIM = 1024

    def __init__(self, model_name: Optional[str] = None):
        """
        Args:
            model_name: 模型名称，默认 BAAI/bge-large-zh-v1.5
        """
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model = None  # TODO: sentence-transformers model
        self._dim = self.DEFAULT_DIM

    async def encode_query(self, text: str) -> np.ndarray:
        """
        将查询文本向量化。

        BGE 模型对 query 使用特殊指令前缀: "为这个句子生成表示以用于检索相关文章："

        Args:
            text: 查询文本

        Returns:
            向量 (ndarray, shape=(dim,))
        """
        if self._model is not None:
            # TODO: embedding = self._model.encode(text, prompt=QUERY_INSTRUCTION)
            pass

        # Stub: 返回零向量（占位）
        logger.debug("encode_query (stub): {}...", text[:50])
        return np.zeros(self._dim, dtype=np.float32)

    async def encode_documents(self, texts: list[str]) -> np.ndarray:
        """
        批量将文档向量化。

        Args:
            texts: 文档文本列表

        Returns:
            向量矩阵 (ndarray, shape=(len(texts), dim))
        """
        if self._model is not None:
            # TODO: return self._model.encode(texts, normalize_embeddings=True)
            pass

        logger.debug("encode_documents (stub): {} docs", len(texts))
        return np.zeros((len(texts), self._dim), dtype=np.float32)

    def load_model(self, model_name: Optional[str] = None) -> None:
        """
        加载 embedding 模型到内存。

        Args:
            model_name: 模型名称，不传则用默认
        """
        if model_name:
            self._model_name = model_name
        # TODO: self._model = SentenceTransformer(self._model_name)
        logger.info("Embedding 模型已加载（stub）: {}", self._model_name)

    @property
    def dim(self) -> int:
        """向量维度"""
        return self._dim

    @property
    def model_name(self) -> str:
        """当前模型名称"""
        return self._model_name
