# `docs/AGENT_DESIGN.md`

定位：

> **Multi-Agent系统详细设计文档**

---

```markdown
# AGENT_DESIGN.md

# 政务多智能体协同平台
# Multi-Agent Detailed Design


Version: v1.0


---

# 1. 文档说明


本文档描述系统中：

- Agent角色设计
- Agent职责划分
- Agent协作流程
- LangGraph编排机制
- State设计
- 错误恢复机制
- Agent安全控制


目标：

构建一个：

> 可规划、可执行、可观察、可治理的企业级 Multi-Agent 系统。



---

# 2. Multi-Agent设计理念


## 2.1 为什么不是单Agent？


传统：

```

User

|

LLM

|

Answer

```


问题：

- 所有能力集中
- Prompt复杂
- Tool数量膨胀
- 难以评估


例如：

一个政务问题：

```

我要开餐馆，需要什么？

```


实际包含：

```

营业执照

*

食品经营许可证

*

消防要求

*

环保要求

*

材料提交

```


单Agent需要同时理解：

- 多领域知识
- 多流程规则
- 多系统接口


容易产生：

- 错误规划
- 工具误调用
- 幻觉


---

# 2.2 Multi-Agent设计原则


系统采用：

```

Supervisor

*

Specialized Agents

*

Tool Agents

*

Governance Agent

```


原则：

## 单一职责

每个Agent负责一个领域。


## 状态共享

Agent之间通过State通信。


## 可控执行

所有流程由LangGraph管理。



---

# 3. Agent整体架构


```

```
             User Query


                 |

                 v


      +--------------------+

      | Supervisor Agent   |

      | Planner + Router   |

      +--------------------+

                 |

   +-------------+-------------+

   |             |             |

   v             v             v
```

Intent Agent   Policy Agent  Material Agent

```
   |             |             |

   +-------------+-------------+

                 |

                 v


         Workflow Agent


                 |

                 v


         Governance Agent
```

```



---

# 4. Agent角色设计


系统包含6类核心Agent。



| Agent | 类型 | 职责 |
|-|-|-|
| Supervisor Agent | Orchestrator | 全局规划和调度 |
| Intent Agent | Understanding | 用户意图识别 |
| Policy Agent | Knowledge | 政策知识检索 |
| Material Agent | Validation | 材料审核 |
| Workflow Agent | Execution | 流程执行 |
| Governance Agent | Control | 安全治理 |



---

# 5. Supervisor Agent设计


## 5.1 职责


Supervisor是系统大脑。


负责：

- 任务理解
- 任务拆解
- Agent选择
- 状态管理
- 异常处理



---

## 5.2 工作流程



```

User Request

```
  |

  v
```

Intent Analysis

```
  |

  v
```

Task Planning

```
  |

  v
```

Agent Routing

```
  |

  v
```

Execution

````


---

# 5.3 Planner设计


输入：


```json
{
"query":"我要开餐馆"
}

````

输出：

```json
{
"tasks":[

"search_policy",

"check_material",

"create_workflow"

]

}

```

---

# 5.4 Router设计

根据任务选择Agent。

例如：

输入：

```
开餐馆需要什么材料

```

Routing:

```
Policy Agent

Material Agent

```

---

# 6. Intent Agent设计

## 6.1 目标

解决：

自然语言

↓

业务事项

---

## 6.2 技术方案

采用：

```
BERT Fine-tuning

+

LLM fallback

```

流程：

```
User Query

 |

BERT Classifier

 |

Intent Label

 |

Supervisor


```

---

## 6.3 意图分类示例

| 输入    | 分类                |
| ----- | ----------------- |
| 我要开公司 | business_register |
| 查询公积金 | fund_query        |
| 办理房产证 | property_service  |

---

# 7. Policy Agent设计

## 7.1 职责

负责：

政策法规查询。

---

## 7.2 RAG架构

```

Query


 |

Embedding


 |

Vector Search


 |

BM25


 |

Hybrid Retrieval


 |

Reranker


 |

LLM


 |

Answer


```

---

## 7.3 知识来源

包括：

```
政策文件

办事指南

法规条例

FAQ

```

---

## 7.4 输出格式

必须包含：

```json
{

"answer":"",

"evidence":[

{

"source":"食品经营许可条例",

"page":12

}

]

}

```

保证：

* 可追溯
* 可审核

---

# 8. Material Agent设计

## 8.1 职责

负责材料完整性审核。

---

## 8.2 输入

```
政策要求

+

用户提交材料

```

---

## 8.3 流程

```

Document

 |

OCR

 |

Entity Extraction

 |

Rule Validation

 |

Result


```

---

## 8.4 输出

```json
{

"passed":false,

"missing":[

"营业场所证明"

]

}

```

---

# 9. Workflow Agent设计

## 9.1 职责

负责真实业务执行。

例如：

创建办件。

---

## 9.2 Tool调用方式

禁止：

```python
api.create_case()

```

必须：

```
Workflow Agent

       |

       v

MCP Client

       |

       v

workflow-mcp-server

```

---

# 10. Governance Agent设计

## 10.1 定位

不是业务Agent。

属于：

旁路控制Agent。

---

## 10.2 负责内容

### 安全检测

```
PII

Prompt Injection

Sensitive Content

```

---

### Agent行为分析

检测：

* 无限循环
* 工具异常
* 异常输出

---

### 自动优化

分析：

```
Trace

Evaluation Result

Human Feedback

```

生成：

* Prompt优化建议
* Workflow优化建议

---

# 11. Agent通信设计

## 11.1 内部通信

采用：

LangGraph State。

```

Agent A

 |

State

 |

Agent B


```

---

## 11.2 State结构

```python

class AgentState:

    user_query:str


    intent:str


    task_plan:list


    current_agent:str


    messages:list


    tool_calls:list


    evidence:list


    risk_level:str


    final_answer:str


```

---

# 12. Agent执行生命周期

```

Receive


 |

Plan


 |

Execute


 |

Observe


 |

Evaluate


 |

Finish



```

---

# 13. Agent安全机制

## 13.1 Step限制

防止无限循环。

配置:

```
max_steps=10

```

---

## 13.2 Loop Detection

滑动窗口：

```
最近6次tool call


```

如果：

```
连续3次相同工具

```

触发：

```
Re-plan

```

---

## 13.3 Timeout控制

每个Agent：

```
timeout=30s

```

---

# 14. Agent错误恢复

## 类型1

工具失败

处理：

```
Retry

↓

Fallback

↓

Human Review

```

---

## 类型2

Agent输出异常

处理：

```
Validator

↓

重新生成


```

---

## 类型3

外部Agent超时

处理：

```
Checkpoint

↓

Suspend

↓

Callback Resume

```

---

# 15. Multi-Agent评测设计

## 15.1 单Agent指标

| 指标            | 说明    |
| ------------- | ----- |
| Accuracy      | 回答正确率 |
| Latency       | 响应时间  |
| Tool Accuracy | 工具选择  |

---

# 15.2 多Agent指标

重点：

## Task Success Rate

最终任务完成比例。

例如：

```
100个办件

成功完成92个

Success Rate=92%

```

---

## Collaboration Efficiency

评价：

```
Agent调用次数

平均步骤

错误次数


```

---

# 16. Prompt设计规范

所有Agent Prompt必须版本化。

结构:

```
Role

Goal

Constraints

Tools

Output Schema

Examples

```

---

# 17. Agent扩展机制

新增Agent：

目录：

```
agent/

  new_agent/

      agent.py

      prompt.py

      schema.py

```

注册:

```python

AgentRegistry.register(
    "new_agent"
)

```

无需修改Runtime。

---

# 18. 典型业务流程示例

## 开餐馆

用户：

```
我要开一家餐馆

```

流程：

```

Supervisor


 ↓


Intent Agent


 ↓


business_license


 ↓


Policy Agent


 ↓


查询政策


 ↓


Material Agent


 ↓


材料检查


 ↓


Workflow Agent


 ↓


创建办件


 ↓


Governance Agent


 ↓


输出结果


```

---

# 19. 设计总结

本系统不是：

```
多个Prompt拼接

```

而是：

```
Multi-Agent Runtime


+

State Management


+

Tool Ecosystem


+

Governance Layer


```

最终实现：

> 一个面向企业生产环境的可控、多能力协同的智能体平台。

```