# `docs/A2A_DESIGN.md`

定位：

> **Agent-to-Agent 跨域智能体协同通信设计文档**

---

```markdown
# A2A_DESIGN.md

# 政务多智能体协同平台
# Agent-to-Agent 跨域通信设计


Version: v1.0



---

# 1. 文档说明


本文档定义系统中：

Agent-to-Agent（A2A）

通信架构。


主要内容：

- A2A引入背景
- Agent发现机制
- Agent Card设计
- Task生命周期
- 异步通信机制
- Callback设计
- LangGraph集成
- 安全隔离
- Mock Agent实现



目标：

实现：

> 不同部门、不同系统、不同部署环境下 Agent 的标准化协同。


---


# 2. 为什么需要A2A？


## 2.1 MCP解决什么问题？


MCP:

> Agent 调用工具


关系：


```

Agent

|

MCP

|

Tool

```



例如：

政策Agent调用：

```

search_policy

```


---

## 2.2 A2A解决什么问题？


A2A:

> Agent 调用 Agent



关系：


```

Agent A

|

A2A Protocol

|

Agent B

```


例如：


政务综合Agent：

需要：

```

查询公积金

```


但是：

公积金系统属于独立部门。


无法直接访问。


因此：


```

综合Agent

```
  |

  |
```

A2A Connector

```
  |

  |
```

公积金Agent

```



---

# 3. MCP与A2A区别



| |MCP|A2A|
|-|-|-|
|通信对象|Agent→Tool|Agent→Agent|
|核心目的|能力调用|任务协作|
|粒度|函数级|任务级|
|状态|短生命周期|长生命周期|
|典型场景|搜索、OCR、API|跨部门业务协同|



---


# 4. A2A整体架构


```

```
                User


                 |

                 v


          Supervisor Agent


                 |

                 |

    判断是否跨域任务


                 |

    +------------+------------+

    |                         |

    v                         v
```

Local Agent              A2A Connector

```
                              |

                              |

                     A2A Protocol


                              |

                              |

                +-------------+-------------+

                |                           |


                v                           v


         Housing Agent              Fund Agent


         不动产系统                  公积金系统
```

````



---

# 5. A2A核心组件



系统包含：


|组件|职责|
|-|-|
|A2A Connector|发送任务|
|Agent Registry|管理Agent|
|Agent Card|描述能力|
|Task Manager|任务状态|
|Callback Server|结果回传|
|Checkpoint|状态恢复|



---

# 6. Agent Registry设计


负责：

管理外部Agent。



例如：


```json
{
"agent_id":"housing_agent",

"name":"不动产查询Agent",

"url":"https://housing.xxx.com",

"status":"online"

}

````

---

# 7. Agent Card设计

Agent Card用于描述：

> 一个Agent有什么能力。

示例：

```json
{

"agent_id":"housing_agent",


"name":"不动产查询Agent",


"description":

"提供个人房产信息查询",



"skills":[


{

"name":"query_property",

"description":

"查询个人房产"


}

],


"authentication":{

"type":"oauth2"

}


}

```

---

# 8. A2A Task设计

所有跨Agent请求抽象为Task。

结构：

```python

class A2ATask:


    task_id:str


    source_agent:str


    target_agent:str


    skill:str


    input:dict


    status:str


```

---

# 9. Task生命周期

状态：

```

        create


          |

          v


       submitted


          |

          v


       working


          |

          |

     +----+----+

     |         |

     v         v


 completed   failed



```

完整状态：

| 状态        | 说明        |
| --------- | --------- |
| created   | 任务创建      |
| submitted | 发送外部Agent |
| working   | 处理中       |
| completed | 完成        |
| failed    | 失败        |
| timeout   | 超时        |

---

# 10. 为什么采用异步模式？

政务系统特点：

* 跨网络
* 服务响应慢
* 人工审核参与

同步调用：

```

Agent

 |

等待30秒

 |

Timeout


```

问题：

* 阻塞资源
* 状态丢失

因此采用：

```

发送任务

↓

保存状态

↓

挂起

↓

Callback恢复



```

---

# 11. A2A异步流程设计

完整流程：

```

Supervisor


 |

 |

create Task


 |

 |

A2A Connector


 |

 |

External Agent


 |

 |

processing


 |

 |

callback


 |

 |

Callback API


 |

 |

LangGraph Resume


 |

 |

Continue Workflow



```

---

# 12. Callback设计

接口：

```
POST

/api/a2a/callback


```

Request:

```json
{

"task_id":"task_001",


"status":"completed",


"artifact":{


"house_count":2

}


}

```

Response:

```json
{

"success":true

}

```

---

# 13. LangGraph集成设计

## 13.1 State增加字段

```python

class OverallState:


    a2a_tasks:list


    waiting_task_id:str


    external_result:dict


```

---

## 13.2 A2A Node

流程节点：

```

Supervisor


    |

    v


A2A Check Node


    |

    v


A2A Connector


    |

    v


Interrupt


```

---

# 14. Checkpoint恢复机制

使用：

LangGraph Checkpointer。

流程：

```

执行到A2A节点


        |

保存State


        |

interrupt


        |

等待callback


        |

读取checkpoint


        |

恢复执行



```

---

# 15. A2A Connector设计

目录：

```

a2a/


├── connector.py

├── protocol.py

├── callback.py

├── registry.py

└── mock_agents/


```

---

# connector.py

核心接口：

```python

class A2AConnector:


    async def send_task(

        self,

        agent_id,

        task

    ):


        pass



```

---

# 16. Mock Agent设计

由于真实政务系统不可接入。

提供模拟Agent。

例如：

```

mock_agents/


├── housing_agent.py

└── fund_agent.py



```

---

# housing_agent示例

能力：

```
query_property

```

输入：

```json

{

"user_id":"001"

}

```

返回：

```json

{

"property_count":1

}

```

---

# 17. A2A安全设计

## 17.1 身份认证

采用：

```

Agent Token


+

mTLS


```

---

## 17.2 数据隔离

禁止：

外部Agent获取全部State。

只发送必要字段。

例如：

禁止：

```json
{
"user_all_data":"xxx"
}

```

允许：

```json
{

"user_id":"001",

"task":"query_property"

}

```

---

# 18. A2A异常处理

## Timeout

策略：

```

Retry

↓

Fallback

↓

Human Review


```

---

## Agent失败

记录：

```json
{

"task_id":"xxx",

"error":

"external agent unavailable"


}

```

---

# 19. A2A调用审计

所有任务记录：

```python

class A2ATaskRecord:


    task_id:str


    source_agent:str


    target_agent:str


    start_time:str


    end_time:str


    status:str


```

保存：

PostgreSQL。

---

# 20. A2A评测指标

## Task Success Rate

跨Agent任务成功率。

---

## Average Completion Time

平均完成时间。

---

## Failure Rate

失败比例。

---

## Agent Routing Accuracy

Supervisor选择正确Agent比例。

---

# 21. 面试回答模板

## Q:

为什么不用MCP解决所有问题？

回答：

> MCP解决的是Agent访问工具的问题，比如搜索、OCR、数据库操作，而A2A解决的是Agent之间协同的问题。例如政务场景中，不动产Agent和公积金Agent属于不同业务域，需要通过A2A进行任务级通信。

---

## Q:

你的A2A是真实接入多个部门吗？

回答：

> 当前项目采用Mock Agent模拟外部部门系统，重点验证协议设计、异步任务管理以及状态恢复机制。真实生产环境中，只需要替换Connector连接真实Agent即可。

---

## Q:

为什么不用同步HTTP调用？

回答：

> 因为跨部门系统存在网络隔离和长耗时任务，同步调用容易导致连接阻塞。所以采用任务提交+Callback回调模式，并结合LangGraph Checkpointer实现任务挂起和恢复。

---

# 22. 总结

A2A能力使系统从：

```
单体Agent系统

```

升级为：

```
多Agent协作系统

```

最终形成：

```

        MCP

Agent -------- Tool


        +


        A2A


Agent -------- Agent


        +


     Evaluation


```

构成完整：

> 企业级 Agent Platform 架构。

```
```

---

现在你的 `docs` 五大核心设计已经闭环：

```
docs/

├── ARCHITECTURE.md     系统架构
│
├── AGENT_DESIGN.md     Agent设计
│
├── MCP_DESIGN.md       Agent调用工具标准
│
├── A2A_DESIGN.md       Agent之间协同标准
│
└── EVALUATION.md       Agent质量治理

```