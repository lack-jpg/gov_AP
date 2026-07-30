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
│   │   ├── __init__.py               # 包初始化
│   │   ├── client.py                 # MCP客户端
│   │   ├── gateway.py                # MCP网关(鉴权/审计)
│   │   ├── schema.py                 # Tool Schema定义
│   │   └── servers/                  # MCP Server
│   │       ├── policy_server/        # 政策查询服务
│   │       │   ├── server.py         # Server入口
│   │       │   └── tools.py          # search_policy/get_policy_detail
│   │       ├── material_server/      # 材料审核服务
│   │       │   ├── server.py         # Server入口
│   │       │   └── tools.py          # extract_entity/check_material
│   │       └── workflow_server/      # 流程执行服务
│   │           ├── server.py         # Server入口
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

---

## 安装

```bash
pip install -r requirements/requirements.txt
```

---

## 配置

复制：

```bash
cp .env.example .env
```

---

## 启动

```bash
docker compose up
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

> **Phase 1 完成** ✅ — 26个文件实现，11个模块支持，65个文件待Phase 2/3/4。
> 系统可在无 LLM / 无 PostgreSQL 的 stub 模式下完整运行。

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

### Agent层 (agents/) — 13/19 完成

```
✅ __init__.py                — AgentRegistry（register/get/list/health_check/unregister，126行）
✅ supervisor/prompts.py      — 5套Prompt模板（133行）
✅ supervisor/planner.py      — Planner（LLM+规则混合，5种intent模板，JSON容错，227行）
✅ supervisor/router.py       — Router（4层策略，16条目路由表，155行）
✅ supervisor/agent.py        — SupervisorAgent（4场景编排，3次重试，192行）
✅ intent/prompts.py          — LLM分类模板 + few-shot示例（48行）
✅ intent/schema.py           — 10个预定义IntentLabel + IntentResult（64行）
✅ intent/classifier.py       — IntentClassifier（3级：BERT→关键词→LLM，18条关键词映射，169行）
✅ intent/agent.py            — IntentAgent（130行）
✅ policy/prompts.py          — RAG回答生成模板（27行）
✅ policy/schema.py           — PolicyResult + PolicyEvidence（28行）
✅ policy/agent.py            — PolicyAgent（LLM+模板双模式，5种业务回答，165行）
✅ material/agent.py          — MaterialAgent（5种业务材料清单，规则校验，118行）
✅ workflow/agent.py          — WorkflowAgent（MCP stub，create_case/query_status，114行）
✅ governance/security.py     — SecurityChecker（PII/注入/敏感词/泄露 4类检测，165行）
✅ governance/behavior.py     — BehaviorAnalyzer（循环/步数/Token异常检测，93行）
✅ governance/optimizer.py    — Optimizer（失败率/步数/延迟/Tool分析，127行）
✅ governance/agent.py        — GovernanceAgent（编排安全+行为+优化，99行）
⏳ material/ocr.py            — OCR引擎（待Phase 2）
⏳ material/extractor.py      — 实体抽取（待Phase 2）
⏳ material/validator.py      — 规则校验（待Phase 2）
```

### 后端层 (backend/) — 8/12 完成

```
✅ config.py                   — Settings（30+字段，pydantic-settings + lru_cache，236行）
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

### 数据库层 (database/) — 3/3 完成

```
✅ connection.py               — async SQLAlchemy + session factory + get_db DI + init/close（104行）
✅ models.py                   — 5表ORM（Trace, Agent, Prompt, Evaluation, Checkpoint，310行）
✅ schemas.py                  — CRUD Pydantic模型（Create/Response，133行）
```

### RAG管线 (rag/) — 5/5 完成（框架就绪，stub待接入真实模型）

```
✅ embedding.py                — EmbeddingEngine（BGE-large-zh-v1.5，78行）
✅ retriever.py                — HybridRetriever（Milvus稠密 + BM25稀疏 + RRF融合，134行）
✅ reranker.py                 — Reranker（bge-reranker-v2-m3，66行）
✅ generator.py                — Generator（LLM + 简单拼接双模式，evidence标注，113行）
✅ knowledge_base.py           — KnowledgeBase（PDF/DOCX/TXT加载 → 切分 → 索引，173行）
```

---

## Phase 2 — MCP Server + Tool Calling ⏳

```
⏳ tools/mcp/client.py                         — MCP Client（tools/list → tools/call）
⏳ tools/mcp/gateway.py                        — MCP Gateway（鉴权/限流/审计/路由）
⏳ tools/mcp/schema.py                         — Tool JSON Schema定义
⏳ tools/mcp/servers/policy_server/server.py   — Policy MCP Server
⏳ tools/mcp/servers/policy_server/tools.py    — search_policy + get_policy_detail
⏳ tools/mcp/servers/material_server/server.py — Material MCP Server
⏳ tools/mcp/servers/material_server/tools.py  — extract_entity + check_material
⏳ tools/mcp/servers/workflow_server/server.py — Workflow MCP Server
⏳ tools/mcp/servers/workflow_server/tools.py  — create_case + query_status
⏳ agents/material/ocr.py                      — OCR引擎
⏳ agents/material/extractor.py                — 实体抽取
⏳ agents/material/validator.py                — 规则校验
```

---

## Phase 2 — MCP Server + Tool Calling

### 第一步：MCP基础设施 (tools/mcp/)

```
tools/mcp/schema.py                                 → Tool JSON Schema（search_policy, get_policy_detail, extract_entity...）
tools/mcp/gateway.py                                → MCP Gateway（鉴权/限流/审计/路由）
tools/mcp/client.py                                  → MCP Client（tools/list → tools/call）
tools/mcp/servers/policy_server/tools.py              → search_policy + get_policy_detail实现
tools/mcp/servers/policy_server/server.py             → Policy MCP Server启动
tools/mcp/servers/material_server/tools.py            → extract_entity + check_material实现
tools/mcp/servers/material_server/server.py           → Material MCP Server启动
tools/mcp/servers/workflow_server/tools.py            → create_case + query_status实现
tools/mcp/servers/workflow_server/server.py           → Workflow MCP Server启动
```

---

## Phase 3 — A2A + Async Callback

### 第一步：A2A基础设施 (tools/a2a/)

```
tools/a2a/protocol.py                              → Agent Card, Task定义, 消息格式
tools/a2a/task.py                                   → Task状态机（created→submitted→working→completed/failed）
tools/a2a/registry.py                               → Agent注册中心（register, discover, health_check）
tools/a2a/connector.py                              → A2A Connector（send_task, check_status）
tools/a2a/callback.py                               → Callback API（接收外部Agent结果, 恢复LangGraph）
tools/a2a/mock_agents/housing_agent.py              → 模拟不动产Agent
tools/a2a/mock_agents/fund_agent.py                 → 模拟公积金Agent
```

---

## Phase 4 — Evaluation + Dashboard

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

## 18. 实现优先级总结

```
第一优先级（让系统跑起来）:
  orchestration/langgraph/state.py → graph.py → nodes.py → edges.py
  agents/supervisor/agent.py → planner.py → router.py
  backend/main.py → config.py → api/routes.py

第二优先级（让Agent有知识）:
  rag/embedding.py → retriever.py → reranker.py → generator.py
  agents/policy/agent.py
  agents/intent/classifier.py → agent.py

第三优先级（让Agent能调工具）:
  tools/mcp/client.py → gateway.py
  tools/mcp/servers/policy_server/server.py → tools.py

第四优先级（让系统可治理）:
  governance/trace.py → guardrail.py → pii.py
  governance/evaluation/metrics.py → evaluator.py → benchmark.py

第五优先级（跨域协同）:
  tools/a2a/protocol.py → task.py → connector.py → callback.py

第六优先级（生产化）:
  deploy/Dockerfile → docker-compose.yml
  governance/dashboard.py → monitor.py
```

---

# 19. License

MIT License

---

# 项目定位总结

本项目目标不是构建一个简单智能问答机器人。

而是探索：

> 企业级多智能体应用如何通过标准协议、工程治理和自动评测实现可靠落地。