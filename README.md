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
government-agent-platform/


├── agents/

│
├── orchestration/

│   └── langgraph/


├── tools/

│   ├── mcp/

│   └── a2a/


├── rag/


├── governance/


├── database/


├── backend/


├── frontend/


└── deploy/

```

详细设计：

见：

```
docs/

ARCHITECTURE.md

AGENT_DESIGN.md

MCP_DESIGN.md

A2A_DESIGN.md

EVALUATION.md

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

# 16. Roadmap

## Phase 1

完成：

* LangGraph Runtime
* Supervisor Agent
* RAG

---

## Phase 2

完成：

* MCP Server
* Tool Calling

---

## Phase 3

完成：

* A2A Connector
* Async Callback

---

## Phase 4

完成：

* Evaluation Platform
* Dashboard

---

# 17. License

MIT License

---

# 项目定位总结

本项目目标不是构建一个简单智能问答机器人。

而是探索：

> 企业级多智能体应用如何通过标准协议、工程治理和自动评测实现可靠落地。