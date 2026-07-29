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

## Phase 1 — LangGraph Runtime + Supervisor + RAG

### 第一步：核心状态和编排 (orchestration/langgraph/)

```
orchestration/langgraph/state.py       → AgentState TypedDict（trace_id, user_query, intent, task_plan, messages...）
orchestration/langgraph/graph.py       → StateGraph构建（add_node, add_edge, add_conditional_edges）
orchestration/langgraph/nodes.py       → 6个Agent节点函数（supervisor_node, intent_node, policy_node...）
orchestration/langgraph/edges.py       → 条件路由函数（route_after_supervisor, route_after_intent...）
orchestration/langgraph/checkpointer.py → PostgreSQL Checkpointer实现
orchestration/langgraph/runtime.py     → 运行时安全（max_steps=10, loop_detection, timeout=30s）
```

### 第二步：数据库和配置 (database/ + backend/)

```
database/connection.py    → async SQLAlchemy engine + session factory
database/models.py        → ORM模型（Trace, Agent, Prompt, Evaluation, Checkpoint）
database/schemas.py       → Pydantic v2序列化模型
backend/config.py          → pydantic-settings配置类（读.env）
backend/main.py            → FastAPI app factory（CORS, middleware, router注册）
```

### 第三步：接入层 (backend/)

```
backend/middleware/auth.py     → JWT验证中间件
backend/middleware/rbac.py     → RBAC权限检查
backend/middleware/logging.py  → trace_id注入 + 结构化日志
backend/middleware/tracing.py  → OpenTelemetry span创建
backend/api/routes.py          → /chat, /agent, /evaluation, /a2a/callback 端点
backend/api/dependencies.py    → get_db, get_current_user, get_agent_runtime
backend/api/schemas.py         → ChatRequest, AgentResponse, EvaluationReport
backend/services/agent_service.py → Agent生命周期管理（创建、执行、恢复）
```

### 第四步：Agent实现 (agents/)

```
agents/__init__.py              → AgentRegistry（register, get, list）
agents/supervisor/planner.py    → 任务拆解逻辑（LLM-based task decomposition）
agents/supervisor/router.py     → Agent路由（intent → agent mapping）
agents/supervisor/agent.py      → Supervisor主逻辑（plan → route → execute）
agents/intent/classifier.py     → BERT分类器（fine-tune + inference）
agents/intent/schema.py         → IntentLabel, IntentResult Pydantic模型
agents/intent/agent.py          → Intent Agent主逻辑（classify + fallback to LLM）
agents/policy/schema.py         → PolicyResult（answer + evidence[]）
agents/policy/agent.py          → Policy Agent主逻辑（call RAG pipeline → format answer）
agents/material/ocr.py          → OCR文档识别
agents/material/extractor.py    → 实体/字段抽取
agents/material/validator.py    → 规则校验（required fields vs submitted）
agents/material/agent.py        → Material Agent主逻辑（OCR → extract → validate）
agents/workflow/agent.py        → Workflow Agent（通过MCP调用create_case/query_status）
agents/governance/security.py   → 安全检测（PII, prompt injection, sensitive words）
agents/governance/behavior.py   → 行为分析（loop detection, anomaly detection）
agents/governance/optimizer.py  → 自动优化（trace分析 → 优化建议）
agents/governance/agent.py      → Governance Agent主逻辑
```

### 第五步：RAG管线 (rag/)

```
rag/embedding.py        → BGE embedding模型加载 + encode_query/encode_documents
rag/retriever.py        → 混合检索（Milvus dense + BM25 sparse → 融合排序）
rag/reranker.py         → BGE Reranker重排序
rag/generator.py        → LLM生成（带evidence标注的答案）
rag/knowledge_base.py   → 知识库索引（文档加载 → 切分 → embedding → 写入Milvus）
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