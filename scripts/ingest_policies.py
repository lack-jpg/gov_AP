"""
scripts.ingest_policies - 政策语料一键入库 + 自检（真实 RAG 激活）

Author: le
Date: 2026/9/6
Version: 0.1
Task: 将 data/policies/ 下的政策文档切分 → Embedding → 写入 Milvus(gov_policy)，
      并用 rag.pipeline 自检检索模式，确认真实 RAG（mode=rag/bm25）而非 stub 生效。

背景:
    policy_server / PolicyAgent 的真实检索链路依赖两件事：
      1. 语料进入进程（data/policies → BM25 内存索引）——随容器挂载自动完成
      2. 向量进入 Milvus（KnowledgeBase.index_documents）——无任何启动钩子自动触发，
         必须显式执行一次。本脚本即补上这一步。
    Embedding/Reranker 模型缺失时不会报错（返回零向量 / 保持原序），
    因此脚本自检 mode 能直接告诉你检索是否真的激活。

前置条件:
    - Milvus 已启动且宿主机可达:
        docker compose up -d milvus        # 宿主映射默认 localhost:12211
    - 宿主机可 import RAG 依赖（pymilvus / sentence-transformers / FlagEmbedding）。
      开发环境 `pip install -r requirements/requirements.txt` 已含。
    - 模型已下载: models/embedding、models/reranker（见 models/README.md）
    - 语料已放置: data/policies/*.{txt,md,pdf,docx}
    - Milvus 地址按 backend.config 读取: .env 的 MILVUS_HOST / MILVUS_PORT
      （缺省 localhost:12211，与 docker-compose 宿主映射一致）

Usage:
    # 宿主机直连 Docker 映射的 Milvus（推荐）
    python scripts/ingest_policies.py

    # 只追加新语料、不清空集合
    python scripts/ingest_policies.py --no-rebuild

    # 指定语料目录 + 自定义自检问题
    python scripts/ingest_policies.py --data-dir data/policies --query "开餐馆需要什么手续"

    # 容器内备选（api 镜像已含 RAG 依赖 + 挂载 models/data + 指向 milvus 的 env）:
    docker compose exec api python -c "import asyncio; from rag.knowledge_base import KnowledgeBase; asyncio.run(KnowledgeBase().rebuild_index('data/policies'))"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 将项目根加入 sys.path，并切换工作目录到项目根。
# 注意：backend.config 的 .env 与 embedding_model_path（models/...）均按相对路径解析，
#       不从项目根运行会读不到 .env / 找不到本地模型。
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


# ============================================================
# 核心逻辑
# ============================================================


async def _run(args: argparse.Namespace) -> int:
    data_dir = str(Path(args.data_dir).resolve())

    from rag.knowledge_base import KnowledgeBase

    print(f"== 政策语料入库: {data_dir} ==")

    kb = KnowledgeBase()

    # ── 1. 入库（默认清空重建，幂等） ──
    if args.no_rebuild:
        print(">> 增量模式: 加载语料并追加索引（不清空集合）")
        docs = await kb.load_documents(data_dir)
        if not docs:
            print("!! 未加载到任何文档，请检查 data_dir 下的文件格式（.txt/.md/.pdf/.docx）")
            return 1
        indexed = await kb.index_documents(docs)
    else:
        print(">> 重建模式: 清空 Milvus 集合后重新切分 → Embedding → 写入")
        indexed = await kb.rebuild_index(data_dir)

    print(f">> 已切分并写入 {indexed} 个片段")

    # ── 2. 知识库数量（验证向量真的落库；Milvus 不可用时 get_document_count 回退本地加载数） ──
    try:
        count = await kb.get_document_count()
        print(f">> 知识库数量: {count}（Milvus gov_policy 实体数；Milvus 未连接时回退为本地加载文档数）")
        if count == 0:
            print("!! 知识库数量为 0：通常是语料为空 / Embedding 模型缺失返回零向量 / 未连接 Milvus，")
            print("   请确认 data_dir 下有文档、models/embedding 已下载、MILVUS_HOST/MILVUS_PORT 可达。")
            return 1
    except Exception as e:  # pragma: no cover - 诊断输出
        print(f"!! 查询知识库数量失败: {e}")

    # ── 3. 自检：真实检索一次，确认识别链路激活 ──
    print("\n== 自检: rag.pipeline.retrieve ==")
    try:
        from rag.pipeline import get_pipeline

        pipeline = get_pipeline()
        result = await pipeline.retrieve(args.query, top_k=3)
        mode = result.get("mode", "empty")
        documents = result.get("documents", [])

        print(f">> 检索问题: {args.query}")
        print(f">> mode = {mode}    命中 {len(documents)} 条")
        for idx, doc in enumerate(documents[:3], start=1):
            print(f"   {idx}. [{doc.get('score', '?')}] {doc.get('title', '')[:40]}  <{doc.get('source', '')}>")

        if mode == "rag":
            print("\n✓ 真实 RAG 已激活：Milvus 稠密检索 + BM25 稀疏检索均已生效")
        elif mode == "bm25":
            print("\n△ 当前为纯 BM25 稀疏检索（Milvus 未连接或 query 向量不可用），语料已生效")
        else:
            print("\n✗ 检索未命中（mode=empty）：语料为空、或 Milvus/模型链路未就绪")
            print("   检查清单: ① data/policies 有文档 ② models/embedding 已下载 ③ MILVUS_HOST 可达")
            return 1
        return 0
    except Exception as e:  # pragma: no cover - 诊断输出
        print(f"!! 自检检索失败: {e}")
        return 1


# ============================================================
# CLI
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="政策语料一键入库：切分 → Embedding → Milvus，并自检 RAG 检索模式",
    )
    parser.add_argument(
        "--data-dir",
        default="data/policies",
        help="政策语料目录（支持 .txt/.md/.pdf/.docx），默认 data/policies",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="不清空 Milvus 集合，增量追加索引（默认清空重建）",
    )
    parser.add_argument(
        "--query",
        default="开办餐馆需要什么手续",
        help="自检检索问题，默认: 开办餐馆需要什么手续",
    )
    args = parser.parse_args()

    code = asyncio.run(_run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
