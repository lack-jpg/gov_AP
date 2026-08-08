"""
backend.config - Application configuration: environment variables, settings via pydantic-settings

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement configuration management with .env support
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，所有值从环境变量/.env文件读取"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 应用 ──
    app_name: str = Field(
        default="Government Agent Platform",
        description="应用名称",
    )
    app_version: str = Field(
        default="0.1.0",
        description="应用版本号",
    )
    debug: bool = Field(
        default=False,
        description="调试模式，生产环境必须为False",
    )
    log_level: str = Field(
        default="INFO",
        description="日志级别: DEBUG | INFO | WARNING | ERROR",
    )
    log_dir: str = Field(
        default="",
        alias="GOV_LOG_DIR",
        description=(
            "日志输出目录（绝对路径）。为空时自动使用项目根下的 logger/ 目录。"
            "Docker 部署时可设为 /var/log/gov_ap/ 等挂载路径。"
        ),
    )

    # ── 服务端口 ──
    host: str = Field(
        default="0.0.0.0",
        alias="APP_HOST",
        description="FastAPI监听地址",
    )
    port: int = Field(
        default=8002,
        alias="APP_PORT",
        description="FastAPI监听端口（默认 8002，避免与本地 8000 冲突）",
    )
    frontend_port: int = Field(
        default=12345,
        alias="FRONTEND_PORT",
        description="前端开发服务器端口（Streamlit / Vite / Next.js）",
    )

    # ── LLM ──
    llm_api_url: str = Field(
        default="http://localhost:8000/v1",
        alias="LLM_API_URL",
        description="LLM API地址（OpenAI兼容接口）",
    )
    llm_api_key: str = Field(
        default="",
        alias="LLM_API_KEY",
        description="LLM API密钥",
    )
    llm_model: str = Field(
        default="qwen2.5-14b-instruct",
        alias="LLM_MODEL",
        description="默认LLM模型名称",
    )
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM生成温度，越低越确定性",
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="LLM单次最大输出Token数",
    )
    llm_timeout: int = Field(
        default=60,
        description="LLM API调用超时时间（秒）",
    )
    llm_cache_enabled: bool = Field(
        default=True,
        alias="LLM_CACHE_ENABLED",
        description="LLM 响应缓存（相同问题复用结果，减少重复调用与成本）",
    )
    llm_cache_ttl: int = Field(
        default=3600,
        alias="LLM_CACHE_TTL",
        description="LLM 缓存过期时间（秒），默认 1 小时",
    )

    # ── 模型文件路径 ──
    models_dir: str = Field(
        default="models",
        alias="MODELS_DIR",
        description="模型文件根目录（相对于项目根目录）",
    )
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5",
        alias="EMBEDDING_MODEL",
        description="Embedding模型名称（HuggingFace ID）",
    )
    embedding_model_path: str = Field(
        default="models/embedding/bge-large-zh-v1.5",
        alias="EMBEDDING_MODEL_PATH",
        description="Embedding模型本地路径，存在则从本地加载",
    )
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        alias="RERANKER_MODEL",
        description="Reranker模型名称（HuggingFace ID）",
    )
    reranker_model_path: str = Field(
        default="models/reranker/bge-reranker-v2-m3",
        alias="RERANKER_MODEL_PATH",
        description="Reranker模型本地路径，存在则从本地加载",
    )
    intent_model_path: str = Field(
        default="models/intent/bert-intent",
        alias="INTENT_MODEL_PATH",
        description="意图分类Bert模型本地路径",
    )
    ocr_model_path: str = Field(
        default="",
        alias="OCR_MODEL_PATH",
        description="PaddleOCR 模型本地路径（空则使用默认）",
    )
    ner_model_path: str = Field(
        default="",
        alias="NER_MODEL_PATH",
        description="BERT-NER 命名实体识别模型本地路径（空则使用regex模式）",
    )

    # ── PostgreSQL ──
    postgres_host: str = Field(
        default="localhost",
        alias="POSTGRES_HOST",
        description="PostgreSQL主机地址",
    )
    postgres_port: int = Field(
        default=5658,
        alias="POSTGRES_PORT",
        description=(
            "PostgreSQL端口。本地开发用宿主端口 5658（docker compose 映射），"
            "容器内运行时设为 5432（服务名 postgres）"
        ),
    )
    postgres_user: str = Field(
        default="gov_agent",
        alias="POSTGRES_USER",
        description="PostgreSQL用户名",
    )
    postgres_password: str = Field(
        default="",
        alias="POSTGRES_PASSWORD",
        description="PostgreSQL密码",
    )
    postgres_db: str = Field(
        default="gov_agent_platform",
        alias="POSTGRES_DB",
        description="PostgreSQL数据库名",
    )

    @property
    def postgres_url(self) -> str:
        """构建完整的PostgreSQL连接URL（asyncpg驱动）"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_url(self) -> str:
        """构建同步PostgreSQL连接URL（psycopg驱动，用于Alembic迁移）"""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ──
    redis_host: str = Field(
        default="localhost",
        alias="REDIS_HOST",
        description="Redis主机地址",
    )
    redis_port: int = Field(
        default=6500,
        alias="REDIS_PORT",
        description=(
            "Redis端口。本地开发用宿主端口 6500（docker compose 映射），"
            "容器内运行时设为 6379（服务名 redis）"
        ),
    )
    redis_password: str = Field(
        default="",
        alias="REDIS_PASSWORD",
        description="Redis密码",
    )

    @property
    def redis_url(self) -> str:
        """构建Redis连接URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # ── Milvus ──
    milvus_host: str = Field(
        default="localhost",
        alias="MILVUS_HOST",
        description="Milvus主机地址",
    )
    milvus_port: int = Field(
        default=19532,
        alias="MILVUS_PORT",
        description=(
            "Milvus端口。本地开发用宿主端口 19532（docker compose 映射），"
            "容器内运行时设为 19530（服务名 milvus）"
        ),
    )
    milvus_index_m: int = Field(
        default=16,
        alias="MILVUS_INDEX_M",
        description="HNSW 索引参数 M（每个节点的最大连接数，越大召回越好、内存/构建开销越高）",
    )
    milvus_index_ef_construction: int = Field(
        default=200,
        alias="MILVUS_INDEX_EF_CONSTRUCTION",
        description="HNSW 索引构建参数 efConstruction（越大索引质量越高、构建越慢）",
    )
    milvus_index_nlist: int = Field(
        default=1024,
        alias="MILVUS_INDEX_NLIST",
        description="HNSW 索引参数 nlist（聚类中心数，影响查询速度与精度）",
    )
    milvus_search_nprobe: int = Field(
        default=10,
        alias="MILVUS_SEARCH_NPROBE",
        description="HNSW 搜索参数 nprobe / ef（检索时扫描的聚类数/候选集大小）",
    )

    # ── Agent Runtime ──
    agent_max_steps: int = Field(
        default=10,
        alias="AGENT_MAX_STEPS",
        description="Agent最大执行步数，超过则终止",
    )
    agent_loop_window: int = Field(
        default=6,
        alias="AGENT_LOOP_WINDOW",
        description="循环检测滑动窗口大小",
    )
    agent_timeout: int = Field(
        default=30,
        alias="AGENT_TIMEOUT",
        description="单个Agent执行超时时间（秒）",
    )

    # ── MCP ──
    mcp_gateway_url: str = Field(
        default="http://localhost:12300",
        alias="MCP_GATEWAY_URL",
        description="MCP Gateway地址（12300 起，Policy/Material/Workflow Server 依次递增）",
    )

    # ── A2A ──
    a2a_callback_url: str = Field(
        default="http://localhost:8002/api/a2a/callback",
        alias="A2A_CALLBACK_URL",
        description="A2A Callback接收地址（本地 API 8002 或 Docker 内 http://api:8002），外部Agent完成回调",
    )
    a2a_housing_url: str = Field(
        default="http://localhost:12201",
        alias="A2A_HOUSING_URL",
        description="不动产外部 Agent 地址（12201；Docker 内为 http://a2a-mock:12201）",
    )
    a2a_fund_url: str = Field(
        default="http://localhost:12202",
        alias="A2A_FUND_URL",
        description="公积金外部 Agent 地址（12202；Docker 内为 http://a2a-mock:12202）",
    )
    a2a_hmac_secret: str = Field(
        default="",
        alias="A2A_HMAC_SECRET",
        description="A2A 回调 HMAC 共享密钥，外部 Agent 凭此签名回调请求",
    )

    # ── JWT ──
    jwt_secret_key: str = Field(
        default="changeme",
        alias="JWT_SECRET_KEY",
        description="JWT签名密钥，生产环境必须更换",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        alias="JWT_ALGORITHM",
        description="JWT签名算法",
    )
    jwt_expire_minutes: int = Field(
        default=1440,
        description="JWT过期时间（分钟），默认24小时",
    )

    # ── OpenTelemetry ──
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4319",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
        description="OpenTelemetry Collector gRPC端点（默认 4319，避免与本地 4317 冲突）",
    )

    # ── LangSmith ──
    langsmith_api_key: str = Field(
        default="",
        alias="LANGSMITH_API_KEY",
        description="LangSmith API Key（可选，用于Trace可视化）",
    )
    langsmith_project: str = Field(
        default="gov-agent-platform",
        alias="LANGSMITH_PROJECT",
        description="LangSmith项目名",
    )

    # ── CORS ──
    cors_origins: str = Field(
        default="http://localhost:12345,http://localhost:3000",
        description="允许的CORS origins，多个用逗号分隔。默认仅允许开发常用端口",
    )

    def get_cors_origins(self) -> list[str]:
        """解析CORS origins为列表"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# ============================================================
# 单例 — 全局配置实例
# ============================================================


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例（带缓存，避免重复读.env）"""
    return Settings()


# 模块级便捷引用
settings = get_settings()
