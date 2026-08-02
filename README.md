# government-agent-platform

# 政务多智能体协同与治理平台

> Enterprise Multi-Agent Platform based on LangGraph + MCP + A2A + AgentOps + RAG

---

<p align="center">

<img src="./docs/images/logo.png" width="160">

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

| Agent            | 职责     |
| ---------------- | ------ |
| Supervisor Agent | 全局任务规划 |
| Intent Agent     | 用户意图识别 |
| Policy Agent     | 政策知识检索 |
| Material Agent   | 材料审核   |
| Workflow Agent   | 流程执行   |
| Governance Agent | 安全治理   |

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

        v                 v                v


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

MCP Client

↓

MCP Gateway

↓

MCP Server

↓

Business Service

```

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

Callback

```

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

## RAG评测

指标：

| 指标               | 说明    |
| ---------------- | ----- |
| Faithfulness     | 回答真实性 |
| Answer Relevance | 答案相关性 |
| Context Recall   | 上下文召回 |

---

## Agent评测

指标：

| 指标                | 说明      |
| ----------------- | ------- |
| Task Success Rate | 任务成功率   |
| Tool Accuracy     | 工具选择准确率 |
| Latency           | 响应耗时    |
| Step Count        | 执行步骤    |

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
│   │   ├── classifier.py             # BERT分类器
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
│       ├── evaluator.py              # 评测引擎
│       ├── metrics.py                # 指标计算
│       ├── benchmark.py              # 基准测试
│       └── runner.py                 # 评测流水线
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
│   ├── Dockerfile                    # Docker镜像
│   ├── docker-compose.yml            # Docker编排
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

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend | **12345** | Vite/Next.js 开发服务器 |
| FastAPI | **8002** | 后端 API（8000 + 2） |
| MCP Gateway | **12300** | 后续 Server 依次 +1 |
| A2A Callback | **12200** | 后续 Connector 依次 +1 |
| PostgreSQL | **5434** | 5432 + 2 |
| Redis | **6381** | 6379 + 2 |
| Milvus | **19532** | 19530 + 2 |
| OpenTelemetry | **4319** | 4317 + 2 |

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

**开发模式（无需 Docker）：**

```bash
# 1. 启动 MCP 基础设施（可选，不启动则自动降级到 stub 模式）
python tools/mcp/start_servers.py --no-gateway   # 仅启动 3 个 MCP Server
# 或分别启动:
python tools/mcp/servers/policy_server/server.py     # :12301
python tools/mcp/servers/material_server/server.py   # :12302
python tools/mcp/servers/workflow_server/server.py   # :12303
python tools/mcp/gateway.py                          # :12300 (Gateway)

# 2. 启动主 API 服务
uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload
```

**Docker 部署：**

```bash
docker compose up
```

**MCP 架构说明：**

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

# 16. 开发指南

> **Phase 1 完成** ✅ — 27个模块完成，系统可在无 LLM / 无 PostgreSQL 的 stub 模式下完整运行。
> **Phase 2 完成** ✅ — MCP Server + Tool Calling 体系就绪，6个Tool + 3个Server + Gateway + Client 全部实现。
> **Phase 3 完成** ✅ — A2A 跨域 Agent 协同 + Async Callback 体系就绪，7个A2A模块 + LangGraph集成完成。
> 已建立 `models/` 模型目录（已 gitignore），端口统一偏移避免本地冲突。

## Phase 1 — LangGraph Runtime + Supervisor + RAG ✅

### 编排层 (orchestration/langgraph/) — 6/6 完成

```
✅ state.py          — AgentState(24字段) + 10 Pydantic模型 + 7枚举 + 3 reducer + 14 helper（931行，117测试）
✅ graph.py          — StateGraph构建（6节点 + 5组条件边 + checkpointer注入）（175行）
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
⏳ material/ 真实OCR模型      — PaddleOCR接入（待Phase 3）
⏳ material/ 真实NER模型      — BERT-NER接入（待Phase 3）
```

### 后端层 (backend/) — 8/12 完成

```
✅ config.py                   — Settings（40+字段含模型路径+端口，pydantic-settings + lru_cache，~290行）
✅ main.py                     — FastAPI app factory + lifespan(db init/shutdown) + CORS + /health（129行）
✅ tools/logger.py             — loguru 完整系统（531行，20测试）
✅ api/schemas.py              — 10个Pydantic API模型（225行）
✅ api/dependencies.py         — 5个DI函数（140行）
✅ api/routes.py               — 5个API端点（/chat, /status, /a2a, /dashboard, /eval，244行）
✅ middleware/auth.py           — JWT + Bearer + X-User-Id + Token生成（155行）
✅ services/agent_service.py   — AgentService（注册+执行+恢复，159行）
⏳ middleware/rbac.py           — RBAC权限（待Phase 2）
⏳ middleware/tracing.py        — OpenTelemetry（待Phase 3）
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

## Phase 4 — Evaluation + Dashboard ⏳

### 第一步：评测体系 (governance/evaluation/)

```
governance/evaluation/metrics.py   → RAG指标（Faithfulness, Answer Relevance, Context Recall）
                                      + Agent指标（Task Success Rate, Tool Accuracy, Latency, Step Count）
governance/evaluation/evaluator.py → 评测引擎（加载trace → 计算指标 → 生成报告）
governance/evaluation/benchmark.py  → 加载Golden Dataset（cases/*.json）→ 运行Agent → 对比预期
governance/evaluation/runner.py     → CI/CD评测流水线（push触发 → 跑benchmark → 生成报告）
```

### 第二步：治理基础设施 (governance/)

```
governance/trace.py      → OpenTelemetry集成（trace_id, span_id, agent, tool, latency, token）
governance/guardrail.py  → 输入检测（PII/Injection/Sensitive）+ 输出过滤（Error/Secret/Prompt leak）
governance/pii.py        → PII脱敏（手机138****1234, 身份证110***********1234, 邮箱u***@domain.com）
governance/monitor.py    → Prometheus指标暴露（agent_success_rate, agent_latency, tool_success_rate）
governance/dashboard.py  → 运维看板数据API（Agent运行统计, 评测趋势, 版本对比）
```

### 第三步：Prompt管理 (prompts/)

```
prompts/registry.py → Prompt注册中心（版本化: Role/Goal/Constraints/Tools/Output Schema/Examples）
```

---

## 17. 实现优先级总结

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

第四优先级（让系统可治理）: ⏳ Phase 3-4
  governance/trace.py → guardrail.py → pii.py
  governance/evaluation/metrics.py → evaluator.py → benchmark.py

第五优先级（跨域协同）:
  tools/a2a/protocol.py → task.py → connector.py → callback.py

第六优先级（生产化）:
  deploy/Dockerfile → docker-compose.yml
  governance/dashboard.py → monitor.py
```

---

# 18. License

MIT License

---

# 项目定位总结

本项目目标不是构建一个简单智能问答机器人。

而是探索：

> 企业级多智能体应用如何通过标准协议、工程治理和自动评测实现可靠落地。