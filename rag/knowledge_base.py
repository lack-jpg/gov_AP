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

# 默认 Milvus 集合名（与 retriever.DEFAULT_COLLECTION 一致）
COLLECTION_NAME = "gov_policy"


def _milvus_host_default() -> str:
    """Milvus 主机（读配置，默认 localhost）。"""
    try:
        from backend.config import get_settings
        return get_settings().milvus_host or "localhost"
    except Exception:
        return "localhost"


def _milvus_port_default() -> int:
    """Milvus 端口（读配置 19532，容器内应为 19530）。"""
    try:
        from backend.config import get_settings
        return int(get_settings().milvus_port) or 19530
    except Exception:
        return 19530


def _milvus_index_params() -> dict:
    """HNSW 索引参数（读配置，默认 M=16 / efConstruction=200 / nlist=1024）。"""
    m, ef, nlist = 16, 200, 1024
    try:
        from backend.config import get_settings
        s = get_settings()
        m = int(s.milvus_index_m) or m
        ef = int(s.milvus_index_ef_construction) or ef
        nlist = int(s.milvus_index_nlist) or nlist
    except Exception:
        pass
    return {"M": m, "efConstruction": ef, "nlist": nlist}


def _ensure_index(collection) -> None:
    """确保 embedding 字段存在 HNSW 索引（幂等，缺则补建）。"""
    try:
        indexes = [idx.field_name for idx in collection.indexes]
        if "embedding" in indexes:
            return
        collection.create_index(
            "embedding",
            {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": _milvus_index_params(),
            },
        )
        logger.info("已创建 HNSW 索引 (gov_policy): {}", _milvus_index_params())
    except Exception as e:
        logger.warning("创建 Milvus 索引失败（不影响数据插入）: {}", e)


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
        milvus_host: str = "",
        milvus_port: int = 0,
    ) -> int:
        """
        将文档索引到 Milvus（含 Embedding）。

        流程: 切分 → Embedding → 写入 Milvus。
        Milvus 不可用时仅完成切分和 Embedding，不中断。

        Args:
            documents: 文档列表，不传则用 load_documents 的结果
            milvus_host: Milvus 主机（空则读配置 MILVUS_HOST）
            milvus_port: Milvus 端口（0 则读配置 MILVUS_PORT）

        Returns:
            索引的文档数
        """
        milvus_host = milvus_host or _milvus_host_default()
        milvus_port = milvus_port or _milvus_port_default()
        docs = documents or self._documents
        if not docs:
            logger.warning("没有文档需要索引")
            return 0

        # 1. 切分
        chunks = await self.split_documents(docs)
        if not chunks:
            return 0

        # 2. Embedding
        vectors = None
        try:
            from rag.embedding import EmbeddingEngine
            engine = EmbeddingEngine()
            vectors = await engine.encode_documents([c["content"] for c in chunks])
            logger.info("Embedding 完成: {} 个片段 → {}", len(chunks), vectors.shape)
        except Exception as e:
            logger.warning("Embedding 失败（跳过向量索引）: {}", e)

        # 3. 写入 Milvus
        if vectors is not None:
            try:
                from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility

                connections.connect(alias="default", host=milvus_host, port=str(milvus_port))
                collection_name = COLLECTION_NAME

                if utility.has_collection(collection_name):
                    collection = Collection(collection_name)
                else:
                    fields = [
                        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
                        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
                        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
                        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=vectors.shape[1]),
                    ]
                    schema = CollectionSchema(fields, description="政务政策知识库")
                    collection = Collection(collection_name, schema)

                # 确保 HNSW 索引（参数读配置）
                _ensure_index(collection)

                # 插入数据
                data = [
                    [c["title"] for c in chunks],
                    [c["content"] for c in chunks],
                    [c["source"] for c in chunks],
                    [v.tolist() for v in vectors],
                ]
                collection.insert(data)
                collection.flush()
                logger.info("Milvus 索引完成: {} 个片段 → {}", len(chunks), collection_name)
            except Exception as e:
                logger.warning("Milvus 索引失败（数据保留在内存）: {}", e)

        logger.info("文档索引完成: {} 个片段", len(chunks))
        return len(chunks)

    async def rebuild_index(self, path: str, milvus_host: str = "", milvus_port: int = 0) -> int:
        """
        重建知识库索引（清空后重新索引）。

        Args:
            path: 文档路径
            milvus_host: Milvus 主机（空则读配置）
            milvus_port: Milvus 端口（0 则读配置）

        Returns:
            索引的文档数
        """
        milvus_host = milvus_host or _milvus_host_default()
        milvus_port = milvus_port or _milvus_port_default()
        # 清空 Milvus 集合
        try:
            from pymilvus import utility
            if utility.has_collection(COLLECTION_NAME):
                utility.drop_collection(COLLECTION_NAME)
                logger.info("已清空旧集合 {}", COLLECTION_NAME)
        except Exception as e:
            logger.warning("清空 Milvus 集合失败: {}", e)

        docs = await self.load_documents(path)
        return await self.index_documents(docs, milvus_host=milvus_host, milvus_port=milvus_port)

    async def get_document_count(self) -> int:
        """获取已索引的文档数"""
        try:
            from pymilvus import utility
            if utility.has_collection("gov_policy"):
                from pymilvus import Collection
                return Collection("gov_policy").num_entities
        except Exception:
            pass
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
