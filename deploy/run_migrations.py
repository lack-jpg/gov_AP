"""deploy.run_migrations - 发布流程显式执行 Alembic 迁移（P4-7）

背景：此前迁移只在应用启动 init_db() 里顺带执行，失败静默 create_all 兜底，
导致模型加列（如 trace.user_id/tenant_id）后没有对应迁移 → 存量库 schema 漂移。

本脚本供容器 entrypoint 在启动 uvicorn 前显式调用：
    1. 以 pg_advisory_lock 串行化迁移（多副本滚动发布只有一个副本执行 DDL，
       其余等待，避免并发迁移竞争 / 重复建索引）；
    2. 迁移失败即非零退出 → 容器启动失败 → 不会带漂移 schema 对外服务。

用法（容器内）:
    python /app/deploy/run_migrations.py
"""
from __future__ import annotations

import os
import sys

_LOCK_KEY = 0x6706_6167_5F41  # 'gov_AP' 哈希风格常量，advisory lock 键

# 本脚本可能以 `python deploy/run_migrations.py`（任意 cwd）或容器 entrypoint
# （cwd=/app）调用；sys.path[0]=脚本目录而非仓库根。显式把仓库根加入 sys.path，
# 保证 `import backend.config` 与 Alembic env.py 都能解析（无需依赖 PYTHONPATH）。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import psycopg

    from alembic import command
    from alembic.config import Config

    from backend.config import get_settings
except ImportError as e:  # pragma: no cover - 依赖缺失属环境配置错误
    print(f"[run_migrations] 依赖不可用，无法执行迁移: {e}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    settings = get_settings()
    print(f"[run_migrations] target DB: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

    # postgres_sync_url 是 SQLAlchemy 方言 URL（postgresql+psycopg://），
    # psycopg3/libpq 不认 +driver scheme；剥离为纯 postgresql:// 再交给 psycopg.connect。
    libpq_url = settings.postgres_sync_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )

    try:
        with psycopg.connect(libpq_url, connect_timeout=10) as conn:
            # 会话级 advisory lock：并发副本在此排队，串行执行迁移
            conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
            try:
                print("[run_migrations] running: alembic upgrade head ...")
                cfg = Config("alembic.ini")
                command.upgrade(cfg, "head")
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
        print("[run_migrations] schema is up to date")
        return 0
    except Exception as e:
        print(f"[run_migrations] 迁移失败（拒绝启动，避免 schema 漂移）: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
