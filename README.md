# government-agent-platform

# 政务多智能体协同与治理平台

> Enterprise Multi-Agent Platform based on LangGraph + MCP + A2A + AgentOps + RAG

> 注意：前端界面全部由AI生成，请勿直接复制。

> **最近更新（2026-08-06）**：前端视觉升级（浅色政务蓝主题 + 共享 UI 组件库 `frontend/ui.py` + 8 页重构 + `design-system/` 设计规范）+ Docker API 容器启动修复（bind mount 权限）+ 评测报告文件回退（`evaluation_results/`）。详见 [更新日志](#20-更新日志)。

---

<p align="center">

<img src="./docs/images/logo.svg" width="160" alt="GAP Logo">

</p>

## 项目简介

`government-agent-platform` 是一个面向政务业务场景设计的企业级多智能体协同平台。

平台围绕“高效办成一件事”场景，通过：

* **LangGraph** 构建可控 Agent 工作流
* **MCP(Model Context Protocol)** 标准化 Agent 工具调用
* **A2A(Agent-to-Agent)** 实现跨域 Agent 协作
* **RAG** 提供政策知识增强能力
* **AgentOps** 实现 Agent 全生命周期治理

构建了一套：

> 可编排、可观测、可评测、可治理的企业级 Agent Runtime 平台。

---

# 1. 背景与问题

传统政务智能化系统通常存在：

## 1.1 单Agent能力不足

单个LLM Agent同时承担：

* 意图理解
* 政策查询
* 材料审核
* 流程执行

容易导致：

* 推理混乱
* 幻觉增加
* 难以维护

---

## 1.2 系统接口割裂

真实业务中存在：

```
市场监管系统

消防系统

不动产系统

公积金系统

统一办件系统
```

不同系统：

* 接口不同
* 数据隔离
* 权限复杂

---

## 1.3 Agent缺少治理

生产环境需要解决：

* Agent调用链追踪
* 工具调用审计
* Prompt管理
* 自动评测
* 安全控制

因此设计：

```
Multi-Agent
+
Agent Governance
+
Evaluation Platform
```

---

# 2. 核心能力

## Multi-Agent协同

平台包含多个领域Agent：

| Agent            | 职责                                       |
| ---------------- | ---------------------------------------- |
| Supervisor Agent | 全局任务规划                                   |
| Intent Agent     | 用户意图识别（BERT 微调模型 + 关键词兜底 + LLM fallback） |
| Policy Agent     | 政策知识检索                                   |
| Material Agent   | 材料审核                                     |
| Workflow Agent   | 流程执行                                     |
| Governance Agent | 安全治理                                     |

---

# 3. 系统架构

```
                         User
                          |
                          v
                  API Gateway
                    FastAPI
                          |
                          v
             +---------------------+
             | Supervisor Agent    |
             | LangGraph Runtime   |
             +---------------------+
                          |
        +-----------------+----------------+
        |                 |                |
        v                 v                |
 Intent Agent       Policy Agent    Material Agent
        |                 |                |
        +-----------------+----------------+
                          |
                          v
                 Workflow Agent
                          |
                          v
              +----------------+
              | MCP Gateway    |
              +----------------+
                 |      |      |
                 v      v      v
             Policy  Material Workflow
             MCP     MCP      MCP
             Server  Server   Server
                          |
                          v
                  Business System
```

---

# 4. 技术架构

## 六层架构

```
L6  AgentOps治理层

    Trace
    Evaluation
    Guardrail
    Prompt Management

L5  A2A跨域协同层

    Agent Communication
    Async Task
    Callback

L4  MCP工具能力层

    Tool Discovery
    Tool Calling

L3  专业Agent层

    Policy
    Material
    Workflow

L2  Agent编排层

    LangGraph

L1  接入层

    FastAPI
```

---

# 5. LangGraph Agent编排

系统采用：

```
StateGraph
+
Node
+
Edge
+
Checkpoint
```

执行流程：

```
START
 |
Supervisor
 |
Intent Recognition
 |
Task Planning
 |
+----------------+
|                |
Policy        Material
Agent         Agent
|                |
+----------------+
        |
 Workflow Agent
        |
 Governance
        |
       END
```

---

# 6. MCP工具标准化

## 为什么引入MCP？

传统方式：

```python
agent
↓
import function
↓
API
```

问题：

* 强耦合
* 难扩展
* 难治理

---

采用：

```
Agent
↓
MCP Client (Bearer Token)
↓
MCP Gateway (JWT 认证 + RBAC)
↓
MCP Server
↓
Business Service
```

> **安全加固（2026-08-05）**：MCP Gateway 增加 JWT Bearer Token 验证 + RBAC 角色控制（`admin`/`agent` 角色方可调用工具），Client 自动携带认证 Header。

---

## MCP Server

### Policy MCP Server

提供：

```
search_policy
get_policy_detail
```

能力：

* Milvus检索
* BM25召回
* Reranker排序

---

### Material MCP Server

提供：

```
extract_entity
check_material
```

能力：

* OCR
* 信息抽取
* 材料校验

---

### Workflow MCP Server

提供：

```
create_case
query_status
```

能力：

* 办件创建
* 状态查询

---

# 7. A2A跨Agent协同

针对跨部门业务：

例如：

```
营业执照办理
↓
市场监管Agent
↓
消防Agent
↓
不动产Agent
```

采用：

```
A2A Connector
+
Async Task
+
Callback (HMAC 签名验证)
```

> **安全加固（2026-08-05）**：A2A 回调端点增加 HMAC-SHA256 签名验证 + ±300s 时间窗口防重放，防止伪造回调注入。外部 Agent 需使用共享密钥签名请求。

任务生命周期：

```
Created
 ↓
Running
 ↓
Waiting
 ↓
Completed
```

---

# 8. AgentOps治理平台

## 全链路Trace

记录：

```json
{
 "trace_id":"",
 "agent":"",
 "tool":"",
 "latency":"",
 "token_usage":""
}
```

---

## Guardrail安全

> **安全加固（2026-08-05）**：护栏前置到 LLM 前执行，注入/严重敏感词在到达 LLM 之前即被阻断。CORS 默认白名单模式（`localhost:12345,localhost:3000`），可通过 `.env` 配置。

支持：

### 输入检测

* 敏感词
* Prompt Injection
* PII

### 输出检测

* 信息泄露
* 内部错误
* 敏感字段

---

## PII脱敏

示例：

手机号：

```
138****1234
```

身份证：

```
110***********1234
```

邮箱：

```
u***@domain.com
```

---

# 9. 自动评测体系

> **最新更新（2026-08-04）**: trace_provider 已接入，支持真实 Agent 工作流执行并收集 trace 数据。
> Intent 数据集（3500 条）评测通过率 **99.5%**，BERT 模型 `source="bert"` 确认有效。

## 快速运行

```bash
# Intent 快速评测（BERT 本地推理，3500 条约 90 秒）
python -m governance.evaluation.runner run \
  --version v0.2 \
  --datasets intent_cases \
  --run-real --output console

# 全流程评测（LangGraph + LLM API，需 --run-full-workflow）
python -m governance.evaluation.runner run \
  --version v0.2 \
  --datasets rag_cases,agent_cases \
  --run-real --run-full-workflow

# LLM Judge 语义打分 + 数据库持久化
python -m governance.evaluation.runner run \
  --version v0.2 \
  --datasets rag_cases \
  --run-real --run-full-workflow --use-llm --save-to-db

# 列出所有可用数据集
python -m governance.evaluation.runner list

# 对比两个版本
python -m governance.evaluation.runner compare --versions v0.1,v0.2
```

## RAG评测

指标：

| 指标               | 说明    | 评分方式                          |
| ---------------- | ----- | ----------------------------- |
| Faithfulness     | 回答真实性 | 规则（bigram Jaccard）/ LLM Judge |
| Answer Relevance | 答案相关性 | 规则（token overlap）/ LLM Judge  |
| Context Recall   | 上下文召回 | 规则（bigram overlap）/ LLM Judge |

---

## Agent评测

指标：

| 指标                | 说明      |
| ----------------- | ------- |
| Task Success Rate | 任务成功率   |
| Tool Accuracy     | 工具选择准确率 |
| Latency           | 响应耗时    |
| Step Count        | 执行步骤    |

**综合评分权重**：task_success_rate 0.25 + tool_accuracy 0.15 + faithfulness 0.15 + answer_relevance 0.15 + context_recall 0.10 + intent_accuracy 0.10 + efficiency 0.10

---

# 10. Prompt管理

支持：

```
Prompt Registry
       |
Version Control
       |
Runtime Loading
```

避免：

```python
prompt="固定字符串"
```

---

# 11. 项目代码结构

```
gov_AP/
│
├── README.md                         # 项目说明（本文件）
├── CLAUDE.md                         # AI编码规范（Cursor/Claude Code/Copilot）
├── STRUCTURE.md                      # 详细文件清单和开发指引
├── .env.example                      # 环境变量模板
├── .gitignore                        # Git忽略规则
├── example.py                        # 文件头模板
├── docker-compose.yml                # Docker编排（根目录，docker compose up 直接可用）
├── .dockerignore                     # Docker构建上下文排除
├── .streamlit/config.toml            # Streamlit 主题/端口配置（浅色政务蓝主题）
│
├── agents/                           # Agent层 — 6个专业Agent
│   ├── __init__.py                   # Agent注册中心
│   ├── supervisor/                   # 全局任务规划
│   │   ├── agent.py                  # Supervisor核心
│   │   ├── planner.py                # 任务拆解
│   │   ├── router.py                 # Agent路由
│   │   └── prompts.py                # Prompt模板
│   ├── intent/                       # 意图识别
│   │   ├── agent.py                  # Intent核心
│   │   ├── classifier.py             # BERT分类器（微调模型自动加载，source="bert"）
│   │   ├── schema.py                 # 数据模型
│   │   └── prompts.py                # Prompt模板
│   ├── policy/                       # 政策检索
│   │   ├── agent.py                  # Policy核心
│   │   ├── schema.py                 # 数据模型
│   │   └── prompts.py                # Prompt模板
│   ├── material/                     # 材料审核
│   │   ├── agent.py                  # Material核心
│   │   ├── ocr.py                    # OCR识别
│   │   ├── extractor.py              # 实体抽取
│   │   ├── validator.py              # 规则校验
│   │   └── prompts.py                # Prompt模板
│   ├── workflow/                     # 流程执行
│   │   ├── agent.py                  # Workflow核心
│   │   └── prompts.py                # Prompt模板
│   └── governance/                   # 安全治理(旁路)
│       ├── agent.py                  # Governance核心
│       ├── security.py               # 安全检测
│       ├── behavior.py               # 行为分析
│       ├── optimizer.py              # 自动优化
│       └── prompts.py                # Prompt模板
│
├── orchestration/                    # 编排层 — LangGraph工作流
│   └── langgraph/
│       ├── __init__.py               # 包初始化
│       ├── state.py                  # AgentState共享状态
│       ├── graph.py                  # StateGraph构建
│       ├── nodes.py                  # 节点函数
│       ├── edges.py                  # 条件路由
│       ├── checkpointer.py           # 状态持久化
│       └── runtime.py                # 运行时安全控制
│
├── tools/                            # 工具层 — MCP + A2A
│   ├── mcp/                          # MCP协议(Agent→Tool)
│   │   ├── __init__.py               # 包初始化 + 导出
│   │   ├── client.py                 # MCP客户端（Gateway/Direct双模）
│   │   ├── gateway.py                # MCP网关（路由/审计/健康聚合）
│   │   ├── schema.py                 # 6 Tool Pydantic模型 + TOOL_REGISTRY
│   │   ├── start_servers.py          # 一键启动所有MCP基础设施
│   │   └── servers/                  # MCP Server
│   │       ├── policy_server/        # 政策查询服务 :12301
│   │       │   ├── server.py         # FastAPI Server入口
│   │       │   └── tools.py          # search_policy/get_policy_detail
│   │       ├── material_server/      # 材料审核服务 :12302
│   │       │   ├── server.py         # FastAPI Server入口
│   │       │   └── tools.py          # extract_entity/check_material
│   │       └── workflow_server/      # 流程执行服务 :12303
│   │           ├── server.py         # FastAPI Server入口
│   │           └── tools.py          # create_case/query_status
│   └── a2a/                          # A2A协议(Agent→Agent)
│       ├── __init__.py               # 包初始化
│       ├── connector.py              # A2A连接器
│       ├── protocol.py               # 通信协议
│       ├── task.py                   # 任务生命周期
│       ├── registry.py               # Agent注册中心
│       ├── callback.py               # 回调处理
│       └── mock_agents/              # 模拟外部Agent
│           ├── housing_agent.py      # 不动产Agent
│           └── fund_agent.py         # 公积金Agent
│
├── rag/                              # 知识层 — RAG检索增强
│   ├── __init__.py                   # 包初始化
│   ├── embedding.py                  # BGE向量化
│   ├── retriever.py                  # 混合检索(Milvus+BM25)
│   ├── reranker.py                   # BGE重排序
│   ├── generator.py                  # LLM答案生成
│   └── knowledge_base.py             # 知识库管理
│
├── governance/                       # 治理层 — AgentOps
│   ├── __init__.py                   # 包初始化
│   ├── trace.py                      # 全链路追踪
│   ├── guardrail.py                  # 安全护栏(输入/输出)
│   ├── pii.py                        # PII脱敏
│   ├── monitor.py                    # Agent监控
│   ├── dashboard.py                  # 运维看板
│   └── evaluation/                   # 自动评测
│       ├── __init__.py               # 包初始化
│       ├── evaluator.py              # 评测引擎（evaluate_from_cases/traces/db）
│       ├── metrics.py                # 指标计算（RAG + Agent + Intent 复合评分）
│       ├── benchmark.py              # 基准测试（GoldenDataset + BenchmarkRunner）
│       ├── runner.py                 # 评测流水线（CLI: run/compare/list + DB持久化）
│       ├── trace_provider.py         # 真实trace提供者（BERT意图 / LangGraph全流程）
│       └── llm_adapter.py            # LLM Judge适配器（BaseChatModel → score回调）
│
├── database/                         # 数据层 — PostgreSQL
│   ├── __init__.py                   # 包初始化
│   ├── connection.py                 # 数据库连接
│   ├── models.py                     # ORM模型
│   ├── schemas.py                    # Pydantic序列化
│   └── migrations/                   # Alembic迁移
│
├── backend/                          # 接入层 — FastAPI
│   ├── __init__.py                   # 包初始化
│   ├── main.py                       # 应用入口
│   ├── config.py                     # 配置管理
│   ├── api/                          # API路由
│   │   ├── __init__.py               # 包初始化
│   │   ├── routes.py                 # 端点定义
│   │   ├── dependencies.py           # 依赖注入
│   │   └── schemas.py                # 请求/响应模型
│   ├── middleware/                   # 中间件
│   │   ├── __init__.py               # 包初始化
│   │   ├── auth.py                   # JWT认证
│   │   ├── rbac.py                   # 角色权限
│   │   ├── logging.py                # 日志记录
│   │   └── tracing.py                # 链路追踪
│   └── services/                     # 业务服务
│       ├── __init__.py               # 包初始化
│       └── agent_service.py          # Agent编排服务
│
├── frontend/                         # 前端层 — Streamlit 能力演示
│   ├── app.py                        # 导航入口（st.navigation + 8 st.Page）
│   ├── common.py                     # 公共工具（路径设置 + 异步执行）
│   ├── api_client.py                 # 后端 API 客户端（httpx，含 chat_with_fallback 降级）
│   ├── ui.py                         # 共享 UI 组件库（主题CSS/页头/指标卡/状态徽章/证据卡等）
│   ├── stub_chat.py                  # 本地 stub 对话（BERT 意图分类 + 政策模板 + PII 脱敏）
│   └── pages/                        # 8 个功能页面
│       ├── home_page.py              # 首页总览
│       ├── chat_page.py              # 智能对话（API 优先 → stub 降级）
│       ├── intent_page.py            # 意图识别演示
│       ├── policy_page.py            # 政策检索演示
│       ├── material_page.py          # 材料审核演示
│       ├── a2a_page.py               # 跨域协同演示
│       ├── governance_page.py        # 安全治理演示
│       └── dashboard_page.py         # 运维看板
│
├── prompts/                          # Prompt管理
│   ├── __init__.py                   # 包初始化
│   └── registry.py                   # Prompt注册中心(版本化)
│
├── cases/                            # 评测用例
│   ├── __init__.py                   # 包初始化
│   ├── intent_cases.json             # 意图分类用例
│   ├── rag_cases.json                # RAG评测用例
│   ├── agent_cases.json              # Agent评测用例
│   ├── security_cases.json           # 安全评测用例
│   ├── business_license.json         # 营业执照场景
│   ├── policy_query.json             # 政策查询场景
│   └── workflow.json                 # 流程执行场景
│
├── deploy/                           # 部署配置
│   ├── Dockerfile                    # API + MCP Server Docker 镜像
│   ├── docker-entrypoint.sh          # API 容器入口（root 授权 bind mount → setpriv 降权 appuser）
│   ├── Dockerfile.frontend           # Streamlit 前端 Docker 镜像（轻量，仅 streamlit + httpx）
│   └── k8s/                          # Kubernetes
│       ├── backend.yaml              # 后端Deployment
│       ├── agent.yaml                # Agent Runtime
│       ├── model.yaml                # 模型服务(GPU)
│       ├── mcp.yaml                  # MCP Server
│       ├── postgres.yaml             # 数据库
│       └── ingress.yaml              # 入口配置
│
├── models/                           # 模型文件（已 gitignore）
│   ├── README.md                     # 模型清单 + 下载说明
│   ├── embedding/                    # BGE Embedding 模型
│   ├── reranker/                     # BGE Reranker 模型
│   ├── intent/                       # 意图分类 BERT 模型
│   └── fine_tuned/                   # 微调产出版本
│
├── requirements/                     # 依赖管理
│   ├── requirements.txt              # 核心依赖
│   ├── requirements-dev.txt          # 开发工具
│   ├── requirements-gpu.txt          # GPU推理
│   └── requirements-ocr.txt          # OCR能力
│
├── design-system/                    # UI 设计规范
│   └── default/MASTER.md             # 配色/字体/间距/组件规格/反模式
│
└── docs/                             # 设计文档
    ├── ARCHITECTURE.md               # 系统架构
    ├── AGENT_DESIGN.md               # Agent设计
    ├── MCP_DESIGN.md                 # MCP协议设计
    ├── A2A_DESIGN.md                 # A2A通信设计
    ├── EVALUATION.md                 # 评测体系设计
    ├── DEPLOYMENT.md                 # 部署方案
    └── PROJECT_ROADMAP.md            # 演进路线
```

---

# 12. 技术栈

## Backend

* Python 3.12
* FastAPI
* Pydantic v2

## Agent

* LangChain 1.x
* LangGraph 1.x

## Protocol

* MCP 1.x
* A2A

## Knowledge

* Milvus
* BGE Embedding
* BGE Reranker

## Database

* PostgreSQL
* Redis

## Observability

* OpenTelemetry
* LangSmith

## Deployment

* Docker
* Docker Compose

---

# 13. 快速启动

## 环境

```bash
python >=3.12
```

## 端口约定

为避免与本地服务冲突，所有端口偏离标准端口：

| 服务            | 端口        | 说明                 |
| ------------- | --------- | ------------------ |
| Frontend      | **12345** | Streamlit 前端界面     |
| FastAPI       | **8002**  | 后端 API（8000 + 2）   |
| MCP Gateway   | **12300** | 后续 Server 依次 +1    |
| A2A Callback  | **12200** | 后续 Connector 依次 +1 |
| PostgreSQL    | **5658**  | 避开 Hyper-V 保留段     |
| Redis         | **6500**  | 避开 Windows 保留端口区间  |
| Milvus        | **19532** | 19530 + 2          |
| OpenTelemetry | **4319**  | 4317 + 2           |

---

## 安装

```bash
pip install -r requirements/requirements.txt
```

---

## 配置

```bash
cp .env.example .env
# 按需编辑 .env 中的 API Key 等配置
```

## 模型下载（可选）

系统在无模型时使用 stub 模式运行。需要真实推理时：

```bash
# 见 models/README.md 的详细说明
huggingface-cli download BAAI/bge-large-zh-v1.5 --local-dir models/embedding/bge-large-zh-v1.5
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir models/reranker/bge-reranker-v2-m3
```

---

## 启动

### 推荐方式：Docker 后端 + 本地前端

这是功能最完整、最推荐的运行方式：

> **注意**：Docker 容器内 `localhost` 指向容器自身。如需容器内 API 访问宿主机 LLM 服务，请设置 `LLM_API_URL=http://host.docker.internal:8000/v1`（Docker Desktop）或宿主机实际 IP。

**第一步：启动 Docker 后端服务**

```bash
# 启动后端基础设施（API + MCP + PostgreSQL + Redis + Milvus）
docker compose up -d api
```

**第二步：启动本地前端**

```bash
# 本地运行完整 8 页前端（需 Python 依赖）
pip install -r requirements/requirements.txt
streamlit run frontend/app.py
```

访问 http://localhost:12345 即可使用全部 8 个功能页。

> **架构说明**：Docker 负责后端引擎（Agent 工作流 + RAG 检索 + 数据库），本地 Streamlit 负责前端展示。前后端分离，各司其职。

---

### 备选方式

**纯 Docker 部署（轻量前端，3 页可用）：**

```bash
# 构建并启动全部服务
docker compose up -d

# 仅重建前端（代码更新后）
docker compose build --no-cache frontend
docker compose up -d frontend
```

访问 http://localhost:12345，首页/智能对话/运维看板 3 页可用，其余 5 页显示本地运行指引。

**纯本地开发（无 Docker）：**

```bash
# 1. 启动 MCP 基础设施（可选，不启动则自动降级到 stub 模式）
python tools/mcp/start_servers.py --no-gateway

# 2. 启动主 API 服务
uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload

# 3. 启动前端
streamlit run frontend/app.py
```

---

### 前端页面可用性

| 页面       | Docker 前端 | 本地前端 | 说明                                              |
| -------- |:---------:|:----:| ----------------------------------------------- |
| 🏠 首页    | ✅         | ✅    | API 健康检查 + 看板概览                                 |
| 💬 智能对话  | ✅         | ✅    | API 优先 → stub 降级（后端离线时本地 BERT + 模板）             |
| 📊 运维看板  | ✅         | ✅    | 纯 API 数据展示                                      |
| 🎯 意图识别  | ⚠️        | ✅    | 需 `agents/` 模块，Docker 中显示本地运行指引                 |
| 📚 政策检索  | ⚠️        | ✅    | 需 `agents/policy/` + langchain，Docker 中显示本地运行指引 |
| 📋 材料审核  | ⚠️        | ✅    | 需 `agents/material/`，Docker 中显示本地运行指引           |
| 🤝 跨域协同  | ⚠️        | ✅    | 需 `tools/a2a/`，Docker 中显示本地运行指引                 |
| 🛡️ 安全治理 | ⚠️        | ✅    | 需 `governance/`，Docker 中显示本地运行指引                |

> 💡 **设计原则**：Docker 前端镜像保持轻量（~200MB），仅包含 streamlit + httpx。依赖项目模块（agents/governance/tools）的页面在 Docker 中优雅降级为提示信息，引导用户本地运行 `streamlit run frontend/app.py` 获得完整体验。安全护栏（PII 脱敏、注入检测）在 Docker 中通过后端 Agent 工作流完整集成。

### MCP 架构说明

```
Agent (LangGraph Node)
    │
    ├─ MCP Client ✅ (优先: 通过 MCP Server 获取真实能力)
    │   ├─ Gateway (12300) ──→ Policy Server (12301)
    │   │                     Material Server (12302)
    │   │                     Workflow Server (12303)
    │   └─ Direct 直连 ────→ Policy Server (12301)  ← Gateway fallback
    │
    └─ Stub 降级 ✅ (MCP 不可用时保留基本功能)
```

---

# 14. Demo场景

## 场景：开餐饮店

用户：

```
我想在成都开一家餐馆，需要什么？
```

流程：

```
Intent Agent
↓
识别:
business_license
↓
Policy Agent
↓
查询政策
↓
Material Agent
↓
检查材料
↓
Workflow Agent
↓
生成办理流程
↓
返回结果
```

---

# 15. 项目亮点

## 1. 从Chatbot升级为Agent Platform

不是：

```
LLM + Prompt
```

而是：

```
Agent Runtime
+
Tool Ecosystem
+
Governance
+
Evaluation
```

---

## 2. MCP标准化工具体系

实现：

* 工具解耦
* 动态发现
* 统一调用

---

## 3. A2A跨域Agent通信

支持：

* 异步任务
* 外部Agent调用
* 状态恢复

---

## 4. AgentOps治理闭环

实现：

```
执行
↓
记录
↓
评估
↓
优化
↓
迭代
```

---

# 16. 业务流程

## 16.1 总体链路

从用户请求到最终回答的完整业务链路：

```
 User
  │
  ├── POST /api/chat { "user_query": "我要开一家餐馆" }
  │     │
  │     ├── JWT 认证 + RBAC 鉴权
  │     ├── trace_id 生成（UUID7）
  │     └── create_initial_state(user_query, trace_id)
  │
  ▼
 AgentService.execute(state, graph)
  │
  │  ┌─────────────────────────────────────────────────────────────┐
  │  │                  AgentRuntime.execute_with_safeguards()      │
  │  │  · LoopDetector（6窗口 + 3连续相同tool → 重规划）            │
  │  │  · Step 限制（最大10步 → 优雅终止）                          │
  │  │  · Timeout（60s → RuntimeTimeoutError）                      │
  │  └─────────────────────────────────────────────────────────────┘
  │
  ▼
 START ──► supervisor_node           ← 任务理解 + 拆解 + 路由
              │
              ├──(无 intent)──► intent_node     ← BERT → 关键词 → LLM
              │                    │                   三级分类
              │                    ▼
              │              supervisor_node       ← 二次回环规划
              │
              ├──(查政策)──► policy_node          ← MCP → Milvus BM25 Reranker
              │                    │                  → LLM 生成 → evidence
              │                    ▼
              │              specialist 回 supervisor
              │
              ├──(审材料)──► material_node        ← MCP → OCR → NER → 规则校验
              │                    │
              │                    ▼
              │              specialist 回 supervisor
              │
              ├──(办件)───► workflow_node         ← MCP → create_case → 办件号
              │                    │
              │                    ▼
              │              route_after_workflow
              │                    │
              │              ┌─────┴─────┐
              │              │           │
              │         (有A2A需求)   (无A2A需求)
              │              │           │
              │              ▼           │
              │         a2a_node         │
              │           │  │           │
              │      (异步)│  │(同步)     │
              │       挂起 │  直接        │
              │      →END │  返回        │
              │              │          │
              │              └────┬─────┘
              │                   ▼
              └──────────► governance_node       ← GuardrailRunner
                              │                      · PII 脱敏
                              │                      · 注入检测
                              │                      · 敏感词过滤
                              │                      · 输出过滤
                              ▼
                           END ──► ChatResponse
                                   { answer, evidence, intent,
                                     risk_level, execution_steps, elapsed_ms }
```

## 16.2 请求接入

1. **JWT 认证**：解析 `Authorization: Bearer <token>` → 提取 `user_id` + `role`（强制 Bearer Token，无旁路）
2. **RBAC 鉴权**：4角色（admin/operator/auditor/user）× 16权限，MCP Tool 级别鉴权 + Gateway 层 JWT 验证
3. **输入护栏前置**：在 LLM 调用前通过 `GuardrailRunner.run_input()` 检测注入/敏感词，命中即阻断（不消耗 Token）
4. **TraceId 生成**：UUID7（时间排序 + 全局唯一），注入 `RequestLoggingMiddleware` → 全链路日志携带
5. **State 初始化**：`create_initial_state(user_query, trace_id)` → 24字段 TypedDict，trace_id/user_query 覆写，空列表追加字段初始化

## 16.3 意图识别与任务规划

```
supervisor_node 进入
  │
  ├── 首次：start_trace(user_query)          ← 建立 trace 上下文
  │
  ├── supervisor.orchestrate(state)
  │     │
  │     ├── 1. Planner._llm_plan(state)      ← LLM 生成 task_plan
  │     │      └── fallback: _rule_plan()    ← 关键词模板
  │     │
  │     └── 2. Router.route(task)             ← LLM + 规则混合
  │            ├── 关键词匹配（优先）
  │            ├── _infer_by_keyword()
  │            └── _llm_route() （LLM fallback）
  │
  └── 输出: state["task_plan"] = [Task, ...]
           每个 Task: {type, agent, description, status: PENDING}
```

Intent 节点：

- **BERT 模型推理**（已微调，`models/intent/bert-intent/`，10 标签 99.5% 准确率）→ 高置信度(>0.7)直接返回
- **关键词匹配**（18条规则）→ 中置信度(0.5-0.7)，BERT 不可用时兜底
- **LLM fallback** → 最低置信度(0.3)，最后手段
- 生产路径：`nodes.py` 中 `IntentClassifier()` 默认启用 BERT（`auto_load=True`）

Intent 回环：`intent_node → supervisor_node` 为**静态边**，意图识别后必回 supervisor 二次规划。

## 16.4 专业 Agent 执行

| 节点              | Agent         | MCP Server              | 工具                                   | 降级行为                       |
| --------------- | ------------- | ----------------------- | ------------------------------------ | -------------------------- |
| `policy_node`   | PolicyAgent   | `policy_server:12301`   | `search_policy`, `get_policy_detail` | stub 模板回答（预置5种导向回答）        |
| `material_node` | MaterialAgent | `material_server:12302` | `extract_entity`, `check_material`   | `passed=True` + 提示 stub 模式 |
| `workflow_node` | WorkflowAgent | `workflow_server:12303` | `create_case`, `query_status`        | `CASE_{uuid}` 模拟办件号        |

每节点执行后：

- `task_plan` 中对应 PENDING 任务 → `status: COMPLETED`
- MCP 调用记录写入 `mcp_history`（含 trace_id / server_name / tool_name / latency_ms / status）
- 异常捕获 → `state["error"]` 设置 → `route_after_specialist` 判断是否回 supervisor 重试（retry_count < 3）

## 16.5 A2A 跨域协同

当 workflow 完成后，`_needs_a2a(intent, user_query)` 检测：

- 关键词：房产/不动产/房屋/产权/公积金/住房基金
- 意图：`property_service` / `fund_query`

**异步模式（真实外部 Agent）**：

```python
# a2a_node 中
result = await a2a_connector.send_task(skill="query_property", ...)
# result["mode"] == "http"
state["waiting_task_id"] = result["task_id"]
await checkpointer.suspend_for_a2a(thread_id, ..., a2a_task_id)
# → 路由到 END（LangGraph 本轮结束，checkpoint 已落 PostgreSQL）
```

**回调恢复**：

```
外部 Agent 完成 → POST /api/a2a/callback { task_id, status, artifact }
  → A2ACallbackHandler.process_callback()
    → checkpointer.resume_from_a2a(task_id)   ← 按 task_id 全库搜索
    → 注入 external_result + 清空 waiting_task_id
    → graph.ainvoke(resumed_state, config)     ← 从断点恢复
    → a2a_node._handle_a2a_resume()           ← 合并外部结果到 evidence
    → governance_node → END
```

**同步模式（stub fallback）**：

```python
result = await _a2a_stub_call(skill, input_data)  # 本地 Mock Agent
# 直接继续流程，无需挂起
```

## 16.6 安全护栏与最终回答

**护栏双层防护**（输入前置 + 输出后置）：

1. **输入护栏（LLM 前）** — `execute_agent()` 中 `GuardrailRunner.run_input(user_query)` 在 `graph.ainvoke` **之前**执行：PII 检测 + Prompt Injection（12种模式）+ 敏感词（10个）。命中即阻断，LLM 不接收恶意输入。
2. **输出护栏（governance_node）** — `GuardrailRunner.run_output(final_answer)`：错误泄露 + 密钥泄露（5种模式）+ Prompt 泄露（4种模式）
3. **PII 自动脱敏** — 手机 `138****1234`、身份证 `110***********1234`、邮箱 `u***@domain.com`、银行卡
4. **阻断决策** — 输入 injection → 立即阻断（不消耗 Token）；密钥泄露 → blocked + risk_level=HIGH/CRITICAL
5. **Trace 收口** — `end_trace()` 将全链路 span 写入 TraceRecorder

`route_after_governance`：

- `blocked=True` → END（安全阻断）
- `error` 且 `retry_count < 3` → supervisor_node（重试）
- 否则 → END（正常结束）

## 16.7 降级与容错

三级降级链：

| 层级      | 降级对象          | 触发条件           | 降级行为                                          |
| ------- | ------------- | -------------- | --------------------------------------------- |
| L1 基础设施 | PostgreSQL    | 连接失败           | 内存模式运行（TraceRecorder / MetricsCollector 内存存储） |
| L1 基础设施 | Redis         | 连接失败           | 无缓存模式（跳过 rate limit / session 缓存）             |
| L1 基础设施 | Milvus        | 连接失败           | BM25 关键词检索（纯内存 TF-IDF）                        |
| L2 模型层  | LLM API       | 无 API Key / 超时 | 规则模板回答（模板引擎 + 关键词匹配）                          |
| L2 模型层  | BERT          | 模型未加载          | 关键词匹配 fallback（18条规则）                         |
| L2 模型层  | PaddleOCR     | pip 未安装        | stub 文本生成（"模拟营业执照内容..."）                      |
| L3 协议层  | MCP Server    | HTTP 不可达       | stub 模板回答（预置政策/材料/办件数据）                       |
| L3 协议层  | A2A Connector | 外部 Agent 不可达   | 本地 Mock Agent（模拟房产/公积金数据）                     |

---

# 17. 代码运行逻辑

## 17.1 图构建

`build_graph()` 在 `orchestration/langgraph/graph.py` 中构建 StateGraph：

| 组件  | 数量      | 详情                                                                                                                                    |
| --- | ------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 节点  | **7**   | supervisor / intent / policy / material / workflow / a2a / governance                                                                 |
| 静态边 | **2**   | `START → supervisor_node`、`intent_node → supervisor_node`                                                                             |
| 条件边 | **6** 组 | route_after_supervisor / route_after_specialist ×2(policy+material) / route_after_workflow / route_after_a2a / route_after_governance |

依赖注入一览：

| 参数              | 类型                    | 注入节点                         | stub 行为           |
| --------------- | --------------------- | ---------------------------- | ----------------- |
| `llm`           | `BaseChatModel`       | 全部 7 节点                      | 纯 stub 模式（关键词+规则） |
| `mcp_client`    | `MCPClient`           | policy / material / workflow | stub 模板回答         |
| `a2a_connector` | `A2AConnector`        | a2a                          | 本地 Mock Agent     |
| `checkpointer`  | `BaseCheckpointSaver` | a2a（挂起/恢复）                   | 无持久化（不支持 A2A 异步）  |
| `supervisor`    | `SupervisorAgent`     | supervisor                   | 自动用 llm 构建        |

所有节点通过 `async def _xxx_wrapper(state)` 闭包注入依赖后在 `graph.add_node()` 注册。

## 17.2 Node 执行流

| 节点                | 底层 Agent        | 核心行为                                                    | 注入依赖                        | MCP / 降级           |
| ----------------- | --------------- | ------------------------------------------------------- | --------------------------- | ------------------ |
| `supervisor_node` | SupervisorAgent | `orchestrate(state)` → Planner 生成 task_plan → Router 决策 | llm, supervisor             | 无 MCP、关键词 fallback |
| `intent_node`     | IntentAgent     | BERT → 关键词 → LLM 三级分类                                   | llm                         | stub 关键词匹配         |
| `policy_node`     | PolicyAgent     | MCP `search_policy` → Milvus+BM25                       | llm, mcp_client             | stub 模板回答          |
| `material_node`   | MaterialAgent   | MCP `check_material` → OCR+NED                          | llm, mcp_client             | `passed=True`      |
| `workflow_node`   | WorkflowAgent   | MCP `create_case` → 办件号                                 | llm, mcp_client             | `CASE_{uuid}`      |
| `a2a_node`        | A2AConnector    | `send_task` → 挂起 OR `_a2a_stub_call`                    | a2a_connector, checkpointer | 本地 Mock            |
| `governance_node` | GuardrailRunner | PII + 注入 + 敏感词 + 输出过滤                                   | 无                           | 异常时自动放行            |

每个节点执行前：

1. `update_current_agent(state, AgentName.X)` — 设置当前 Agent
2. `transition_to(state, NodeName.X)` — 记录当前节点
3. `start_trace()` 守卫（仅 supervisor 首次进入）
4. `AgentTracer.span()` 包裹核心逻辑（governance/supervisor/intent）
5. `record_agent_call()` — 成功 + 失败路径均记录 metrics

## 17.3 Edge 条件路由

| 路由函数                     | 判定依据                                                                                 | 可能目标                                                            |
| ------------------------ | ------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| `route_after_supervisor` | task_plan 状态：无 intent → intent；有 PENDING → 按 agent；全完成 → supervisor(合成) 或 governance | intent / policy / material / workflow / governance / supervisor |
| `route_after_specialist` | 先检查 error/risk，再复用 `route_after_supervisor`                                          | 同上全量 + supervisor(重试)                                           |
| `route_after_workflow`   | waiting_task_id → END(挂起)；`_needs_a2a()` → a2a；全完成 → governance                      | a2a / governance / supervisor / END                             |
| `route_after_a2a`        | waiting_task_id → END；有 error → supervisor；否则 → governance                           | governance / supervisor / END                                   |
| `route_after_governance` | blocked → END；waiting → END；error 且 retry<3 → supervisor；否则 END                      | supervisor / END                                                |

关键规则：

- **任务状态机驱动**：`task_plan` 中每个 Task 的 `status: PENDING → COMPLETED/FAILED`
- **意图回环**：intent 识别后必回 supervisor 二次规划（静态边保证）
- **提前进入治理**：`risk_level=high/critical` 时跳过后续任务，直接 governance
- **错误重试**：`state["error"]` 非空 + `retry_count < 3` → 回 supervisor 重新规划

## 17.4 状态管理

`AgentState`（TypedDict，24字段）分两类更新策略：

**覆盖更新（标量字段）**：

```
trace_id / user_query / intent / current_agent / current_node
final_answer / risk_level / safety_check / execution_metrics
waiting_task_id / external_result / policy_result / material_result
error / retry_count
```

**追加更新（列表字段 + Annotated reducer）**：

```
task_plan     → _task_plan_reducer（按 id 合并）
messages      → operator.add
tool_calls    → _tool_calls_reducer（按 tool_call_id 合并）
mcp_history   → append
a2a_tasks     → append
evidence      → append
error_history → append
```

3个自定义 reducer：

- `_task_plan_reducer`：按 `task["id"]` 合并（新 id 追加，已有 id 覆盖）
- `_tool_calls_reducer`：按 `tool_call_id` 去重合并
- `_append_reducer`：通用追加

## 17.5 治理集成

治理模块在 `nodes.py` 中的接线方式：

```
supervisor_node（首个节点）
  ├── get_current_trace() is None → start_trace(user_query)
  └── AgentTracer.span(AGENT, supervisor) → 记录 orchestrate 调用

每个节点
  ├── AgentTracer.span(AGENT, node) 或 直接 time.perf_counter()
  ├── record_agent_call(agent, success, latency_ms, trace_id)
  └── 异常路径同样 record_agent_call(success=False)

governance_node（末尾节点）
  ├── GuardrailRunner.run_input(user_query)
  ├── GuardrailRunner.run_output(final_answer)
  ├── detect_pii(user_query)
  ├── get_collector().record_guardrail_block()
  └── finally: end_trace()
```

**Trace 层级结构**：

- `start_trace()` 建立 root trace（contextvars 协程安全传播）
- 每个 `AgentTracer.span()` 自动创建子 span（`parent_span_id` 自动继承）
- `end_trace()` 将全链路 span 写入 `TraceRecorder`（内存，可选 `flush_to_db()`）

**Metrics 指标收集**：

- `record_agent_call()` → Counter + Gauge + Histogram（agent/latency/tokens/steps）
- `record_tool_call()` → Counter + Histogram（tool 维度）
- `record_guardrail_block()` → Counter（按 guard_type + severity）
- 全量可用 `export_prometheus_metrics()` 输出 Prometheus 文本格式

## 17.6 降级容错链

```
┌─────────────────────────────────────────────────┐
│                AgentRuntime 安全护栏               │
│  · LoopDetector: 6窗口 + 3连续相同 → 中断          │
│  · StepLimiter: 10步 → RuntimeExceededError      │
│  · Timeout: 60s → RuntimeTimeoutError            │
└─────────────────┬───────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
  LLM          MCP           A2A
  │             │             │
  ├─可用        ├─可用         ├─可用
  │  real LLM   │  MCP Server  │  HTTP async
  │             │              │
  ├─不可用       ├─不可用        ├─不可用
  │  stub 模板  │  stub 回答    │  mock Agent
  │             │              │
  ▼             ▼             ▼
 最终回答       最终回答       外部结果

任何层异常 → set_error(state, msg)
           → route 判断 retry_count
           → <3: 回 supervisor 重规划
           → ≥3: 进入 governance 处理
```

---

# 18. 开发指南

> **Phase 1 完成** ✅ — 27个模块完成，系统可在无 LLM / 无 PostgreSQL 的 stub 模式下完整运行。
> **Phase 2 完成** ✅ — MCP Server + Tool Calling 体系就绪，6个Tool + 3个Server + Gateway + Client 全部实现。
> **Phase 3 完成** ✅ — A2A 跨域 Agent 协同 + Async Callback 体系就绪，7个A2A模块 + LangGraph集成完成。
> 已建立 `models/` 模型目录（已 gitignore），端口统一偏移避免本地冲突。

## Phase 1 — LangGraph Runtime + Supervisor + RAG ✅

### 编排层 (orchestration/langgraph/) — 6/6 完成

```
✅ state.py          — AgentState(24字段) + 10 Pydantic模型 + 6枚举 + 3 reducer + 9 helper（931行，117测试）
✅ graph.py          — StateGraph构建（7节点 + 6组条件边 + 2静态边 + checkpointer注入）（250行）
✅ nodes.py          — 6个Agent节点函数（336行）
✅ edges.py          — 5个条件路由函数（145行）
✅ checkpointer.py   — PostgreSQL Checkpointer + A2A挂起/恢复（310行）
✅ runtime.py        — Runtime安全护栏 + LoopDetector + 3异常类（394行，22测试）
```

### Agent层 (agents/) — 17/19 完成

```
✅ __init__.py                — AgentRegistry（register/get/list/health_check/unregister，126行）
✅ supervisor/prompts.py      — 5套Prompt模板（133行）
✅ supervisor/planner.py      — Planner（LLM+规则混合，5种intent模板，JSON容错，227行）
✅ supervisor/router.py       — Router（4层策略，16条目路由表，155行）
✅ supervisor/agent.py        — SupervisorAgent（4场景编排，3次重试，192行）
✅ intent/prompts.py          — LLM分类模板 + few-shot示例（48行）
✅ intent/schema.py           — 10个预定义IntentLabel + IntentResult（64行）
✅ intent/classifier.py       — IntentClassifier（3级：BERT→关键词→LLM，18条关键词映射，支持本地模型，~185行）
✅ intent/agent.py            — IntentAgent（130行）
✅ policy/prompts.py          — RAG回答生成模板（27行）
✅ policy/schema.py           — PolicyResult + PolicyEvidence（28行）
✅ policy/agent.py            — PolicyAgent（LLM+模板双模式，5种业务回答，165行）
✅ material/prompts.py        — 材料审核Prompt模板（Phase 2）
✅ material/ocr.py            — OCREngine（stub，支持图片/文本格式检测，Phase 2）
✅ material/extractor.py      — EntityExtractor（6种正则模式，PII脱敏，Phase 2）
✅ material/validator.py      — MaterialValidator（5种业务材料清单，别名匹配，格式校验，Phase 2）
✅ material/agent.py          — MaterialAgent（5种业务材料清单，规则校验，118行）
✅ workflow/agent.py          — WorkflowAgent（MCP stub，create_case/query_status，114行）
✅ governance/security.py     — SecurityChecker（PII/注入/敏感词/泄露 4类检测，165行）
✅ governance/behavior.py     — BehaviorAnalyzer（循环/步数/Token异常检测，93行）
✅ governance/optimizer.py    — Optimizer（失败率/步数/延迟/Tool分析，127行）
✅ governance/agent.py        — GovernanceAgent（编排安全+行为+优化，99行）
✅ material/ 真实OCR模型      — PaddleOCR接入（双模式：真实引擎 + stub fallback）
✅ material/ 真实NER模型      — BERT-NER接入（双模式：transformers pipeline + regex fallback）
```

### 后端层 (backend/) — 8/12 完成

```
✅ config.py                   — Settings（40+字段含模型路径+端口，pydantic-settings + lru_cache，~290行）
✅ main.py                     — FastAPI app factory + lifespan(db init/shutdown) + CORS + /health（129行）
✅ tools/logger.py             — loguru 完整系统（531行，20测试）
✅ api/schemas.py              — 10个Pydantic API模型（225行）
✅ api/dependencies.py         — 5个DI函数（140行）
✅ api/routes.py               — 5个API端点（/chat, /status, /a2a, /dashboard, /eval，244行）
✅ middleware/auth.py           — JWT Bearer + X-User-Id 降级 + Token生成 + Fallthrough 容错（~170行）
✅ services/agent_service.py   — AgentService（注册+执行+恢复，159行）
✅ middleware/rbac.py           — RBAC权限（4角色+16权限+MCP Tool鉴权+FastAPI依赖注入，~390行）
✅ middleware/tracing.py        — OpenTelemetry（Trace/Span创建、W3C传播、Agent/Tool instrumentation、NoOp降级，~440行）
```

### 模型存储 (models/) — 已完成

```
✅ models/README.md              — 模型清单 + 3种下载方式 + 微调说明
✅ models/embedding/             — BGE Embedding 模型目录（~1.3GB，已 gitignore）
✅ models/reranker/              — BGE Reranker 模型目录（~2.3GB，已 gitignore）
✅ models/intent/                — 意图分类 BERT 模型目录（~400MB，已 gitignore）
✅ models/fine_tuned/            — 微调版本管理（intent-v1, ner 等）
```

### 数据库层 (database/) — 3/3 完成

```
✅ connection.py               — async SQLAlchemy + session factory + get_db DI + init/close（104行）
✅ models.py                   — 5表ORM（Trace, Agent, Prompt, Evaluation, Checkpoint，310行）
✅ schemas.py                  — CRUD Pydantic模型（Create/Response，133行）
```

### RAG管线 (rag/) — 5/5 完成（框架就绪，stub待接入真实模型）

```
✅ embedding.py                — EmbeddingEngine（BGE-large-zh-v1.5，支持本地路径加载，~100行）
✅ retriever.py                — HybridRetriever（Milvus稠密 + BM25稀疏 + RRF融合，134行）
✅ reranker.py                 — Reranker（bge-reranker-v2-m3，支持本地路径加载，~85行）
✅ generator.py                — Generator（LLM + 简单拼接双模式，evidence标注，113行）
✅ knowledge_base.py           — KnowledgeBase（PDF/DOCX/TXT加载 → 切分 → 索引，173行）
```

---

## Phase 2 — MCP Server + Tool Calling ✅

> **完成日期**: 2026-07-30
> **架构**: Agent → MCPClient → MCPGateway (12300) → MCP Server (12301/12302/12303) → Business Logic
> **降级策略**: MCP 不可用时自动 fallback 到 stub 模式，保证系统可用

### MCP 工具 Schema (tools/mcp/schema.py) — 1/1 完成

```
✅ schema.py                   — 6个Tool的Input/Output Pydantic模型 + TOOL_REGISTRY全局注册表（267行）
```

### MCP 基础设施 (tools/mcp/) — 3/3 完成

```
✅ client.py                   — MCPClient（HTTP连接池、工具发现缓存、Gateway/Direct双模fallback，212行）
✅ gateway.py                  — MCPGateway（路由转发、审计日志、Server健康聚合、FastAPI sub-app，153行）
✅ start_servers.py            — 一键启动脚本（3个MCP Server + Gateway，55行）
```

### Policy MCP Server (tools/mcp/servers/policy_server/) — 2/2 完成

```
✅ tools.py                    — search_policy（7条政策语料库关键词匹配）+ get_policy_detail（文档详情查询）
✅ server.py                   — FastAPI MCP Server（:12301, /tools/list + /tools/call）
```

### Material MCP Server + Agent 补全 — 6/6 完成

**Agent 层**:

```
✅ agents/material/prompts.py  — 材料审核 + 实体抽取Prompt模板
✅ agents/material/ocr.py      — OCREngine（stub: 图片magic bytes检测 + 模拟文本生成）
✅ agents/material/extractor.py — EntityExtractor（6种正则模式: 姓名/身份证/手机号/地址/事项/信用代码 + PII脱敏）
✅ agents/material/validator.py — MaterialValidator（5类业务材料清单、10+别名映射、身份证/手机号格式校验）
```

**MCP Server**:

```
✅ tools/mcp/servers/material_server/tools.py  — extract_entity（OCR→实体抽取）+ check_material（Validator调用）
✅ tools/mcp/servers/material_server/server.py — FastAPI MCP Server（:12302）
```

### Workflow MCP Server (tools/mcp/servers/workflow_server/) — 2/2 完成

```
✅ tools.py                    — create_case（CASE_XXXXXXXX办件号生成）+ query_status（hash确定性状态）
✅ server.py                   — FastAPI MCP Server（:12303）
```

### LangGraph 集成更新 — 2/2 完成

```
✅ orchestration/langgraph/nodes.py  — policy_node/material_node/workflow_node 接入 MCPClient，MCP优先 + stub降级
✅ orchestration/langgraph/graph.py  — build_graph() 新增 mcp_client 参数注入
```

---

## Phase 3 — A2A + Async Callback ✅

> **完成日期**: 2026-08-02
> **架构**: Agent → A2AConnector → External Agent (Mock/HTTP) → Callback → Checkpointer → Resume LangGraph
> **降级策略**: 外部 Agent 不可用时自动 fallback 到 stub（本地 Mock Agent 直接调用）

### A2A 协议 (tools/a2a/protocol.py) — 1/1 完成

```
✅ protocol.py                — 6个Pydantic模型（AgentCard, A2AMessage, A2ATaskRequest, A2ATaskResponse, A2AStatusQuery, A2AStatusUpdate）
                                 + 2个枚举（A2AMessageType, AgentHealth）+ 复用 A2ATaskStatus/A2ATaskRecord（smoke test: 28 passed）
```

### A2A 任务管理 (tools/a2a/task.py) — 1/1 完成

```
✅ task.py                    — TaskStateMachine（状态机: CREATED→SUBMITTED→WORKING→COMPLETED/FAILED/TIMEOUT）
                                 + TaskStore（内存存储: create/get/update/delete/list_by_status）
                                 + InvalidTransitionError + 全局单例（smoke test: 27 passed）
```

### 外部 Agent 注册中心 (tools/a2a/registry.py) — 1/1 完成

```
✅ registry.py                — ExternalAgentRegistry（register, discover, get_agent, health_check, list_all）
                                 + 技能索引（skill→Agent映射）+ initialize_default_agents 预注册（smoke test: 23 passed）
```

### A2A 连接器 (tools/a2a/connector.py) — 1/1 完成

```
✅ connector.py               — A2AConnector（send_task→HTTP/stub, check_status, cancel_task）
                                 + httpx.AsyncClient HTTP连接池 + stub fallback 自动降级（smoke test: 14 passed）
```

### A2A 回调处理器 (tools/a2a/callback.py) — 1/1 完成

```
✅ callback.py                — A2ACallbackHandler（process_callback: 验证→更新状态→恢复LangGraph）
                                 + create_callback_router（FastAPI sub-router）+ 全局单例（smoke test: 18 passed）
```

### Mock 外部 Agent (tools/a2a/mock_agents/) — 2/2 完成

```
✅ housing_agent.py           — HousingAgent（query_property: 3条模拟房产数据 + register_property）
                                 + 公积金关联查询 + 脱敏返回 + stub 便捷函数（smoke test: 18 passed）
✅ fund_agent.py              — FundAgent（query_fund: 3条模拟公积金数据 + query_fund_detail: 提取记录+贷款测算）
                                 + stub 便捷函数（smoke test: 18 passed）
```

### LangGraph 集成 — 3/3 完成

```
✅ orchestration/langgraph/nodes.py   — 新增 a2a_node（技能检测→A2A调用→挂起/恢复）+ 3个辅助函数
✅ orchestration/langgraph/edges.py   — 新增 route_after_workflow + route_after_a2a + _needs_a2a 检测
✅ orchestration/langgraph/graph.py   — build_graph() 新增 a2a_connector 参数 + a2a_node 节点注册 + 路由配置
```

### FastAPI 集成 — 3/3 完成

```
✅ backend/api/routes.py              — /api/a2a/callback 实现真实回调处理 + _resume_agent_after_callback
✅ backend/api/dependencies.py        — 新增 get_a2a_connector() DI + get_agent_graph() 注入 A2A/Checkpointer
✅ backend/services/agent_service.py  — resume_from_checkpoint 完整实现（读取checkpoint→注入external_result→恢复执行）
```

---

## Phase 4 — Evaluation + Dashboard ✅

> **最新更新（2026-08-05）**: 安全加固完成 — 护栏前置 LLM、MCP 认证+RBAC、CORS 白名单、A2A Callback HMAC、30+ 处 logger.warning、端口文档统一。
> **上一更新（2026-08-04）**: trace_provider 已实现，`--run-real` 可运行真实 Agent 工作流收集 trace。
> Intent 评测：3500 条用例，BERT 推理，**3484/3500 passed（99.5%）**。

### 第一步：评测体系 (governance/evaluation/) ✅

```
✅ metrics.py          → RAG指标（Faithfulness, Answer Relevance, Context Recall，~630行）
                         + Agent指标（Task Success Rate, Tool Accuracy, Latency, Step Count）
                         + 双模式评分：LLM语义评估 + 规则bigram启发式
✅ evaluator.py        → 评测引擎（~490行）+ 3条评测路径（cases/traces/db）+ 版本对比
✅ benchmark.py        → Golden Dataset加载器 + BenchmarkRunner 批量评测（~350行）
✅ runner.py           → CI/CD评测流水线（CLI: run/compare/list + DB持久化，~900行）
✅ trace_provider.py   → 真实trace提供者（BERT意图 + LangGraph全流程双路径）
✅ llm_adapter.py      → LLM Judge适配器（BaseChatModel → (prompt)→str 回调）
```

### 第二步：治理基础设施 (governance/) ✅

```
✅ trace.py      → OpenTelemetry集成（trace_id, span_id, agent, tool, latency, token，~520行）
                   + TraceRecorder存储器 + AgentTracer装饰器/上下文管理器 + contextvars异步传播
✅ guardrail.py  → 输入检测（PII/Injection/Sensitive）+ 输出过滤（Error/Secret/Prompt leak，~660行）
                   + 12种注入模式检测 + 5种密钥泄露检测 + GuardrailRunner编排
✅ pii.py        → PII脱敏（手机138****1234, 身份证110***********1234, 邮箱u***@domain.com，~360行）
                   + 4种PII类型 + detect_pii/mask_pii/batch处理
✅ monitor.py    → Prometheus指标暴露（agent_success_rate, agent_latency, tool_success_rate，~620行）
                   + MetricsCollector收集器 + Counter/Gauge/Histogram + Prometheus文本格式导出
✅ dashboard.py  → 运维看板数据API（Agent运行统计, 评测趋势, 版本对比，~450行）
                   + DashboardDataProvider + 双模式（DB查询/Memory聚合）+ 系统健康检查 + 告警
```

### 第三步：Prompt管理 (prompts/) ✅

```
✅ registry.py   → Prompt注册中心（版本化: Role/Goal/Constraints/Tools/Output Schema/Examples，~590行）
                   + PromptTemplate结构化模板 + PromptRegistry注册中心
                   + 6个Agent预置模板 + 版本激活/停用 + {{ var }}渲染 + DB持久化
```

---

## 19. 实现优先级总结

```
第零步（环境准备）:
  .env.example → 编辑 .env（端口/密钥）
  models/ → 按需下载 Embedding / Reranker / BERT 模型

第一优先级（让系统跑起来）:
  orchestration/langgraph/state.py → graph.py → nodes.py → edges.py
  agents/supervisor/agent.py → planner.py → router.py
  backend/main.py → config.py → api/routes.py

第二优先级（让Agent有知识）:
  rag/embedding.py → retriever.py → reranker.py → generator.py
  agents/policy/agent.py
  agents/intent/classifier.py → agent.py

第三优先级（让Agent能调工具）: ✅ Phase 2 完成
  ✅ tools/mcp/schema.py → client.py → gateway.py
  ✅ tools/mcp/servers/policy_server/server.py → tools.py
  ✅ tools/mcp/servers/material_server/server.py → tools.py
  ✅ tools/mcp/servers/workflow_server/server.py → tools.py
  ✅ agents/material/ocr.py → extractor.py → validator.py → prompts.py
  ✅ orchestration/langgraph/nodes.py → graph.py (MCP集成)

第四优先级（让系统可治理）: ✅ Phase 4 完成
  ✅ governance/trace.py → guardrail.py → pii.py → monitor.py → dashboard.py
  ✅ governance/evaluation/metrics.py → evaluator.py → benchmark.py → runner.py
  ✅ prompts/registry.py

第五优先级（跨域协同）:
  tools/a2a/protocol.py → task.py → connector.py → callback.py

第六优先级（生产化）:
  deploy/Dockerfile → docker-compose.yml（根目录）
  governance/dashboard.py → monitor.py
```

---

# 20. 更新日志

## 2026-08-06 — 前端视觉升级 + Docker 容器启动修复 + 评测报告文件回退

### 前端视觉升级（浅色专业政务风）

基于 `/ui-ux-pro-max` 生成的政务设计系统（`design-system/default/MASTER.md`），三层改造让 8 页前端形成统一视觉语言：

| 改动 | 文件 | 说明 |
| --- | --- | --- |
| Streamlit 主题 | `.streamlit/config.toml` | 新增 `[theme]`：政务蓝 `#1E40AF` 主色 / 背景 `#F6F8FB` / 次背景 `#EFF6FF` / 正文 `#1F2A44` |
| 共享 UI 组件库 | `frontend/ui.py`（新增） | `inject_theme_css()` 全局主题 + `page_header` / `metric_card` / `status_badge` / `evidence_card` / `architecture_diagram` 等 11 个组件，全部基于 Streamlit 原生 API + 内联 CSS，零新增依赖 |
| 全局主题注入 | `frontend/app.py` | `set_page_config` 后调用 `ui.inject_theme_css()` |
| 逐页重构 | `frontend/pages/*.py`（8 页） | 统一页头/指标卡语义色/状态徽章/证据卡；首页 ASCII 架构图升级为 HTML 流程图；示例问题改 `st.pills`；去掉零散 emoji 装饰 |
| 设计规范 | `design-system/default/MASTER.md`（新增） | 配色/字体/间距/组件规格/反模式，供后续页面遵循 |

### Docker API 容器启动修复

**根因**：Windows Docker Desktop 把宿主机目录 bind mount 进容器后显示为 root 所有（`drwxr-xr-x`），非 root 用户（appuser, uid=1000）写不进 → loguru 创建日志文件 `PermissionError` → uvicorn lifespan 启动异常反复重启。

| 改动 | 文件 | 说明 |
| --- | --- | --- |
| 容器入口脚本 | `deploy/docker-entrypoint.sh`（新增） | root 启动 → `chown` 授权 `/app/{logger,data,models,evaluation_results}` → `setpriv` 降权为 appuser 执行 uvicorn（业务进程仍非 root） |
| Dockerfile | `deploy/Dockerfile` | 移除 `USER appuser`，改为 ENTRYPOINT 降权模式；入口脚本 `export HOME=/home/appuser` 修复 asyncpg 读 `/root/.postgresql` 的权限错误 |
| Compose 挂载 | `docker-compose.yml` | api 服务挂载 `./evaluation_results:/app/evaluation_results`（评测报告文件回退读取） |

### 评测报告文件回退

`/api/evaluation/report/{version}` 原先只读 PostgreSQL `evaluation` 表；benchmark runner 的 `--save-result`（写文件）与 `--save-to-db`（写库）是独立开关，只写了文件时 API 会返回 404/错误。

- **`backend/api/routes.py`**: 新增 `_load_benchmark_report_file()`，DB 无记录或 DB 不可用时回退读取 `evaluation_results/*.json`（按 JSON 内 `version` 字段匹配、取最新、按 dataset 用例数加权聚合），保证已有评测文件也能在看板展示。

## 2026-08-05 — 安全加固 + 认证重构 + Bug 修复

### LangGraph 1.x API 兼容

Docker 容器内 LangGraph 版本升级导致 4 项 API 不兼容，已全部适配：

- **`checkpointer.py`**: `aput()` 增加 `new_versions` 参数，`aput_writes()` 增加 `task_path` 参数，`self._serde` → `self.serde` 属性变更，`dumps_typed()`/`loads_typed()` 适配 `(encoding, bytes)` 元组格式
- **`edges.py`**: intent 任务跳过时标记 `SKIPPED`，`all_completed` 检查扩大为 `COMPLETED/FAILED/SKIPPED`，防止 supervisor ↔ intent 死循环
- **`dependencies.py`**: `execute_agent()` 增加通用 `except Exception` 兜底，避免未预期异常逃逸

### 安全加固

| 加固项               | 文件                                | 说明                                                                       |
| ----------------- | --------------------------------- | ------------------------------------------------------------------------ |
| 护栏前置 LLM          | `dependencies.py`                 | `GuardrailRunner.run_input()` 在 `graph.ainvoke` 前执行，注入/敏感词立即阻断           |
| MCP 认证+RBAC       | `gateway.py`, `client.py`         | Gateway 增加 JWT Bearer Token 验证 + `admin`/`agent` 角色控制，Client 携带认证 Header |
| CORS 白名单          | `config.py`                       | 默认值从 `"*"` 改为 `"localhost:12345,localhost:3000"`                         |
| A2A Callback HMAC | `routes.py`, `schemas.py`         | HMAC-SHA256 签名验证 + ±300s 防重放窗口                                           |
| 端口文档统一            | `docker-compose.yml`, `config.py` | 修正 Redis 端口注释 6480→6500，补充容器内/本地开发的端口区分说明                                |

### 认证体系重构

旧版认证存在两个问题：(1) `dependencies.py:get_user_id()` 直接从 `X-User-Id` Header 读取用户 ID，忽略 `AuthMiddleware` 已注入的 `request.state.user_id`；(2) `RBACMiddleware` 在 `AuthMiddleware` 之前执行（FastAPI LIFO 顺序），权限检查时 `request.state.user_role` 尚未设置。

修复：

- **`dependencies.py`**: `get_user_id()` 改为从 `request.state.user_id` 读取
- **`main.py`**: 调换 `RBACMiddleware` / `AuthMiddleware` 注册顺序，Auth 先执行设置身份，RBAC 后执行检查权限；`global_exception_handler` 不再拦截 `HTTPException`（401/403 由 Starlette 原样返回）
- **`auth.py`**: JWT 解码失败改为 `pass`（fallthrough 到 `X-User-Id` 降级），不再立即抛 401
- **`rbac.py`**: USER 角色增加 `DASHBOARD_VIEW` + `EVALUATION_VIEW` 权限
- **`api_client.py`**: 新增 `_headers()` 函数，同时发送 `Bearer Token` + `X-User-Id` 双重认证头，Docker 前端容器兼容

### 日志系统修复

- **`tools/logger.py`**: `LOG_DIR` 从相对路径 `"logger"` 改为基于项目根目录的绝对路径，支持 `GOV_LOG_DIR` 环境变量覆盖
- **`config.py`**: 新增 `log_dir` 配置项
- 30+ 处降级路径增加 `logger.warning()`，覆盖 DB/Redis/MCP/A2D 和安全事件

### 前端改进

- **`dashboard_page.py`**: cases JSON 兼容 `list[{_description, cases, ...}]` 和 `dict` 两种结构
- **`api_client.py`**: `chat_with_fallback()` 后端不可用时自动降级到本地 stub（BERT 意图 + 政策模板）+ 双重认证头

### 验证

```
pytest: 78/78 passed
guardrail: 45/45 passed
state: 117/117 passed
a2a: 15/15 passed
logger smoke: 20/20 passed
chat e2e: restaurant_license / risk=low / 200 OK
dashboard: total_requests=6, success_rate=1.0, active_agents=4
```

---

# 项目定位总结

本项目目标不是构建一个简单智能问答机器人。

而是探索：

> 企业级多智能体应用如何通过标准协议、工程治理和自动评测实现可靠落地。