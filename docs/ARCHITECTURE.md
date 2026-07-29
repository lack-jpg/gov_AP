# `docs/ARCHITECTURE.md`

定位：

> **政务多智能体协同与治理平台系统架构设计文档**

---

```markdown
# ARCHITECTURE.md

# 政务多智能体协同与治理平台
# System Architecture Design


Version: v1.0

Author: AI Engineering Team


---

# 1. 文档说明


## 1.1 文档目的


本文档用于描述：

- 系统整体架构
- 核心模块职责
- 数据流设计
- Agent协同机制
- MCP/A2A通信设计
- AgentOps治理体系


目标：

构建一个：

> 可扩展、可观测、可治理的企业级 Multi-Agent Application Platform。



---

# 2. 系统定位


## 2.1 一句话定义


本系统是一套基于：

- LangGraph
- MCP
- A2A
- RAG
- AgentOps


构建的政务领域多智能体协同平台。


系统支持：

用户诉求理解

↓

任务规划

↓

Agent协同

↓

工具调用

↓

业务执行

↓

结果评估

↓

持续优化



---

# 3. 设计目标


## 3.1 业务目标


解决传统政务系统：

|问题|解决方案|
|-|-|
|跨部门流程复杂|Multi-Agent协同|
|知识分散|RAG知识增强|
|接口异构|MCP标准化|
|系统隔离|A2A通信|
|Agent不可控|AgentOps治理|



---


## 3.2 技术目标


实现：

### Agent可编排

基于LangGraph:

```

StateGraph

Node

Edge

Checkpoint

```


---

### Tool可扩展


通过MCP:

```

Agent

↓

MCP Client

↓

MCP Server

↓

Business API

```


---

### Agent可治理


通过AgentOps:

```

Trace

Evaluation

Guardrail

Prompt Management

```



---

# 4. 总体架构


系统采用六层架构。



```

```
                用户端

                   |

                   v


          +----------------+

          | API Gateway    |

          | FastAPI        |

          +----------------+

                   |

                   v
```

================================================

```
         Agent Orchestration Layer


          LangGraph Runtime
```

================================================

```
                   |

                   v


          Supervisor Agent


                   |

    +--------------+--------------+

    |              |              |

    v              v              v
```

Intent Agent    Policy Agent   Material Agent

```
    |              |              |

    +--------------+--------------+

                   |

                   v


          Workflow Agent
```

================================================

```
            Tool Capability Layer
```

================================================

```
                   |

                   v


          MCP Gateway


      |            |            |

      v            v            v


Policy MCP   Material MCP   Workflow MCP



                   |

                   v


          Business Systems
```

================================================

```
          Cross Agent Layer
```

================================================

```
          A2A Connector


                   |

                   v


    External Domain Agents
```

================================================

```
          Governance Layer
```

================================================

Trace

Evaluation

Guardrail

Prompt Management

================================================

```



---

# 5. 六层架构设计


# L1 接入层


## 技术


```

FastAPI

Nginx

JWT

RBAC

````



职责:


- 用户请求接入
- 身份认证
- 请求限流
- API管理


---

请求示例:


```json
{
"user_id":"001",
"query":"我要开一家餐馆"
}

````

---

# L2 Agent编排层

核心:

```
LangGraph Runtime
```

负责：

* Agent调度
* 状态管理
* 条件路由
* 异常恢复

核心组件:

```
StateGraph

Node

Edge

Checkpointer

```

---

# L3 专业Agent层

系统包含:

## Supervisor Agent

职责：

全局任务管理。

能力:

* Task Planning
* Agent Routing
* Context Management

---

## Intent Agent

负责：

用户意图识别。

流程:

```
Text

↓

BERT Classifier

↓

Intent Label

```

例如:

```
开餐馆

↓

business_license

```

---

## Policy Agent

负责政策知识查询。

架构:

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

LLM

```

输出:

```json
{
"answer":"",
"evidence":[]
}

```

---

## Material Agent

负责：

材料审核。

能力:

* OCR
* Entity Extraction
* Rule Validation

---

## Workflow Agent

负责：

业务流程执行。

所有外部调用：

必须经过MCP。

---

# L4 MCP能力层

## 设计目标

解决：

Agent与业务系统强耦合问题。

传统:

```
Agent

↓

API

```

升级:

```
Agent

↓

MCP Client

↓

MCP Gateway

↓

MCP Server

↓

API

```

---

# MCP Server设计

## Policy MCP Server

Tools:

```
search_policy

get_policy_detail

```

---

## Material MCP Server

Tools:

```
extract_entity

check_material

```

---

## Workflow MCP Server

Tools:

```
create_case

query_status

```

---

# L5 A2A跨Agent层

## 使用场景

当任务涉及：

* 不动产
* 公积金
* 外部部门

当前系统无法直接处理。

通过A2A调用外部Agent。

---

## 通信流程

```

Local Agent

      |

      |

A2A Connector

      |

      |

External Agent


```

---

## Task生命周期

```

Created

  |

Running

  |

Waiting

  |

Completed


```

---

# L6 AgentOps治理层

治理体系包括:

## Trace系统

记录:

```
trace_id

agent

tool

latency

token

error

```

---

## Guardrail

输入:

* Prompt Injection
* PII
* Sensitive Words

输出:

* 数据泄露
* 内部错误

---

## Evaluation

自动评估:

```
Agent Success Rate

Tool Accuracy

RAG Quality

Latency


```

---

# 6. 数据流设计

## 用户请求流程

```

User

 |

 |

API Gateway

 |

 |

Supervisor Agent

 |

 |

Intent Agent

 |

 |

Planner

 |

 +------------+

 |            |

Policy     Material

Agent       Agent

 |

 |

Workflow Agent

 |

 |

MCP Tool

 |

 |

Business System

 |

 |

Final Answer


```

---

# 7. Agent State设计

LangGraph共享状态:

```python

class AgentState:


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

# 8. Checkpoint机制

## 目的

支持：

* 长流程恢复
* A2A异步等待
* 异常恢复

流程:

```

Agent执行


↓

保存State


↓

等待外部任务


↓

恢复State


↓

继续执行


```

---

# 9. 安全架构

## 输入安全

检测:

```
PII

Injection

Sensitive Content

```

---

## 输出安全

过滤:

```
Internal Error

System Prompt

Secret

```

---

# 10. 可扩展设计

未来支持:

## 新增Agent

只需要:

```
agents/

   new_agent/


```

无需修改核心Runtime。

---

## 新增工具

新增:

```
MCP Server

```

Agent无需修改。

---

# 11. 部署架构

生产环境:

```

                 Nginx


                   |

                   v


              FastAPI


                   |

        +----------+----------+

        |                     |

   Agent Runtime        MCP Server


        |

        |

 PostgreSQL

 Redis

 Milvus


```

---

# 12. 技术选型总结

| 模块              | 技术            |
| --------------- | ------------- |
| Backend         | FastAPI       |
| Agent Framework | LangGraph 1.x |
| LLM Framework   | LangChain 1.x |
| Protocol        | MCP/A2A       |
| Vector DB       | Milvus        |
| Database        | PostgreSQL    |
| Cache           | Redis         |
| Trace           | OpenTelemetry |
| Evaluation      | RAGAS         |
| Deployment      | Docker        |

---

# 13. 架构设计原则总结

本平台遵循:

## 解耦

MCP隔离工具。

## 可控

LangGraph管理流程。

## 可扩展

Agent插件化。

## 可治理

AgentOps闭环。

最终形成:

```

Enterprise Agent Platform


=
 
Agent Runtime

+

Tool Ecosystem

+

Knowledge System

+

Governance System


```