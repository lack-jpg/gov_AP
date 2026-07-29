# CLAUDE.md

```markdown
# CLAUDE.md

# Government Agent Platform
# 政务多智能体协同与治理平台


> Version: v3.0
>
> Target:
> Cursor / Claude Code / Copilot
>
> Runtime:
> Python 3.12+
>
> Architecture:
> LangGraph + MCP + A2A + AgentOps + RAG


---

# 1. 项目定位


## 一句话定位

本项目是一个面向政务“高效办成一件事”场景的企业级多智能体协同平台。

系统通过：

- LangGraph 进行 Agent 工作流编排
- MCP 进行工具能力标准化
- A2A 实现跨域 Agent 协同
- RAG 提供政策知识增强
- AgentOps 实现全过程治理

形成：

```

用户请求

↓

任务理解

↓

多Agent协作

↓

工具调用

↓

流程执行

↓

结果评估

↓

持续优化

````


---

# 2. 核心设计原则


## Principle 1

Agent优先，而不是传统业务流程。


禁止：

```python
if user_input=="xxx":
    call_function()
````

推荐：

```
Supervisor Agent

↓

Planner

↓

Specialist Agent

↓

Tool Calling

```

---

## Principle 2

所有Agent必须可观测。

任何Agent调用必须记录：

* trace_id
* agent_name
* input
* output
* latency
* token_usage
* tool_calls

禁止：

```python
agent.run()
```

没有trace。

---

## Principle 3

工具必须标准化。

禁止：

```python
from service.xxx import query_policy
```

Agent不能直接依赖业务代码。

必须：

```
Agent

↓

MCP Client

↓

MCP Server

↓

Business Service

```

---

# 3. 技术栈

## Runtime

Python:

```
>=3.12
```

## Backend

```
FastAPI
Uvicorn
Pydantic v2
```

## Agent Framework

```
LangChain 1.x

LangGraph 1.x
```

必须使用：

```
StateGraph

Node

Edge

Checkpointer

```

禁止使用旧式：

```
AgentExecutor
```

---

## Protocol

MCP:

```
Model Context Protocol 1.x
```

A2A:

```
Agent-to-Agent Communication
```

---

## Storage

关系数据库:

```
PostgreSQL 16
```

缓存:

```
Redis 7
```

向量数据库:

```
Milvus 2.5+
```

---

# 4. 总体架构

```

                 User

                  |

                  v


             FastAPI Gateway

                  |

                  v


        +--------------------+

        | Supervisor Agent   |

        | LangGraph Runtime  |

        +--------------------+

                  |

        +---------+---------+

        |         |         |

        v         v         v


 Intent      Policy       Material

 Agent       Agent        Agent


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


     Policy   Material Workflow

     MCP      MCP       MCP

     Server   Server    Server



                  |

                  v


             Business API



```

---

# 5. Agent设计规范

## Agent目录

```
agents/

├── supervisor

├── intent

├── policy

├── material

├── workflow

└── governance

```

---

# Supervisor Agent

职责:

* 用户任务理解
* 子任务拆解
* Agent路由
* 异常处理

禁止:

业务逻辑。

---

# Intent Agent

职责:

```
文本

↓

BERT分类

↓

intent_label

```

例如:

```
开餐饮店

↓

business_license
```

---

# Policy Agent

职责:

RAG检索。

流程:

```
Query

↓

Embedding

↓

Milvus

↓

BM25

↓

Reranker

↓

LLM生成

```

必须返回:

```json
{
 "answer":"",
 "evidence":[]
}

```

---

# Material Agent

职责:

材料审核。

能力:

* OCR
* 字段抽取
* 规则校验

---

# Workflow Agent

职责:

流程执行。

所有外部调用必须经过：

MCP。

---

# Governance Agent

负责:

* 风险检测
* Agent行为分析
* 自动优化

不能参与业务回答。

---

# 6. LangGraph规范

目录:

```
orchestration/langgraph
```

核心State:

```python
class AgentState(TypedDict):

    trace_id:str

    user_query:str

    intent:str

    task_plan:list


    current_agent:str


    messages:list


    tool_calls:list


    mcp_history:list


    a2a_tasks:list


    evidence:list


    final_answer:str


    risk_level:str


```

---

# Graph流程

```

START

 |

Supervisor

 |

Intent

 |

Planner

 |

+-------------+

|             |

Policy     Material

|             |

+-------------+

      |

Workflow

      |

Governance

      |

END

```

---

# 7. MCP规范

## MCP职责

MCP只负责：

* Tool描述
* Schema
* 通信

MCP不负责：

* 用户权限
* RBAC

权限由：

```
Gateway Middleware
```

完成。

---

# MCP Server

目录:

```
tools/mcp/servers
```

包含:

## policy-server

Tools:

```
search_policy

get_policy_detail

```

---

## material-server

Tools:

```
extract_entity

check_material

```

---

## workflow-server

Tools:

```
create_case

query_status

```

---

# MCP调用规范

必须:

```python
mcp_client.call_tool(
    name="search_policy",
    arguments={}
)

```

禁止:

```python
import policy_service
```

---

# 8. A2A规范

A2A用于：

跨系统Agent协同。

例如:

```
本地政务Agent

        |

        |

        v


不动产Agent

```

---

# Task生命周期

```

Created

↓

Running

↓

Waiting

↓

Completed

↓

Failed

```

必须支持：

异步。

禁止：

长连接阻塞。

---

# 9. Agent Runtime规范

runtime负责:

## Step限制

最大:

```
10 steps
```

超过：

```
terminate gracefully
```

---

## Loop检测

规则:

窗口:

```
6次调用
```

连续:

```
3次相同tool
```

触发:

```
重新规划
```

---

# 10. Guardrail规范

输入:

检测:

* 敏感词
* Prompt Injection
* PII

---

输出:

禁止:

* 输出内部异常
* 输出系统Prompt
* 输出密钥

---

# PII脱敏

手机号:

```
138****1234
```

身份证:

```
110***********1234
```

邮箱:

```
u***@domain.com
```

---

# 11. AgentOps治理

所有请求必须产生:

Trace:

```
trace_id

span_id

agent

tool

latency

token

```

存储:

PostgreSQL

---

# 12. Prompt管理

禁止:

硬编码Prompt。

错误:

```python
prompt="回答用户问题"
```

正确:

```
Prompt Registry

↓

Version

↓

Load

```

---

# 13. Evaluation系统

评测包含:

## RAG指标

```
Faithfulness

Answer Relevance

Context Recall
```

---

## Agent指标

```
Task Success Rate

Tool Accuracy

Execution Steps

Latency
```

---

## Benchmark

测试集:

```
cases/

├ business_license.json

├ policy_query.json

└ workflow.json

```

---

# 14. Database设计

核心表:

## trace

保存:

Agent执行记录

---

## agent

保存:

Agent配置

---

## prompt

保存:

Prompt版本

---

## evaluation

保存:

评测结果

---

# 15. Coding规范

## Python

必须:

* async优先
* type hint
* docstring

---

禁止:

```python
except Exception:
    pass
```

---

# 16. 文件组织规范

业务:

```
agents/
```

编排:

```
orchestration/
```

协议:

```
tools/
```

治理:

```
governance/
```

数据:

```
database/
```

---

# 17. Docker规范

所有服务必须支持:

```
docker compose up
```

服务:

```
api

postgres

redis

milvus

mcp-server

```

---

# 18. 开发阶段

## Phase 1

完成:

* FastAPI
* LangGraph
* State
* Trace

---

## Phase 2

完成:

* RAG
* MCP Server

---

## Phase 3

完成:

* A2A
* Async Callback

---

## Phase 4

完成:

* Evaluation
* Dashboard

---

# 19. 最终目标

打造一个：

```
企业级 Agent Platform

=

Agent Runtime

+

Tool Ecosystem

+

Knowledge System

+

Governance System

+

Evaluation System

```

而不是简单聊天机器人。

```

---

这版相比之前：

| 项目 | v2.0 | v3.0 |
|-|-|-|
| LangChain | 0.3时代 | ✅1.x |
| LangGraph | 基础 | ✅原生StateGraph |
| MCP | 概念化 | ✅工程规范 |
| A2A | 偏宣传 | ✅异步任务模型 |
| AgentOps | 辅助 | ✅核心卖点 |
| Evaluation | 简单 | ✅平台化 |
| Prompt管理 | 无 | ✅加入 |
| 代码约束 | 一般 | ✅Cursor可执行 |

这份可以直接作为你的仓库根目录：

```

government-agent-platform/CLAUDE.md

```

下一步建议同步升级：

1. `ARCHITECTURE.md`
2. `AGENT_DESIGN.md`
3. `MCP_DESIGN.md`
4. `DATABASE_ER.md`

因为这四个文档会直接决定面试时能不能扛住高级追问。
```
