"""
rag.embedding - Embedding module: BGE embedding model for document and query vectorization

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement embedding generation using BGE model
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

from tools.logger import get_logger

logger = get_logger(__name__)


# BGE 查询指令前缀（BGE 系列模型要求 query 与 document 使用不同编码方式）
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class EmbeddingEngine:
    """
    文本向量化引擎。

    默认使用 BGE-large-zh-v1.5（中文语义向量）。
    优先从本地 models/embedding/ 加载，不存在则从 HuggingFace 下载。

    使用方式:
        engine = EmbeddingEngine()
        vec = await engine.encode_query("开餐馆需要什么手续")
        # ndarray shape=(1024,)
    """

    DEFAULT_MODEL = "BAAI/bge-large-zh-v1.5"
    DEFAULT_DIM = 1024

    def __init__(self, model_name: Optional[str] = None, model_path: Optional[str] = None):
        """
        Args:
            model_name: 模型名称，默认 BAAI/bge-large-zh-v1.5
            model_path: 本地模型路径，存在则从本地加载（优先于 model_name）
        """
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model_path = model_path or self._resolve_path()
        self._model = None  # sentence-transformers SentenceTransformer
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
        try:
            self._ensure_model()
        except Exception as e:
            logger.warning("Embedding 模型不可用，返回零向量: {}", e)
            return np.zeros(self._dim, dtype=np.float32)

        try:
            # 使用同步 encode，通过 asyncio.to_thread 避免阻塞事件循环
            import asyncio
            vec = await asyncio.to_thread(
                self._model.encode,
                text,
                prompt=QUERY_INSTRUCTION,
                normalize_embeddings=True,
            )
            return np.asarray(vec, dtype=np.float32)
        except Exception as e:
            logger.warning("encode_query 失败，返回零向量: {}", e)
            return np.zeros(self._dim, dtype=np.float32)

    async def encode_documents(self, texts: list[str]) -> np.ndarray:
        """
        批量将文档向量化。

        Args:
            texts: 文档文本列表

        Returns:
            向量矩阵 (ndarray, shape=(len(texts), dim))
        """
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        try:
            self._ensure_model()
        except Exception as e:
            logger.warning("Embedding 模型不可用，返回零矩阵: {}", e)
            return np.zeros((len(texts), self._dim), dtype=np.float32)

        try:
            import asyncio
            matrix = await asyncio.to_thread(
                self._model.encode,
                texts,
                normalize_embeddings=True,
            )
            return np.asarray(matrix, dtype=np.float32)
        except Exception as e:
            logger.warning("encode_documents 失败，返回零矩阵: {}", e)
            return np.zeros((len(texts), self._dim), dtype=np.float32)

    def load_model(self, model_name: Optional[str] = None, model_path: Optional[str] = None) -> None:
        """
        加载 embedding 模型到内存。

        优先使用本地路径，不存在则从 HuggingFace ID 加载。

        Args:
            model_name: 模型名称，不传则用默认
            model_path: 本地模型路径，存在则从本地加载
        """
        if model_name:
            self._model_name = model_name
        if model_path:
            self._model_path = model_path

        load_from = self._model_path or self._model_name
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(load_from)
            self._dim = self._model.get_sentence_embedding_dimension() or self.DEFAULT_DIM
            logger.info("Embedding 模型已加载: {} (dim={})", load_from, self._dim)
        except Exception as e:
            logger.warning("Embedding 模型加载失败（将使用零向量兜底）: {}", e)
            self._model = None

    # ── 内部 ──

    def _ensure_model(self) -> None:
        """确保模型已加载（惰性加载）"""
        if self._model is None:
            self.load_model()

    @staticmethod
    def _resolve_path() -> Optional[str]:
        """从 config 或环境变量解析本地模型路径"""
        path = os.environ.get("EMBEDDING_MODEL_PATH", "models/embedding/bge-large-zh-v1.5")
        if os.path.isdir(path):
            return path
        return None

    @property
    def dim(self) -> int:
        """向量维度"""
        return self._dim

    @property
    def model_name(self) -> str:
        """当前模型名称"""
        return self._model_name

    @property
    def model_path(self) -> Optional[str]:
        """本地模型路径"""
        return self._model_path
