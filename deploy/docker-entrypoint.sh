#!/bin/sh
# =====================================================
# gov-agent-api 容器入口脚本
#
# 问题：compose 将宿主机目录 bind mount 到 /app/logger、/app/data、
#       /app/models，bind mount 会覆盖镜像构建时的 chown，
#       导致容器内非 root 用户（appuser, uid=1000）无写权限，
#       loguru 创建日志文件失败 → uvicorn lifespan 启动抛异常。
#
# 方案：以 root 启动（Dockerfile 不再设置 USER appuser）
#   1. 授权所有 bind mount 目录给 appuser
#   2. 通过 setpriv 降权为 appuser 执行原始 CMD（uvicorn）
#      最终业务进程仍为非 root，保留安全加固。
# =====================================================
set -e

for d in /app/logger /app/data /app/models /app/evaluation_results; do
    if [ -d "$d" ]; then
        chown -R appuser:appuser "$d" 2>/dev/null \
            || echo "[entrypoint] warning: 无法 chown $d（可能为只读挂载）"
    fi
done

# ──────────────────────────────────────────────────────────────
# P4-7 DB 迁移：发布流程显式执行 alembic upgrade head（带 advisory lock）
#  - 由 deploy/run_migrations.py 串行化迁移，多副本滚动发布不竞争
#  - 迁移失败非零退出 → 容器启动失败，禁止带漂移 schema 对外服务
#  - 移除旧 "启动即静默 create_all 兜底"（现仅在本地开发 DB_ALLOW_CREATE_ALL=true 兜底）
# ──────────────────────────────────────────────────────────────
echo "[entrypoint] running database migrations..."
python /app/deploy/run_migrations.py

# 以 appuser 身份运行原始 CMD；exec 使 uvicorn 成为 PID 1，信号正常透传
# 注：setpriv 只切换 uid/gid，不更新 HOME —— 显式指向 appuser 家目录，
#     避免 PostgreSQL 客户端（asyncpg）去读 /root/.postgresql/ 触发 Permission denied。
export HOME=/home/appuser
exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"
