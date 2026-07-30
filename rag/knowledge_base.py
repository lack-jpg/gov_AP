"""
rag.knowledge_base - Knowledge base: policy document indexing and management

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement policy knowledge base indexing and update pipeline
"""
from __future__ import annotations

import os
from typing import Optional

from tools.logger import get_logger

logger = get_logger(__name__)


class KnowledgeBase:
    """
    政策知识库管理。

    流程:
        文档加载 → 文本切分 → Embedding → 写入 Milvus → 可检索

    支持的文档格式: PDF, DOCX, TXT, Markdown

    TODO: 接入 pypdf/python-docx 加载文档，pymilvus 写入索引

    使用方式:
        kb = KnowledgeBase()
        await kb.load_documents("data/policies/")
        await kb.index_documents()
    """

    DEFAULT_CHUNK_SIZE = 512
    DEFAULT_CHUNK_OVERLAP = 64

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._documents: list[dict] = []

    async def load_documents(self, path: str) -> list[dict]:
        """
        加载文档目录中的所有文件。

        Args:
            path: 文件或目录路径

        Returns:
            加载的文档列表 [{title, content, source, page}, ...]
        """
        docs: list[dict] = []

        if os.path.isfile(path):
            docs = await self._load_file(path)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for fname in files:
                    if self._is_supported(fname):
                        fpath = os.path.join(root, fname)
                        file_docs = await self._load_file(fpath)
                        docs.extend(file_docs)

        self._documents = docs
        logger.info(
            "文档加载完成: {} 个文件 → {} 个文档片段",
            len(set(d.get("source", "") for d in docs)), len(docs),
        )
        return docs

    async def split_documents(
        self,
        documents: list[dict],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> list[dict]:
        """
        将文档切分为固定大小的片段。

        Args:
            documents: 原始文档列表
            chunk_size: 每段最大字符数
            chunk_overlap: 段落重叠字符数

        Returns:
            切分后的片段列表
        """
        cs = chunk_size or self._chunk_size
        co = chunk_overlap or self._chunk_overlap
        chunks: list[dict] = []

        for doc in documents:
            content = doc.get("content", "")
            title = doc.get("title", "")

            # 简单滑动窗口切分
            start = 0
            while start < len(content):
                end = min(start + cs, len(content))
                chunk_text = content[start:end]

                chunks.append({
                    **doc,
                    "content": chunk_text,
                    "chunk_start": start,
                    "chunk_end": end,
                    "chunk_id": f"{title}_chunk_{len(chunks)}",
                })

                start += cs - co
                if start >= len(content):
                    break

        logger.info("文档切分: {} → {} 个片段", len(documents), len(chunks))
        return chunks

    async def index_documents(
        self,
        documents: Optional[list[dict]] = None,
    ) -> int:
        """
        将文档索引到 Milvus。

        Args:
            documents: 文档列表，不传则用 load_documents 的结果

        Returns:
            索引的文档数
        """
        docs = documents or self._documents
        if not docs:
            logger.warning("没有文档需要索引")
            return 0

        # 1. 切分
        chunks = await self.split_documents(docs)

        # 2. Embedding
        # TODO: from rag.embedding import EmbeddingEngine
        # engine = EmbeddingEngine()
        # vectors = await engine.encode_documents([c["content"] for c in chunks])

        # 3. 写入 Milvus
        # TODO: from pymilvus import Collection
        # collection.insert([...])

        logger.info("文档索引完成: {} 个片段", len(chunks))
        return len(chunks)

    async def rebuild_index(self, path: str) -> int:
        """
        重建知识库索引（清空后重新索引）。

        Args:
            path: 文档路径

        Returns:
            索引的文档数
        """
        # TODO: 清空 Milvus 集合
        docs = await self.load_documents(path)
        return await self.index_documents(docs)

    async def get_document_count(self) -> int:
        """获取已索引的文档数"""
        # TODO: Milvus num_entities
        return len(self._documents)

    # ── 内部 ──

    async def _load_file(self, path: str) -> list[dict]:
        """加载单个文件"""
        ext = os.path.splitext(path)[1].lower()
        title = os.path.basename(path)

        try:
            if ext == ".txt":
                with open(path, encoding="utf-8") as f:
                    content = f.read()
            elif ext == ".md":
                with open(path, encoding="utf-8") as f:
                    content = f.read()
            elif ext == ".pdf":
                # TODO: from pypdf import PdfReader
                # reader = PdfReader(path)
                # content = "\n".join(p.extract_text() or "" for p in reader.pages)
                logger.debug("PDF 支持待接入: {}", path)
                content = ""
            elif ext == ".docx":
                # TODO: from docx import Document
                # doc = Document(path)
                # content = "\n".join(p.text for p in doc.paragraphs)
                logger.debug("DOCX 支持待接入: {}", path)
                content = ""
            else:
                logger.debug("不支持的文件格式: {}", path)
                return []
        except Exception as e:
            logger.warning("文件加载失败: {} ({})", path, e)
            return []

        return [{"title": title, "content": content, "source": path, "page": 1}]

    @staticmethod
    def _is_supported(filename: str) -> bool:
        """检查文件格式是否支持"""
        ext = os.path.splitext(filename)[1].lower()
        return ext in (".txt", ".md", ".pdf", ".docx")
