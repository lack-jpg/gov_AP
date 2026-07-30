# STRUCTURE.md

# 项目文件清单与开发指引

> 每个文件标注了：**用途**（这个文件是做什么的）和 **下一步**（你该在这个文件里写什么代码）

---

# 1. 根目录文件

## README.md
- **用途**：项目说明、架构概览、快速开始、开发指南
- **下一步**：✅ 已更新，后续随项目迭代补充实际运行截图和API文档链接

## CLAUDE.md
- **用途**：AI编码规范（Cursor/Claude Code/Copilot 读取），定义编码约束、架构原则
- **下一步**：✅ 已完成 v3.0

## STRUCTURE.md
- **用途**：项目文件清单和每个文件的开发指引（本文件）
- **下一步**：✅ 当前文件，随项目新增文件同步更新

## .env.example
- **用途**：环境变量模板（LLM密钥、数据库地址、Redis、Milvus等配置）
- **下一步**：✅ 已配置所有核心变量，后续新增服务时追加对应环境变量

## .gitignore
- **用途**：Git忽略规则（__pycache__、.env、venv、模型文件等）
- **下一步**：✅ 已完成，根据实际开发需要微调

## example.py
- **用途**：Python文件的docstring头模板（Author/Date/Version/Task格式）
- **下一步**：✅ 已完成，不需要修改

---

# 2. agents/ — Agent层

## agents/__init__.py
- **用途**：Agent注册中心，管理所有Agent的注册、发现、生命周期
- **状态**：✅ 已完成（126行）
  - `AgentRegistry` 类：register/get/list/list_active/health_check/set_status/get_metadata/unregister/clear
  - `get_agent_registry()` 全局单例工厂

---

## agents/supervisor/ — Supervisor Agent（编排者）

### agents/supervisor/__init__.py
- **用途**：Supervisor包初始化
- **下一步**：导出 `SupervisorAgent` 类

### agents/supervisor/agent.py
- **用途**：Supervisor核心逻辑 —— 接收用户请求 → 规划 → 路由 → 汇总结果
- **状态**：✅ 已完成（~200行）
  - `SupervisorAgent` 类：`orchestrate()` 主循环（4场景：初始/错误/完成/继续）
  - `handle_intent_result()` 基于意图重新规划
  - `handle_error_and_replan()` 错误恢复（最多3次重试，跳过失败任务）
  - `_synthesize()` 汇总 policy + material 结果生成最终回答
  - 构造函数接收 `llm: Optional[BaseChatModel]`，无LLM时用规则模式

### agents/supervisor/planner.py
- **用途**：任务规划器 —— LLM-based将用户自然语言需求拆解为子任务序列
- **状态**：✅ 已完成（~230行）
  - `Planner` 类：LLM+规则混合策略（`_llm_plan` + `_rule_plan` 兜底）
  - `plan(state)` → `list[Task]`，`replan_on_error(state, error)` 跳过失败任务
  - 5种intent预置标准任务模板（business_license, restaurant_license, fund_query...）
  - LLM输出JSON容错解析（正则提取 + `model_validate`）

### agents/supervisor/router.py
- **用途**：Agent路由器 —— 根据任务类型和意图选择合适的Agent
- **状态**：✅ 已完成（~170行）
  - `Router` 类：4层路由策略（精确匹配 → 模糊匹配 → LLM → 关键词推断）
  - `ROUTING_TABLE`：16条 task_type→AgentName 映射
  - `route(task)` → `AgentName`，`route_batch(tasks)` 批量路由
  - `_infer_by_keyword()` 中文关键词兜底推断

### agents/supervisor/prompts.py
- **用途**：Supervisor Agent的Prompt模板（版本化管理）
- **状态**：✅ 已完成（~140行）
  - `SUPERVISOR_SYSTEM_PROMPT`：角色+职责+可调度Agent表+输出格式
  - `PLANNER_SYSTEM_PROMPT` + `PLANNER_USER_PROMPT`：任务拆解模板（含{intent}和{context}占位符）
  - `ROUTER_SYSTEM_PROMPT` + `ROUTER_USER_PROMPT`：路由判断模板
  - `SUPERVISOR_SYNTHESIS_PROMPT`：结果汇总模板（含{policy_result}/{material_result}占位符）

---

## agents/intent/ — Intent Agent（意图识别）

### agents/intent/__init__.py
- **用途**：Intent包初始化
- **下一步**：导出 `IntentAgent` 类

### agents/intent/agent.py
- **用途**：Intent Agent核心 —— 3级分类（BERT→关键词→LLM fallback）
- **状态**：✅ 已完成（130行）
  - `IntentAgent` 类：classify() → process() LangGraph节点接口
  - 三级策略链：BERT分类器 → 关键词匹配 → LLM fallback
  - 构造函数接收 classifier + llm + bert_threshold

### agents/intent/classifier.py
- **用途**：意图分类器 —— BERT模型推理 + 关键词匹配兜底
- **状态**：✅ 已完成（169行）
  - `IntentClassifier` 类：3级分类链（_bert_classify → _keyword_classify）
  - 18条关键词→意图映射表（餐馆→restaurant_license, 公司→business_register...）
  - _bert_classify 为stub（TODO: 加载真实 fine-tuned BERT）
  - BERT_CONFIDENCE_THRESHOLD=0.7，低于此值触发LLM fallback

### agents/intent/schema.py
- **用途**：Intent Agent的数据模型（Pydantic v2）
- **状态**：✅ 已完成（64行）
  - `IntentLabel` — {label_id, label_name, category}
  - `IntentResult` — {label, label_name, confidence, source}
  - `IntentClassificationResult` — 多分类结果（含candidates）
  - `INTENT_LABELS` — 10个预定义标签常量

### agents/intent/prompts.py
- **用途**：Intent Agent的Prompt模板
- **状态**：✅ 已完成（48行）
  - `INTENT_CLASSIFICATION_PROMPT` — LLM分类模板（含10种标签+分类原则）
  - `FEW_SHOT_EXAMPLES` — 5条 few-shot 示例

---

## agents/policy/ — Policy Agent（政策检索）

### agents/policy/__init__.py
- **用途**：Policy包初始化
- **下一步**：导出 `PolicyAgent` 类

### agents/policy/agent.py
- **用途**：Policy Agent核心 —— RAG管线编排 + 模板兜底
- **状态**：✅ 已完成（165行）
  - `PolicyAgent` 类：search() → search_with_intent() → process() LangGraph节点
  - LLM+模板双模式：有LLM走RAG流程，无LLM用关键词模板
  - 5种业务模板回答（餐馆/企业注册/公积金/不动产/通用）
  - TODO: 接入 rag/ 模块的完整 RAG 管线

### agents/policy/schema.py
- **用途**：Policy Agent的数据模型
- **状态**：✅ 已完成（28行）
  - `PolicyDocument` — {title, content, source, page, score}
  - `PolicyEvidence` — {source, excerpt, page, relevance_score}
  - `PolicyResult` — {answer, evidence[], confidence, retrieved_count}

### agents/policy/prompts.py
- **用途**：Policy Agent的Prompt模板
- **状态**：✅ 已完成（27行）
  - `POLICY_RAG_PROMPT` — RAG回答生成模板（role + 输出格式JSON）

---

## agents/material/ — Material Agent（材料审核）

### agents/material/__init__.py
- **用途**：Material包初始化
- **下一步**：导出 `MaterialAgent` 类

### agents/material/agent.py
- **用途**：Material Agent核心 —— 材料完整性审核 + 建议
- **状态**：✅ 已完成（118行）
  - `MaterialAgent` 类：review() + process() LangGraph节点接口
  - 5种业务类型的 REQUIRED_MATERIALS 清单（restaurant_license/business_license/business_register/property_service/fund_query）
  - _check_warnings() 温馨提示生成
  - TODO: OCR + 实体抽取接入

### agents/material/ocr.py
- **用途**：OCR识别 —— 从文档图片/PDF中提取文字（⏳ Phase 2）

### agents/material/extractor.py
- **用途**：实体抽取 —— 从OCR文本中提取关键字段（⏳ Phase 2）

### agents/material/validator.py
- **用途**：规则校验 —— 检查提交材料是否满足业务要求（⏳ Phase 2）

### agents/material/prompts.py
- **用途**：Material Agent的Prompt模板（⏳ Phase 2）

---

## agents/workflow/ — Workflow Agent（流程执行）

### agents/workflow/agent.py
- **用途**：Workflow Agent核心 —— 通过MCP Client调用业务系统
- **状态**：✅ 已完成（114行）
  - `WorkflowAgent` 类：create_case() + query_status() + process()
  - MCP stub 模式：模拟 CASE_XXXXXXXX 办件号 + log_mcp_call 记录
  - TODO: 接入真实 MCP Client

---

## agents/governance/ — Governance Agent（安全治理，旁路）

### agents/governance/agent.py
- **用途**：Governance Agent核心 —— 协调安全检查、行为监控、优化建议
- **状态**：✅ 已完成（99行）
  - `GovernanceAgent` 类：check() 输入→输出→行为分析三级检查
  - process() LangGraph节点接口 + generate_optimization_suggestions()
  - **旁路控制，不参与业务回答**

### agents/governance/security.py
- **用途**：安全检测 —— PII/注入/敏感词/泄露4类检测
- **状态**：✅ 已完成（165行）
  - `SecurityChecker` 类：check_input() + check_output()
  - PII正则（手机/身份证/邮箱）+ 8条注入特征 + 8个敏感词
  - _detect_internal_leak() 输出泄露检测（traceback/API_KEY/SECRET/SystemMessage）

### agents/governance/behavior.py
- **用途**：行为分析 —— 循环检测、异常行为识别
- **状态**：✅ 已完成（93行）
  - `BehaviorAnalyzer` 类：analyze() 4维度检测
  - 工具循环（滑动窗口） + MCP步数过多(>20) + Token消耗过大(>100K)
  - _detect_loop() 窗口6/阈值3

### agents/governance/optimizer.py
- **用途**：自动优化 —— 分析trace和evaluation结果，生成优化建议
- **状态**：✅ 已完成（127行）
  - `Optimizer` 类：analyze() 4维度（失败率>20%/步数>5/延迟>5000ms/Tool频率>10）
  - suggest_prompt_improvement() 基于失败case的Prompt改进建议

---

# 3. orchestration/ — LangGraph编排层

## orchestration/__init__.py
- **用途**：编排层包初始化
- **下一步**：导出 `AgentRuntime` 和 `build_graph` 工厂函数

## orchestration/langgraph/__init__.py
- **用途**：LangGraph包初始化
- **下一步**：导出核心类

---

### orchestration/langgraph/state.py
- **用途**：定义所有Agent节点共享的AgentState（TypedDict）+ 10个Pydantic子模型
- **状态**：✅ 已完成（~680行，117条冒烟测试通过）
  - **7个枚举**：RiskLevel, TaskStatus, MCPCallStatus, A2ATaskStatus, AgentName, NodeName
  - **10个Pydantic模型**：Task, Evidence, PolicyResult, IntentResult, MaterialCheckResult, MCPCallRecord, ToolCall, A2ATaskRecord, ExecutionMetrics, GuardrailResult — 65个字段全部带 `Field(description=...)`
  - **AgentState TypedDict**：24个字段，7个Annotated累加字段（task_plan/tool_calls/mcp_history/a2a_tasks/evidence/messages/error_history），3个自定义reducer
  - **14个Helper函数**：create_initial_state, set_intent, add_task, record_mcp_call, set_error, update_current_agent...
  - 运行 `python -m orchestration.langgraph.state` 执行117条冒烟测试

### orchestration/langgraph/graph.py
- **用途**：构建完整的LangGraph StateGraph
- **状态**：✅ 已完成（~170行）
  - `build_graph()` 工厂函数：注册6个节点，5组条件边，支持checkpointer注入
  - Graph结构: START → supervisor → {intent → supervisor} → {policy/material/workflow} → governance → END
  - `create_default_graph()` 便捷函数：无LLM纯stub模式，用于开发调试和CI
  - 节点通过 lambda 闭包注入 llm/supervisor 实例

### orchestration/langgraph/nodes.py
- **用途**：LangGraph节点函数 —— 每个节点包装一个Agent调用
- **状态**：✅ 已完成（~320行）
  - `supervisor_node()`：调用SupervisorAgent.orchestrate()
  - `intent_node()`：关键词stub分类（餐馆→restaurant_license, 公司→business_register...），TODO: 替换为BERT
  - `policy_node()`：3场景模板stub回答（餐饮/企业注册/公积金），TODO: 替换为RAG管线
  - `material_node()`：stub空审核（默认passed），TODO: 替换为OCR+实体抽取
  - `workflow_node()`：stub模拟办件（生成CASE_XXXXXXXX），TODO: 替换为MCP调用
  - `governance_node()`：stub安全检查（默认通过），TODO: 替换为真实Guardrail
  - 全部节点记录MCP调用日志 + error处理

### orchestration/langgraph/edges.py
- **用途**：条件路由函数 —— 根据state决定下一个节点
- **状态**：✅ 已完成（~190行）
  - `route_after_supervisor()`：4阶段遍历（无intent→intent, 无plan→supervisor, pending task→对应agent, 完成→governance）
  - `route_after_intent()`：回supervisor做二次规划
  - `route_after_specialist()`：错误→supervisor, 高风险→governance, 否则继续route_after_supervisor
  - `route_after_governance()`：blocked→END, waiting_a2a→END(挂起), error+retry<3→supervisor, 正常→END
  - `route_on_start()`：起始路由

### orchestration/langgraph/checkpointer.py
- **用途**：PostgreSQL Checkpointer —— LangGraph状态持久化 + A2A挂起/恢复
- **状态**：✅ 已完成（310行）
  - `PostgresCheckpointer(BaseCheckpointSaver)`：aget_tuple/alist/aput/aput_writes/adelete_thread
  - suspend_for_a2a() / resume_from_a2a() A2A异步任务支持
  - `_CheckpointRow` 独立ORM表（langgraph_checkpoints）
  - 序列化使用 JsonPlusSerializer

### orchestration/langgraph/runtime.py
- **用途**：Agent Runtime安全控制 —— 步骤限制、循环检测、超时控制
- **状态**：✅ 已完成（394行，22条测试通过）
  - `RuntimeConfig` dataclass（max_steps=10, loop_window=6, loop_threshold=3, timeout=30s, max_retries=3）
  - `LoopDetector` 类：feed()/feed_batch()/reset()/recent_tools
  - `AgentRuntime` 类：execute_with_safeguards()/check_step()/check_loop_detected()
  - `RuntimeExceededError`/`RuntimeTimeoutError`/`RuntimeLoopDetectedError` 3个异常类
  - `create_runtime_from_settings()` 工厂函数
  - 运行 `python -m orchestration.langgraph.runtime` 执行22条测试

---

# 4. tools/ — 工具生态层

## tools/__init__.py
- **用途**：工具层包初始化
- **下一步**：导出MCP和A2A的核心类

---

## tools/mcp/ — MCP协议（Agent → Tool）

### tools/mcp/__init__.py
- **用途**：MCP包初始化
- **下一步**：导出 `MCPClient`, `MCPGateway`

### tools/mcp/client.py
- **用途**：MCP Client —— Agent侧调用入口，负责工具发现和调用
- **下一步**：实现 `MCPClient` 类：
  - `list_tools() -> List[ToolSchema]` — 工具发现
  - `call_tool(name: str, arguments: dict) -> ToolResult` — 工具调用
  - `get_tool_schema(name: str) -> ToolSchema` — 获取工具Schema
  - 记录每次调用的 trace_id, latency, status

### tools/mcp/gateway.py
- **用途**：MCP Gateway —— 统一鉴权、限流、审计、路由
- **下一步**：实现 `MCPGateway` 类：
  - `authenticate(user_id, token) -> bool` — 身份认证
  - `authorize(user_id, tool_name) -> bool` — RBAC权限检查
  - `route(tool_name: str) -> str` — 路由到对应MCP Server
  - `audit(trace_id, agent, tool, result)` — 审计日志

### tools/mcp/schema.py
- **用途**：所有MCP工具的JSON Schema定义
- **下一步**：定义每个Tool的 inputSchema 和 outputSchema：
  - `SEARCH_POLICY_SCHEMA` — {query: str, top_k: int} → {documents: [...]}
  - `GET_POLICY_DETAIL_SCHEMA` — {document_id: str} → {title, content, source}
  - `EXTRACT_ENTITY_SCHEMA` — {file_id: str} → {entities: {...}}
  - `CHECK_MATERIAL_SCHEMA` — {business_type, materials: [...]} → {passed, missing}
  - `CREATE_CASE_SCHEMA` — {user_id, service} → {case_id, status}
  - `QUERY_STATUS_SCHEMA` — {case_id} → {status}

---

### tools/mcp/servers/policy_server/

#### tools/mcp/servers/policy_server/__init__.py
- **用途**：Policy MCP Server包初始化
- **下一步**：导出 `PolicyMCPServer`

#### tools/mcp/servers/policy_server/server.py
- **用途**：Policy MCP Server入口 —— 注册tools、启动MCP服务
- **下一步**：实现 `PolicyMCPServer`：
  - 使用 `mcp` 库创建Server实例
  - 注册 `search_policy` 和 `get_policy_detail` 工具
  - 配置host/port
  - 启动server

#### tools/mcp/servers/policy_server/tools.py
- **用途**：Policy MCP工具实现 —— search_policy + get_policy_detail
- **下一步**：实现两个工具函数：
  - `search_policy(query, top_k)` — 调用RAG管线（embedding → Milvus → BM25 → Reranker）
  - `get_policy_detail(document_id)` — 从PostgreSQL/Milvus获取文档详情

---

### tools/mcp/servers/material_server/

#### tools/mcp/servers/material_server/__init__.py
- **用途**：Material MCP Server包初始化
- **下一步**：导出 `MaterialMCPServer`

#### tools/mcp/servers/material_server/server.py
- **用途**：Material MCP Server入口
- **下一步**：实现 `MaterialMCPServer`，注册extract_entity和check_material工具

#### tools/mcp/servers/material_server/tools.py
- **用途**：Material MCP工具实现
- **下一步**：实现两个工具函数：
  - `extract_entity(file_id)` — OCR + 实体抽取
  - `check_material(business_type, materials)` — 规则校验

---

### tools/mcp/servers/workflow_server/

#### tools/mcp/servers/workflow_server/__init__.py
- **用途**：Workflow MCP Server包初始化
- **下一步**：导出 `WorkflowMCPServer`

#### tools/mcp/servers/workflow_server/server.py
- **用途**：Workflow MCP Server入口
- **下一步**：实现 `WorkflowMCPServer`，注册create_case和query_status工具

#### tools/mcp/servers/workflow_server/tools.py
- **用途**：Workflow MCP工具实现
- **下一步**：实现两个工具函数：
  - `create_case(user_id, service)` — 创建办件记录
  - `query_status(case_id)` — 查询办件状态

---

## tools/a2a/ — A2A协议（Agent → Agent）

### tools/a2a/__init__.py
- **用途**：A2A包初始化
- **下一步**：导出 `A2AConnector`, `AgentRegistry`, `TaskManager`

### tools/a2a/connector.py
- **用途**：A2A连接器 —— 向外部Agent发送任务
- **下一步**：实现 `A2AConnector` 类：
  - `send_task(target_agent_id, task: A2ATask) -> str` — 发送任务，返回task_id
  - `check_status(task_id) -> TaskStatus` — 查询任务状态
  - `cancel_task(task_id) -> bool` — 取消任务

### tools/a2a/protocol.py
- **用途**：A2A通信协议定义 —— Agent Card, 消息格式, 任务结构
- **下一步**：定义 Pydantic 模型：
  - `AgentCard` — {agent_id, name, description, skills, url, authentication}
  - `Skill` — {name, description, input_schema, output_schema}
  - `A2AMessage` — {from_agent, to_agent, task_id, type, payload}

### tools/a2a/task.py
- **用途**：A2A任务生命周期管理
- **下一步**：实现 `A2ATask` 和 `TaskManager`：
  - Task状态机：created → submitted → working → completed/failed/timeout
  - `TaskManager.create_task(...)` — 创建任务
  - `TaskManager.update_status(task_id, status)` — 更新状态
  - `TaskManager.get_task(task_id)` — 获取任务详情

### tools/a2a/registry.py
- **用途**：外部Agent注册中心
- **下一步**：实现 `AgentRegistry` 类：
  - `register(agent_card: AgentCard)` — 注册Agent
  - `discover(skill_name: str) -> List[AgentCard]` — 按技能发现Agent
  - `health_check(agent_id: str) -> bool` — 健康检查
  - `list_agents() -> List[AgentCard]` — 列出所有Agent

### tools/a2a/callback.py
- **用途**：A2A回调处理 —— 接收外部Agent的异步结果，恢复LangGraph执行
- **下一步**：实现 `CallbackHandler` 类：
  - `handle_callback(task_id, status, artifact)` — 处理回调
  - `resume_workflow(task_id, result)` — 恢复LangGraph执行
  - 回调API: `POST /api/a2a/callback` — {task_id, status, artifact}

### tools/a2a/mock_agents/__init__.py
- **用途**：Mock Agent包初始化
- **下一步**：导出模拟Agent类

### tools/a2a/mock_agents/housing_agent.py
- **用途**：模拟不动产查询Agent（测试A2A协议）
- **下一步**：实现 `HousingAgent`：
  - 技能：`query_property(user_id)` → {property_count, properties: [...]}
  - 模拟5-10秒延迟（模拟跨网络调用）

### tools/a2a/mock_agents/fund_agent.py
- **用途**：模拟公积金查询Agent（测试A2A协议）
- **下一步**：实现 `FundAgent`：
  - 技能：`query_fund(user_id)` → {balance, monthly_payment, ...}
  - 模拟3-8秒延迟

---

# 5. rag/ — RAG检索增强

## rag/__init__.py
- **用途**：RAG包初始化
- **下一步**：导出 `RAGPipeline` 类

### rag/embedding.py
- **用途**：文本向量化 —— BGE-large-zh-v1.5 模型
- **状态**：✅ 已完成框架（78行，stub就绪）
  - `EmbeddingEngine` 类：encode_query()/encode_documents()/load_model()
  - 默认模型 BAAI/bge-large-zh-v1.5，DIM=1024
  - 当前返回零向量（stub），TODO: 接入 sentence-transformers

### rag/retriever.py
- **用途**：混合检索 —— Milvus + BM25 + RRF融合
- **状态**：✅ 已完成框架（134行，stub就绪）
  - `HybridRetriever` 类：hybrid_search()/dense_search()/sparse_search()
  - RRF (Reciprocal Rank Fusion) 融合算法实现（alpha权重 + k平滑参数）
  - 当前返回空结果（stub），TODO: 接入 pymilvus + BM25

### rag/reranker.py
- **用途**：重排序 —— bge-reranker-v2-m3
- **状态**：✅ 已完成框架（66行，stub就绪）
  - `Reranker` 类：rerank() + _model_rerank() + load_model()
  - Stub 模式按顺序递减打分（0.95→0.85→...）

### rag/generator.py
- **用途**：LLM答案生成 —— 基于检索文档生成带evidence的答案
- **状态**：✅ 已完成（113行）
  - `Generator` 类：generate() LLM模式 + _simple_generate() 简单拼接兜底
  - GENERATOR_SYSTEM_PROMPT 模板（role + 输出JSON格式）
  - evidence自动构建（取top-3文档的source/excerpt/score）

### rag/knowledge_base.py
- **用途**：知识库管理 —— 文档加载、切分、索引
- **状态**：✅ 已完成（173行）
  - `KnowledgeBase` 类：load_documents()/split_documents()/index_documents()/rebuild_index()
  - 支持 TXT/MD/PDF/DOCX 格式（PDF/DOCX stub）
  - 滑动窗口切分（默认512字符，64重叠）

---

# 6. governance/ — AgentOps治理层

## governance/__init__.py
- **用途**：治理层包初始化
- **下一步**：导出 Trace、Guardrail、Evaluation 核心类

### governance/trace.py
- **用途**：全链路追踪 —— 基于OpenTelemetry记录Agent执行的每个步骤
- **下一步**：实现 `TraceCollector` 类：
  - `start_trace(trace_id, user_query) -> Span` — 创建根span
  - `record_agent_call(span, agent_name, input, output, latency, token_usage)` — 记录Agent span
  - `record_tool_call(span, tool_name, input, output, latency, status)` — 记录Tool span
  - 导出到OpenTelemetry Collector + PostgreSQL

### governance/guardrail.py
- **用途**：安全护栏 —— 输入检测 + 输出过滤
- **下一步**：实现 `Guardrail` 类：
  - `check_input(text: str) -> GuardrailResult` — 检测PII/Injection/Sensitive
  - `check_output(text: str) -> GuardrailResult` — 过滤Error/Secret/Prompt leak
  - `block_if_dangerous(result) -> bool` — 是否应该拦截

### governance/pii.py
- **用途**：PII脱敏 —— 手机号、身份证、邮箱自动掩码
- **下一步**：实现 `PIIDesensitizer` 类：
  - `mask_phone(text) -> str` — 138****1234
  - `mask_id_card(text) -> str` — 110***********1234
  - `mask_email(text) -> str` — u***@domain.com
  - `detect_pii(text) -> List[PIIMatch]` — 检测PII位置和类型

### governance/monitor.py
- **用途**：Agent监控 —— Prometheus指标暴露
- **下一步**：实现 `AgentMonitor` 类：
  - 指标：agent_success_rate, agent_latency_seconds, agent_errors_total, tool_success_rate, tool_latency_seconds
  - `record_execution(agent_name, latency, success, error)` — 记录指标
  - 暴露 `/metrics` 端点给Prometheus

### governance/dashboard.py
- **用途**：运维看板数据API —— 提供Agent运行统计、评测趋势等数据
- **下一步**：实现 `DashboardAPI` 类：
  - `get_agent_stats(time_range) -> AgentStats` — Agent运行统计
  - `get_evaluation_trends() -> List[EvaluationTrend]` — 评测趋势
  - `get_version_comparison(v1, v2) -> VersionDiff` — 版本对比

---

## governance/evaluation/ — 自动评测系统

### governance/evaluation/__init__.py
- **用途**：评测包初始化
- **下一步**：导出 `Evaluator`, `Benchmark`, `Runner`

### governance/evaluation/metrics.py
- **用途**：评测指标计算 —— RAG指标 + Agent指标
- **下一步**：实现：
  - **RAG指标**：`faithfulness(answer, context)`, `answer_relevance(answer, query)`, `context_recall(retrieved, ground_truth)`, `context_precision(retrieved, relevant)`
  - **Agent指标**：`task_success_rate(results)`, `tool_accuracy(predictions, ground_truth)`, `average_latency(traces)`, `average_step_count(traces)`
  - 使用 RAGAS 库计算RAG指标

### governance/evaluation/evaluator.py
- **用途**：评测引擎 —— 加载trace → 计算指标 → 生成报告
- **下一步**：实现 `Evaluator` 类：
  - `evaluate_rag(trace: Trace) -> RAGMetrics` — RAG质量评估
  - `evaluate_agent(trace: Trace) -> AgentMetrics` — Agent执行质量评估
  - `evaluate_security(trace: Trace) -> SecurityMetrics` — 安全评估
  - `generate_report(results) -> EvaluationReport` — 生成评测报告

### governance/evaluation/benchmark.py
- **用途**：基准测试 —— 加载Golden Dataset，运行Agent，对比预期结果
- **下一步**：实现 `Benchmark` 类：
  - `load_dataset(dataset_path) -> List[TestCase]` — 加载cases/*.json
  - `run_benchmark(dataset, agent_graph) -> BenchmarkResult` — 运行所有用例
  - `compare_versions(v1_results, v2_results) -> ComparisonReport` — 版本对比

### governance/evaluation/runner.py
- **用途**：评测流水线 —— CI/CD集成，定时或触发式运行评测
- **下一步**：实现 `EvaluationRunner` 类：
  - `run_pipeline()` — 完整流水线（load → execute → evaluate → report）
  - `run_on_commit()` — Git push触发评测
  - `run_scheduled(cron)` — 定时评测

---

# 7. database/ — 数据层

## database/__init__.py
- **用途**：数据库包初始化
- **下一步**：导出 `get_session`, `init_db` 工厂函数

### database/connection.py
- **用途**：数据库连接管理 —— async SQLAlchemy + asyncpg
- **状态**：✅ 已完成（104行）
  - `create_engine()`/`create_session_factory()` 工厂函数
  - `get_engine()`/`get_session_factory()` 惰性单例
  - `get_db()` FastAPI异步依赖注入（async generator, 自动commit/rollback/close）
  - `init_db()`/`close_db()` 应用启停管理

### database/models.py
- **用途**：SQLAlchemy ORM模型
- **状态**：✅ 已完成（310行）
  - **Trace表**（21字段）：trace_id, span_id, parent_span_id, agent_name, node_name, input/output_data, tool_name/input/output, latency_ms, input/output_tokens, status, error_message, risk_level, metadata_, created_at
  - **Agent表**（8字段）：agent_id, name, version, config(JSON), status, description, created_at, updated_at
  - **Prompt表**（8字段）：prompt_id, agent_name, name, version, content, variables(JSON), is_active, created_by, created_at
  - **Evaluation表**（13字段）：eval_id, version, 7项指标, total_cases, passed_cases, report_json(JSON), created_at
  - **Checkpoint表**（7字段）：checkpoint_id, task_id, thread_id, state_json(JSON), checkpoint_data(JSON), status, created_at
  - 全部字段带 comment + `mapped_column`

### database/schemas.py
- **用途**：Pydantic v2序列化模型（与ORM模型对应）
- **状态**：✅ 已完成（133行）
  - TraceCreate/TraceResponse, AgentCreate/AgentResponse
  - PromptCreate/PromptResponse, EvaluationCreate/EvaluationResponse
  - CheckpointCreate/CheckpointResponse
  - from_attributes=True 支持 ORM 直接转 Pydantic

### database/migrations/__init__.py
- **用途**：Alembic数据库迁移
- **下一步**：配置Alembic环境，生成初始迁移脚本

---

# 8. backend/ — FastAPI接入层

## backend/__init__.py
- **用途**：后端包初始化
- **下一步**：导出 `create_app` 工厂函数

### backend/main.py
- **用途**：FastAPI应用入口 —— app创建、中间件注册、路由挂载
- **状态**：✅ 已完成（~150行）
  - `create_app()` 工厂函数：CORS + RequestLoggingMiddleware + 全局异常处理 + /api路由 + /health
  - `lifespan()` async context manager：startup调用setup_logging + 打印配置摘要，shutdown清理
  - 模块级 `app` 实例（uvicorn入口: `backend.main:app`）

### backend/config.py
- **用途**：应用配置管理 —— 基于pydantic-settings读.env
- **状态**：✅ 已完成（~240行）
  - `Settings(BaseSettings)` 类：30+字段，覆盖 App / LLM / Embedding / PostgreSQL / Redis / Milvus / Agent Runtime / MCP / A2A / JWT / OpenTelemetry / LangSmith / CORS
  - 计算属性：`postgres_url`（asyncpg）、`postgres_sync_url`（psycopg）、`redis_url`
  - `get_settings()` lru_cache单例 + 模块级 `settings` 便捷引用
  - 全部字段支持 `.env` 文件和环境变量，带 `env_prefix` alias

---

## backend/api/

### backend/api/__init__.py
- **用途**：API包初始化
- **下一步**：导出所有router

### backend/api/routes.py
- **用途**：API端点定义
- **状态**：✅ 已完成（~230行）
  - `POST /api/chat`：核心端点，接收ChatRequest → execute_agent → 提取evidence/elapsed/risk_level → 返回ChatResponse
  - `GET /api/agent/status/{trace_id}`：stub（TODO: 从DB/Redis查询真实状态）
  - `POST /api/a2a/callback`：stub（TODO: 按task_id恢复LangGraph checkpoint）
  - `GET /api/dashboard/overview`：stub（TODO: 从Trace统计真实数据）
  - `GET /api/evaluation/report/{version}`：stub（TODO: 从evaluation表读取）

### backend/api/dependencies.py
- **用途**：FastAPI依赖注入 —— DB session, current user, agent runtime
- **状态**：✅ 已完成（~140行）
  - `get_user_id()`：从X-User-Id Header提取，无则401
  - `get_trace_id()`：从X-Trace-Id Header提取，无则自动生成
  - `get_config()`：Settings单例注入
  - `get_agent_graph()`：惰性单例StateGraph（首次调用时根据settings.llm_api_key决定LLM/stub模式）
  - `execute_agent()`：create_initial_state → graph.ainvoke，封装递归限制和config

### backend/api/schemas.py
- **用途**：API请求/响应的Pydantic模型
- **状态**：✅ 已完成（~230行）
  - **Request**：ChatRequest, AgentStatusRequest, A2ACallbackRequest, EvaluationRequest
  - **Response**：ChatResponse(trace_id/answer/evidence/risk_level/elapsed_ms), AgentStatusResponse, A2ACallbackResponse, DashboardOverview, EvaluationMetricsResponse
  - **通用**：EvidenceItem, ErrorResponse（统一错误格式）
  - 全部字段带 `Field(description=...)` 和 `ge/le` 约束

---

## backend/middleware/

### backend/middleware/__init__.py
- **用途**：中间件包初始化
- **下一步**：导出所有中间件

### backend/middleware/auth.py
- **用途**：JWT认证中间件
- **状态**：✅ 已完成（155行）
  - `get_current_user()` DI：JWT decode + sub/role/tenant_id 提取
  - `get_optional_user()` DI：可选鉴权（有Token解析，无则None）
  - `AuthMiddleware` 类：Bearer Token优先 → X-User-Id降级 → 401
  - `create_access_token()` 工具函数

### backend/middleware/rbac.py
- **用途**：RBAC权限中间件（⏳ Phase 2）

### backend/middleware/logging.py
- **用途**：已迁移至 `tools/logger.py`
- **状态**：✅ 已迁移（tools/logger.py，531行，20条测试）
  - **3个ContextVar / 3个Format函数 / setup_logging() / RequestLoggingMiddleware(BaseHTTPMiddleware) / log_agent_call() / log_mcp_call() / get_logger()**
  - 运行时日志写入 `logger/` 目录（gitignore）
  - 运行 `python tools/logger.py` 执行20条冒烟测试

### backend/middleware/tracing.py
- **用途**：OpenTelemetry链路追踪中间件（⏳ Phase 3）

---

## backend/services/

### backend/services/agent_service.py
- **用途**：Agent编排服务 —— 管理Agent生命周期
- **状态**：✅ 已完成（159行）
  - `AgentService` 类：initialize() 注册6个Agent + 构建Graph
  - `execute()` 带Runtime安全护栏的完整工作流执行
  - `resume_from_checkpoint()` A2A异步任务恢复
  - `get_graph()` 获取已编译的StateGraph

---

# 9. prompts/ — Prompt管理

## prompts/__init__.py
- **用途**：Prompt包初始化
- **下一步**：导出 `PromptRegistry`

### prompts/registry.py
- **用途**：Prompt注册中心 —— 版本化Prompt管理
- **下一步**：实现 `PromptRegistry` 类：
  - `register(name, version, content, agent)` — 注册Prompt
  - `load(name, version=None) -> Prompt` — 加载Prompt（version=None加载最新active版本）
  - `compare(v1, v2) -> PromptDiff` — 对比两个版本
  - `set_active(name, version)` — 设置活跃版本
  - 每个Prompt结构：{Role, Goal, Constraints, Tools, Output Schema, Examples}

---

# 10. cases/ — 评测用例

## cases/__init__.py
- **用途**：用例包初始化
- **下一步**：导出用例加载函数

### cases/intent_cases.json
- **用途**：意图分类测试用例
- **下一步**：填充真实测试数据：
  ```json
  {
    "id": "intent_001",
    "query": "我要开一家餐馆",
    "expected_intent": "business_license",
    "expected_labels": ["business_license"]
  }
  ```

### cases/rag_cases.json
- **用途**：RAG评测用例
- **下一步**：填充测试数据：{query, expected_answer, expected_sources}

### cases/agent_cases.json
- **用途**：Agent评测用例（多Agent协同）
- **下一步**：填充测试数据：{query, expected_intent, expected_tools, expected_final_state}

### cases/security_cases.json
- **用途**：安全评测用例
- **下一步**：填充测试数据：{input, expected_blocked, reason}（包含PII/Injection/Jailbreak测试）

### cases/business_license.json
- **用途**：营业执照办理场景端到端测试
- **下一步**：✅ 已有基础框架，补充完整流程的expected_answer

### cases/policy_query.json
- **用途**：政策查询场景测试
- **下一步**：填充政策查询相关的测试用例

### cases/workflow.json
- **用途**：流程执行场景测试
- **下一步**：填充完整办件流程的测试用例

---

# 11. deploy/ — 部署配置

## deploy/Dockerfile
- **用途**：Docker镜像构建文件
- **下一步**：实现多阶段构建：
  - Stage 1：安装依赖（利用缓存层）
  - Stage 2：复制代码、设置入口（uvicorn main:app）

## deploy/docker-compose.yml
- **用途**：本地开发环境一键启动
- **下一步**：定义5个服务：
  - **api**：FastAPI backend（端口8000）
  - **postgres**：PostgreSQL 16（端口5432）
  - **redis**：Redis 7（端口6379）
  - **milvus**：Milvus 2.5（端口19530）
  - 配置网络和卷挂载

## deploy/k8s/backend.yaml
- **用途**：K8s Backend Deployment + Service
- **下一步**：编写Deployment配置（replicas=3, resource limits, liveness probe）

## deploy/k8s/agent.yaml
- **用途**：K8s Agent Runtime Deployment
- **下一步**：编写Deployment配置（状态敏感，配合Redis+PostgreSQL Checkpoint）

## deploy/k8s/model.yaml
- **用途**：K8s GPU模型服务（vLLM）
- **下一步**：编写Deployment配置（GPU node selector, vLLM startup command）

## deploy/k8s/mcp.yaml
- **用途**：K8s MCP Server Deployment
- **下一步**：编写Deployment配置（3个MCP Server独立部署）

## deploy/k8s/postgres.yaml
- **用途**：K8s PostgreSQL StatefulSet + Service
- **下一步**：编写StatefulSet配置（持久化存储, 主从复制）

## deploy/k8s/ingress.yaml
- **用途**：K8s Ingress配置
- **下一步**：编写Ingress规则（域名路由, TLS termination）

---

# 12. models/ — 模型文件存储

> 所有模型文件已被 `.gitignore` 排除，不纳入版本管理。
> 首次部署需按 `models/README.md` 中的说明下载模型。
> 详见 `models/README.md`

## models/README.md
- **用途**：模型清单、下载方式、微调说明
- **状态**：✅ 已完成

## models/embedding/
- **目录**：`models/embedding/bge-large-zh-v1.5/`
- **用途**：BGE-large-zh-v1.5 Embedding 模型，文本向量化（dim=1024）
- **大小**：~1.3 GB
- **下一步**：按 README 下载 → `rag/embedding.py` 自动从本地加载

## models/reranker/
- **目录**：`models/reranker/bge-reranker-v2-m3/`
- **用途**：BGE Reranker v2-m3 模型，检索结果精排
- **大小**：~2.3 GB
- **下一步**：按 README 下载 → `rag/reranker.py` 自动从本地加载

## models/intent/
- **目录**：`models/intent/bert-intent/`
- **用途**：基于 `bert-base-chinese` 在政务语料上 fine-tune 的意图分类模型
- **大小**：~400 MB
- **下一步**：训练后存放 → `agents/intent/classifier.py` 自动从本地加载

## models/fine_tuned/
- **目录**：`models/fine_tuned/intent-v1/` `models/fine_tuned/ner/`
- **用途**：项目自行微调的模型产出，支持版本化（v1/v2）、A/B 测试和回滚
- **下一步**：Phase 2 训练脚本产出后存放于此

---

# 13. requirements/ — 依赖管理

## requirements/requirements.txt
- **用途**：核心依赖（FastAPI, LangChain, LangGraph, MCP, OpenAI, Milvus, PostgreSQL, Redis, OpenTelemetry...）
- **下一步**：✅ 已完成，后续新增依赖时更新

## requirements/requirements-dev.txt
- **用途**：开发工具依赖（pytest, ruff, black, mypy）
- **下一步**：✅ 已完成

## requirements/requirements-gpu.txt
- **用途**：GPU推理依赖（vLLM, CUDA相关）
- **下一步**：✅ 已完成

## requirements/requirements-ocr.txt
- **用途**：OCR能力依赖（PaddleOCR, Tesseract等）
- **下一步**：✅ 已完成

---

# 14. docs/ — 设计文档

| 文件 | 内容 | 状态 |
|------|------|------|
| ARCHITECTURE.md | 六层架构、数据流、安全架构 | ✅ 完成 |
| AGENT_DESIGN.md | 6类Agent角色、协作流程、State设计 | ✅ 完成 |
| MCP_DESIGN.md | MCP协议、3个Server、Tool Schema、Gateway | ✅ 完成 |
| A2A_DESIGN.md | Agent Card、Task生命周期、异步Callback、Mock Agent | ✅ 完成 |
| EVALUATION.md | RAG/Agent/安全评测指标、Benchmark、自动评测流水线 | ✅ 完成 |
| DEPLOYMENT.md | Docker、K8s、GPU规划、高可用、国产化适配 | ✅ 完成 |
| PROJECT_ROADMAP.md | V1.0→V4.0四阶段演进路线 | ✅ 完成 |

---

# 15. 开发优先级总结

```
第一优先级（让系统跑起来）:
  1. orchestration/langgraph/state.py      — AgentState定义
  2. orchestration/langgraph/graph.py      — StateGraph构建
  3. orchestration/langgraph/nodes.py      — 节点函数
  4. orchestration/langgraph/edges.py      — 条件路由
  5. agents/supervisor/planner.py          — 任务拆解
  6. agents/supervisor/router.py           — Agent路由
  7. agents/supervisor/agent.py            — Supervisor主逻辑
  8. backend/config.py                     — 配置管理
  9. backend/main.py                       — FastAPI入口
  10. backend/api/routes.py                — API端点

第二优先级（让Agent有知识）:
  11. rag/embedding.py                     — BGE向量化
  12. rag/retriever.py                     — 混合检索
  13. rag/reranker.py                      — 重排序
  14. rag/generator.py                     — LLM生成
  15. agents/policy/agent.py               — Policy Agent
  16. agents/intent/classifier.py          — BERT分类
  17. agents/intent/agent.py               — Intent Agent

第三优先级（让Agent能调工具）:
  18. tools/mcp/client.py                  — MCP Client
  19. tools/mcp/gateway.py                 — MCP Gateway
  20. tools/mcp/servers/policy_server/     — Policy MCP Server

第四优先级（让系统可治理）:
  21. governance/trace.py                  — 全链路追踪
  22. governance/guardrail.py              — 安全护栏
  23. governance/pii.py                    — PII脱敏
  24. governance/evaluation/metrics.py     — 评测指标
  25. governance/evaluation/evaluator.py   — 评测引擎

第五优先级（跨域协同）:
  26. tools/a2a/protocol.py                — A2A协议
  27. tools/a2a/task.py                    — 任务管理
  28. tools/a2a/connector.py               — A2A连接器
  29. tools/a2a/callback.py                — 回调处理

第六优先级（生产化）:
  30. deploy/Dockerfile                    — Docker镜像
  31. deploy/docker-compose.yml            — 本地部署
  32. governance/dashboard.py              — 运维看板
  33. governance/monitor.py                — Prometheus监控
```
