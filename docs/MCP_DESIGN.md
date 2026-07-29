# `docs/MCP_DESIGN.md`

定位：

> **Model Context Protocol 工具标准化设计文档**
---

```markdown
# MCP_DESIGN.md

# 政务多智能体协同平台
# MCP接口规范设计


Version: v1.0



---

# 1. 文档说明


本文档定义系统中 MCP(Model Context Protocol) 层的：

- 架构设计
- Server规范
- Tool定义规范
- Client调用流程
- Gateway设计
- 安全控制
- 审计机制


目标：

建立一个：

> 标准化、可扩展、可治理的 Agent Tool Ecosystem。


---

# 2. MCP设计背景


## 2.1 为什么引入MCP？


传统Agent调用方式：


```

Agent

|

Python Function

|

API

````


存在问题：

## 强耦合


Agent代码依赖具体业务接口。


例如：


```python

workflow.create_order()

````

业务变化：

Agent需要修改。

---

## 工具不可发现

LLM不知道：

当前有哪些能力。

需要人工维护Tool列表。

---

## 缺少统一规范

不同系统：

```
REST API

RPC

SDK

Database

```

接口形式不同。

---

# 2.2 MCP解决方案

采用：

```
                Agent


                  |

                  |

              MCP Client


                  |

                  |

             MCP Gateway


                  |

        +---------+---------+

        |         |         |

        v         v         v


    Policy    Material   Workflow

    Server     Server     Server


```

---

# 3. MCP整体架构

```

                         User


                          |

                          v


                  Supervisor Agent


                          |

                          v


                    Agent Runtime


                          |

                          v


                    MCP Client


                          |

                          v


                  MCP Gateway


                          |

       +------------------+------------------+

       |                  |                  |


       v                  v                  v


Policy MCP        Material MCP       Workflow MCP

Server            Server             Server


       |                  |                  |

       v                  v                  v


Milvus             OCR Service       Business API

PostgreSQL         Rule Engine       Workflow System



```

---

# 4. MCP核心组件设计

系统包含：

| 组件          | 职责        |
| ----------- | --------- |
| MCP Client  | Agent调用入口 |
| MCP Gateway | 统一管理入口    |
| MCP Server  | 业务能力提供方   |
| Tool        | 具体能力接口    |
| Schema      | 参数规范      |

---

# 5. MCP Client设计

## 5.1 职责

Agent侧负责：

* 获取工具列表
* 调用工具
* 管理上下文
* 记录调用日志

---

## 5.2 调用流程

```

Agent


 |

 |

tools/list


 |

 |

MCP Server


 |

 |

返回Tool列表


```

然后：

```

Agent


 |

 |

tools/call


 |

 |

Tool执行


 |

 |

Result


```

---

# 6. MCP Gateway设计

## 6.1 为什么需要Gateway？

不要让Agent直接访问Server。

原因：

* 统一鉴权
* 流量控制
* 审计
* 路由

---

## 6.2 Gateway职责

### 身份认证

```
user_id

tenant_id

role

```

---

### 权限控制

例如：

用户：

```
普通市民

```

禁止调用：

```
query_internal_case()

```

---

### 请求审计

记录：

```
trace_id

agent

tool

timestamp

result

```

---

# 7. MCP Server设计规范

系统定义三个核心Server。

---

# 7.1 Policy MCP Server

## 职责

提供政策知识查询能力。

---

## Tools

## search_policy

功能：

政策检索。

Request:

```json
{
"query":"餐饮许可证办理条件",
"top_k":5
}

```

Response:

```json
{

"documents":[

{

"title":"食品经营许可条例",

"content":"...",


"score":0.92

}

]

}

```

---

## get_policy_detail

Request:

```json
{

"document_id":"policy_001"

}

```

Response:

```json
{

"title":"",

"content":"",

"source":""

}

```

---

# 7.2 Material MCP Server

## 职责

材料审核。

---

## Tools

## extract_entity

功能：

OCR字段提取。

Request:

```json
{

"file_id":"xxx"

}

```

Response:

```json
{

"name":"张三",

"id_card":"110***********"

}

```

---

## check_material_complete

功能：

材料完整性检查。

Request:

```json
{

"business_type":"restaurant",

"materials":[]

}

```

Response:

```json
{

"passed":false,

"missing":[

"营业场所证明"

]

}

```

---

# 7.3 Workflow MCP Server

## 职责

业务流程执行。

---

## Tools

## create_case

创建办件。

Request:

```json
{

"user_id":"001",

"service":"restaurant_license"

}

```

Response:

```json
{

"case_id":"CASE001",

"status":"created"

}

```

---

## query_status

查询状态。

Request:

```json
{

"case_id":"CASE001"

}

```

Response:

```json
{

"status":"processing"

}

```

---

# 8. Tool Schema规范

所有Tool必须定义JSON Schema。

示例：

```json
{

"name":"search_policy",

"description":"搜索政策文件",

"inputSchema":{

"type":"object",

"properties":{

"query":{

"type":"string"

},

"top_k":{

"type":"integer"

}

}

}

}

```

要求：

* 参数明确
* 类型固定
* 描述完整

---

# 9. tools/list机制

Agent启动时：

```

MCP Client


 |

tools/list


 |

MCP Gateway


 |

MCP Server


```

返回：

```json
{

"tools":[

{

"name":"search_policy",

"description":"政策检索"

},

{

"name":"create_case",

"description":"创建办件"

}

]

}

```

Agent根据任务选择工具。

---

# 10. tools/call调用流程

完整流程：

```

User Query


 |

Supervisor


 |

Policy Agent


 |

MCP Client


 |

tools/call


 |

Policy MCP Server


 |

Milvus


 |

Result


 |

Agent State


```

---

# 11. MCP调用状态记录

所有调用必须进入State。

结构：

```python

class MCPCallRecord:


    trace_id:str


    server_name:str


    tool_name:str


    input_args:dict


    output_result:dict


    latency_ms:float


    status:str



```

---

# 12. MCP安全设计

## 12.1 RBAC权限

注意：

MCP协议本身不负责权限。

权限由Gateway实现。

流程：

```

Request


 |

RBAC Middleware


 |

Permission Check


 |

MCP Server


```

---

# 12.2 PII保护

敏感字段禁止进入日志。

例如：

身份证：

```
110***********1234

```

手机号：

```
138****1234

```

---

# 12.3 Tool调用限制

例如：

普通Agent：

允许：

```
search_policy

```

禁止：

```
delete_case

```

---

# 13. MCP异常处理

## Tool超时

策略：

```
Retry

↓

Fallback

↓

Return Error

```

---

## Tool失败

返回标准错误：

```json
{

"error_code":"TOOL_FAILED",

"message":"policy service unavailable"

}

```

---

# 14. MCP与LangGraph集成

架构：

```

LangGraph Node


       |

       |

MCP Client


       |

       |

Tool Result


       |

       |

Update State



```

示例：

```python

def policy_agent(state):


    result = mcp_client.call_tool(

        "search_policy",

        {

        "query":state.query

        }

    )


    state.evidence=result


    return state



```

---

# 15. MCP扩展机制

新增能力：

例如：

医保查询。

只需要：

```
mcp/

 |

servers/

    |

    medical_server/


```

新增Tool：

```
query_medical_record

```

Agent无需修改。

---

# 16. MCP设计原则总结

## 标准化

统一工具协议。

## 解耦

Agent与业务系统隔离。

## 可发现

动态获取能力。

## 可治理

统一审计。

## 可扩展

插件化Server。

最终形成：

```

Agent

+

MCP Ecosystem

+

Business Capability


```

---

# 17. 面试回答模板

## Q:

为什么不用普通API？

回答：

> 普通API解决的是系统调用问题，而MCP解决的是Agent调用工具的标准化问题。我们的Agent不直接依赖业务接口，而通过MCP Client动态发现工具能力，通过Gateway统一做鉴权和审计，因此新增业务能力时无需修改Agent逻辑。

---

## Q:

MCP有没有权限管理？

回答：

> MCP本身主要解决工具描述和通信规范，不负责业务权限。所以我们在MCP Gateway层增加RBAC控制，根据用户身份、Agent角色和Tool权限进行动态校验。

---

## Q:

你项目中MCP真正落地在哪里？

回答：

> 我们主要抽象了政策查询、材料审核、流程执行三个领域能力，每个领域作为独立MCP Server提供标准Tool，Agent通过MCP Client调用，实现工具层解耦。

```
这份 `MCP_DESIGN.md` 和你的项目架构已经形成闭环：

ARCHITECTURE.md
|
|
AGENT_DESIGN.md
|
|
MCP_DESIGN.md
|
|
A2A_DESIGN.md
|
|
EVALUATION.md

```
