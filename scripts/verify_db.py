"""
scripts.verify_db - 数据库环境验证脚本

Author: le
Date: 2026/7/30
Version: 0.1
Task: Verify all database services are running and accessible

Usage:
    python scripts/verify_db.py          # 验证所有数据库
    python scripts/verify_db.py --pg-only # 仅验证 PostgreSQL
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# 验证函数
# ============================================================


async def verify_postgres() -> dict:
    """
    验证 PostgreSQL 连接 + 表创建。

    Returns:
        {"ok": bool, "tables": int, "rows": int, "error": str|None}
    """
    from sqlalchemy import select, text
    from database.connection import get_session_factory

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            # 1. 基础连接测试
            await session.execute(text("SELECT 1"))

            # 2. 查询所有用户表
            result = await session.execute(text("""
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """))
            tables = [row[0] for row in result.fetchall()]

            # 3. 统计每个表的行数
            table_rows: dict[str, int] = {}
            total_rows = 0
            for table_name in tables:
                result = await session.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                )
                count = result.scalar() or 0
                table_rows[table_name] = count
                total_rows += count

            return {
                "ok": True,
                "tables": len(tables),
                "table_names": tables,
                "rows": total_rows,
                "table_rows": table_rows,
                "error": None,
            }

    except Exception as e:
        return {
            "ok": False,
            "tables": 0,
            "table_names": [],
            "rows": 0,
            "table_rows": {},
            "error": str(e),
        }


async def verify_redis() -> dict:
    """
    验证 Redis 连接。

    Returns:
        {"ok": bool, "error": str|None}
    """
    try:
        from database.redis import get_redis_client

        client = get_redis_client()
        await client.connect()
        pong = await client.ping()

        return {
            "ok": pong is True,
            "error": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


async def verify_milvus() -> dict:
    """
    验证 Milvus 连接。

    Returns:
        {"ok": bool, "collections": int, "error": str|None}
    """
    try:
        from backend.config import get_settings
        from pymilvus import connections, utility

        settings = get_settings()

        # 在事件循环中连接 Milvus
        connections.connect(
            alias="verify",
            host=settings.milvus_host,
            port=settings.milvus_port,
            timeout=10,
        )

        collections = utility.list_collections(using="verify")
        connections.disconnect("verify")

        return {
            "ok": True,
            "collections": len(collections),
            "collection_names": collections,
            "error": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "collections": 0,
            "collection_names": [],
            "error": str(e),
        }


# ============================================================
# 报告输出
# ============================================================


def print_report(pg: dict, redis: dict, milvus: dict) -> None:
    """打印聚合验证报告"""

    print()
    print("=" * 60)
    print("  数据库环境验证报告")
    print("=" * 60)
    print()

    # ── PostgreSQL ──
    print("── PostgreSQL ──")
    if pg["ok"]:
        print(f"  Status:  OK")
        print(f"  Tables:  {pg['tables']}")
        for name, count in pg["table_rows"].items():
            print(f"    - {name}: {count} rows")
        if pg["tables"] == 0:
            print("    (表尚未创建 — 启动 FastAPI 后会自动建表)")
    else:
        print(f"  Status:  FAIL")
        print(f"  Error:   {pg['error']}")
    print()

    # ── Redis ──
    print("── Redis ──")
    if redis["ok"]:
        print(f"  Status:  OK (PONG)")
    else:
        print(f"  Status:  FAIL")
        print(f"  Error:   {redis['error']}")
    print()

    # ── Milvus ──
    print("── Milvus ──")
    if milvus["ok"]:
        print(f"  Status:  OK")
        print(f"  Collections: {milvus['collections']}")
        for name in milvus.get("collection_names", []):
            print(f"    - {name}")
    else:
        print(f"  Status:  FAIL")
        print(f"  Error:   {milvus['error']}")
    print()

    # ── 汇总 ──
    all_ok = pg["ok"] and redis["ok"] and milvus["ok"]
    print("=" * 60)
    if all_ok:
        print("  汇总: ALL OK ")
    else:
        print("  汇总: SOME FAILED ")
        failed = []
        if not pg["ok"]:
            failed.append("PostgreSQL")
        if not redis["ok"]:
            failed.append("Redis")
        if not milvus["ok"]:
            failed.append("Milvus")
        print(f"  失败: {', '.join(failed)}")
    print("=" * 60)
    print()


# ============================================================
# 入口
# ============================================================


async def main():
    parser = argparse.ArgumentParser(description="验证数据库环境")
    parser.add_argument(
        "--pg-only", action="store_true", help="仅验证 PostgreSQL"
    )
    parser.add_argument(
        "--redis-only", action="store_true", help="仅验证 Redis"
    )
    parser.add_argument(
        "--milvus-only", action="store_true", help="仅验证 Milvus"
    )
    args = parser.parse_args()

    # 默认验证所有
    do_pg = args.pg_only or not (args.redis_only or args.milvus_only)
    do_redis = args.redis_only or not (args.pg_only or args.milvus_only)
    do_milvus = args.milvus_only or not (args.pg_only or args.redis_only)

    pg = await verify_postgres() if do_pg else {"ok": True, "tables": 0, "rows": 0, "table_rows": {}, "error": "skipped"}
    redis = await verify_redis() if do_redis else {"ok": True, "error": "skipped"}
    milvus = await verify_milvus() if do_milvus else {"ok": True, "collections": 0, "collection_names": [], "error": "skipped"}

    print_report(pg, redis, milvus)

    # 退出码：全部通过 → 0，有失败 → 1
    all_ok = pg["ok"] and redis["ok"] and milvus["ok"]
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
