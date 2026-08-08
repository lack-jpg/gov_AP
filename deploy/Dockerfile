# =====================================================
# Dockerfile - Government Agent Platform (FastAPI Backend)
# Author: le
# Date: 2026/8/2
# Version: 0.2
# Task: Multi-stage Docker build for FastAPI backend
#
# Usage:
#   docker build -f deploy/Dockerfile -t gov-agent-api:latest .
# =====================================================

# ──────────────────────────────────────
# Stage 1: Builder — 安装依赖
# ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# 系统依赖（用于文档解析、图像处理等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 优先安装轻量核心依赖（不包含 GPU/OCR 重型组件）
COPY requirements/requirements.txt requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt || pip install --no-cache-dir --prefix=/install \
    fastapi uvicorn[standard] pydantic pydantic-settings \
    langchain langchain-core langchain-community langgraph \
    langchain-openai openai httpx sqlalchemy asyncpg redis \
    python-jose passlib[bcrypt] python-dotenv loguru pymilvus

# ──────────────────────────────────────
# Stage 2: Runtime — 运行应用
# ──────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装依赖
COPY --from=builder /install /usr/local

# 复制应用代码
COPY . .

# 入口脚本（以 root 运行 → 授权 bind mount 目录 → 降权为 appuser）
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 非 root 用户（安全）
# 注：不设置 USER —— 入口脚本以 root 启动，chown 挂载目录后通过
#     setpriv 降权为 appuser 运行 uvicorn，最终业务进程仍为非 root。
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

EXPOSE 12401

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:12401/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "12401"]
