# `docs/DEPLOYMENT.md`

定位：

> **生产级 Agent 平台部署设计文档**

---

```markdown
# DEPLOYMENT.md


# 政务多智能体协同平台

# 部署设计文档


Version: v1.0



---

# 1. 文档说明


本文档定义：

government-agent-platform


生产环境部署方案。


主要包括：


- 部署架构
- 服务拆分
- Docker化
- Kubernetes部署
- GPU资源规划
- 模型服务部署
- 数据服务部署
- 高可用设计
- 国产化适配


目标：


> 将Agent系统从开发环境平滑迁移至生产环境。



---


# 2. 部署总体架构



生产环境采用：

```

Kubernetes

*

Docker

*

微服务架构

```



整体架构：


```

```
                用户


                 |

                 v


          Nginx Gateway


                 |

                 v


          FastAPI Backend


                 |

   +-------------+--------------+

   |             |              |


   v             v              v
```

LangGraph      MCP Gateway      A2A Gateway

Runtime

```
   |             |              |


   v             v              v
```

Agent服务      MCP Server      External Agent

```
   |

   v
```

Model Service

```
   |

   v
```

GPU推理集群

```



---

# 3. 服务拆分设计



系统拆分为以下服务：



|服务|职责|部署方式|
|-|-|-|
|backend|业务API|Deployment|
|agent-runtime|Agent执行|Deployment|
|model-service|LLM推理|GPU Node|
|mcp-gateway|工具管理|Deployment|
|mcp-server|业务工具|Deployment|
|a2a-gateway|跨Agent通信|Deployment|
|evaluation|自动评测|Job|
|frontend|管理后台|Nginx|
|postgres|业务数据|StatefulSet|
|redis|缓存|StatefulSet|
|milvus|向量数据库|StatefulSet|



---

# 4. Docker部署设计



## 4.1 Backend Dockerfile


目录：


```

deploy/

└── Dockerfile

````



示例：


```dockerfile

FROM python:3.12-slim


WORKDIR /app


COPY requirements.txt .


RUN pip install -r requirements.txt


COPY backend .


CMD [

"uvicorn",

"main:app",

"--host",

"0.0.0.0"

]


````

---

# 4.2 GPU模型服务

LLM单独部署。

架构：

```

Agent Runtime


      |

      |

OpenAI Compatible API


      |

      |

vLLM


      |

      |

GPU


```

例如：

```
Qwen2.5-14B-Instruct


```

启动：

```bash

python -m vllm.entrypoints.openai.api_server

--model Qwen/Qwen2.5-14B-Instruct

--tensor-parallel-size 2


```

---

# 5. 模型服务架构

## 5.1 模型分类

系统包含：

| 模型        | 用途   |
| --------- | ---- |
| LLM       | 复杂推理 |
| BERT      | 意图分类 |
| Embedding | 向量检索 |
| Reranker  | 重排序  |
| OCR Model | 材料识别 |

---

## 5.2 推理服务设计

```

                Agent


                  |


                  |


          Model Gateway


                  |


       +----------+----------+

       |                     |


       v                     v


   LLM Server          Embedding Server


       |                     |

       v                     v


     GPU                 GPU



```

---

# 6. GPU资源规划

## 小规模部署

测试环境：

| 服务        | GPU     |
| --------- | ------- |
| LLM       | 1张24G   |
| Embedding | 共享      |
| Reranker  | CPU/GPU |

---

## 生产环境

推荐：

| 服务        | GPU         |
| --------- | ----------- |
| LLM推理     | 4×A800/H800 |
| Embedding | 1×GPU       |
| Reranker  | 1×GPU       |

---

# 7. Kubernetes部署设计

目录：

```

deploy/k8s/


├── backend.yaml

├── agent.yaml

├── model.yaml

├── mcp.yaml

├── postgres.yaml

└── ingress.yaml


```

---

# 8. Backend Deployment

示例：

```yaml

apiVersion: apps/v1

kind: Deployment


metadata:

 name: backend



spec:

 replicas: 3



 template:


  spec:


   containers:


   - name: backend


     image:

       government/backend:v1



     ports:


     - containerPort:8000



```

---

# 9. Agent Runtime部署

Agent Runtime特点：

* 状态敏感
* 任务较长

因此：

采用：

```

Deployment

+

Redis

+

PostgreSQL Checkpoint


```

保存：

```
trace

state

checkpoint


```

---

# 10. LangGraph状态持久化

生产环境：

禁止：

```
MemorySaver

```

使用：

```
PostgreSQL Checkpointer


```

数据：

```sql

agent_state

checkpoint_id

task_id

created_time


```

支持：

* 服务重启恢复
* A2A任务恢复
* 长任务暂停

---

# 11. MCP Server部署

每个MCP Server独立部署。

例如：

```

mcp-policy


mcp-material


mcp-workflow



```

优势：

* 独立扩容
* 独立升级
* 故障隔离

---

# 12. A2A Gateway部署

职责：

```

Agent发现

任务转发

认证

Callback


```

架构：

```

Agent


 |

A2A Gateway


 |

External Agent


```

---

# 13. 数据库部署

## PostgreSQL

保存：

```

用户

Agent状态

Trace

Evaluation结果


```

---

## Redis

用途：

```

Session

Cache

Task Queue


```

---

## Milvus

用途：

```

政策知识库

Embedding索引


```

---

# 14. 配置管理

采用：

环境变量。

目录：

```

.env.example


```

示例：

```env


LLM_API_URL=http://model-service:8000


POSTGRES_HOST=postgres


REDIS_HOST=redis


MILVUS_HOST=milvus



```

---

# 15. 日志与监控

## 日志

采用：

```

Python logging

+

ELK


```

记录：

* Trace ID
* Agent
* Tool
* Latency

---

# 16. Metrics监控

指标：

## Agent指标

```

agent_success_rate

agent_latency

agent_error


```

## LLM指标

```

token_usage

gpu_memory

request_latency


```

## MCP指标

```

tool_success_rate

tool_latency


```

---

# 17. 链路追踪

采用：

```

OpenTelemetry


```

Trace:

```

Request


 |

Supervisor


 |

Policy Agent


 |

MCP Tool


 |

LLM


```

---

# 18. 高可用设计

## 服务高可用

采用：

```

多副本Deployment


```

例如：

```

backend replicas=3

agent replicas=3


```

---

## 数据高可用

PostgreSQL：

```

Primary

+

Replica


```

Redis：

```

Cluster


```

---

# 19. 异常恢复策略

## Agent异常

流程：

```

Exception


 |

Retry


 |

Fallback


 |

Human Review


```

---

## MCP失败

```

Tool Error


 |

Retry


 |

Alternative Tool


```

---

## A2A失败

```

Timeout


 |

Callback Retry


 |

人工处理


```

---

# 20. 国产化部署适配

支持：

## 操作系统

```

麒麟OS

统信UOS


```

---

## CPU架构

支持：

```

x86_64

arm64


```

---

## 国产GPU

适配：

```

昇腾

寒武纪


```

---

# 21. 信创部署架构

```

Kylin OS


 |

Docker


 |

Kubernetes


 |

Agent Platform


 |

Ascend Runtime


```

---

# 22. CI/CD流程

```

Git Push


 |

CI


 |

Unit Test


 |

Docker Build


 |

Image Registry


 |

K8S Deploy


 |

Evaluation Test


```

---

# 23. 发布流程

版本：

```

v1.0

v1.1

v2.0


```

发布前：

必须通过：

* 单元测试
* MCP测试
* A2A测试
* Evaluation Benchmark

---

# 24. 生产安全设计

## 网络隔离

```

公网


 |

Gateway


 |

业务区


 |

数据区


```

---

## 数据保护

包括：

* PII脱敏
* 数据加密
* 审计日志

---

# 25. 面试回答模板

## Q:

你的Agent系统如何部署？

回答：

> 我们采用微服务化部署，Agent Runtime、MCP Server、A2A Gateway、模型服务分别独立部署。LangGraph负责流程编排，状态通过PostgreSQL持久化，LLM通过vLLM提供OpenAI兼容接口，支持GPU推理。

---

## Q:

为什么LLM不直接放在Backend？

回答：

> 因为生产环境模型服务和业务服务生命周期不同。模型需要独立扩缩容，同时GPU资源需要隔离，所以采用独立Model Service，通过API调用。

---

## Q:

如何保证Agent任务不中断？

回答：

> 我们使用LangGraph Checkpointer保存执行状态，当Agent执行到长耗时任务，例如A2A跨系统调用时，会保存Checkpoint并挂起，外部任务完成后恢复执行。

---

# 26. 总结

最终部署体系：

```

          Kubernetes


              |

     +--------+---------+

     |                  |


 Agent Platform    Model Platform


     |                  |


 LangGraph          vLLM


     |


 MCP + A2A


     |


 AgentOps



```

最终实现：

> 一个可部署、可扩展、可治理的企业级多智能体平台。

```
```

---

目前你的完整 `docs` 已经形成：

```
docs/

├── ARCHITECTURE.md      系统架构
│
├── AGENT_DESIGN.md      Agent设计
│
├── MCP_DESIGN.md        工具标准
│
├── A2A_DESIGN.md        Agent通信
│
├── EVALUATION.md        自动评测
│
└── DEPLOYMENT.md        生产部署
```
