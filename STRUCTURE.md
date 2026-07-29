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
- **下一步**：实现 `AgentRegistry` 类：
  - `register(name, agent_instance)` — 注册Agent
  - `get(name) -> Agent` — 获取Agent
  - `list() -> List[str]` — 列出所有可用Agent
  - `health_check(name) -> bool` — 健康检查

---

## agents/supervisor/ — Supervisor Agent（编排者）

### agents/supervisor/__init__.py
- **用途**：Supervisor包初始化
- **下一步**：导出 `SupervisorAgent` 类

### agents/supervisor/agent.py
- **用途**：Supervisor核心逻辑 —— 接收用户请求 → 规划 → 路由 → 汇总结果
- **下一步**：实现 `SupervisorAgent` 类：
  - `plan(user_query: str, state: AgentState) -> List[Task]` — 调用planner拆解任务
  - `route(task: Task) -> str` — 调用router选择Agent
  - `execute(state: AgentState) -> AgentState` — 主执行循环
  - `handle_error(error, state) -> AgentState` — 异常处理和恢复

### agents/supervisor/planner.py
- **用途**：任务规划器 —— LLM-based将用户自然语言需求拆解为子任务序列
- **下一步**：实现 `Planner` 类：
  - `decompose(user_query: str, intent: str) -> List[Task]` — LLM拆解任务
  - Task结构：`{id, type, agent, input, dependencies, priority}`
  - 例如："开餐馆" → `[{search_policy}, {check_material}, {create_case}]`

### agents/supervisor/router.py
- **用途**：Agent路由器 —— 根据任务类型和意图选择合适的Agent
- **下一步**：实现 `Router` 类：
  - `route(task: Task) -> str` — 返回agent_name
  - 路由表：`{"policy_query": "policy_agent", "material_check": "material_agent", ...}`
  - 支持LLM动态路由fallback

### agents/supervisor/prompts.py
- **用途**：Supervisor Agent的Prompt模板（版本化管理）
- **下一步**：定义 `SUPERVISOR_SYSTEM_PROMPT`、`PLANNER_PROMPT`、`ROUTER_PROMPT`：
  - Role: "你是一个政务办事系统的任务协调者"
  - Constraints: "只做任务规划，不直接回答业务问题"
  - Output Schema: 定义JSON格式输出

---

## agents/intent/ — Intent Agent（意图识别）

### agents/intent/__init__.py
- **用途**：Intent包初始化
- **下一步**：导出 `IntentAgent` 类

### agents/intent/agent.py
- **用途**：Intent Agent核心 —— 优先BERT分类，置信度低时fallback到LLM
- **下一步**：实现 `IntentAgent` 类：
  - `classify(user_query: str) -> IntentResult` — BERT优先，LLM兜底
  - `get_intent_label(intent_id: str) -> str` — 标签映射

### agents/intent/classifier.py
- **用途**：BERT意图分类器 —— Fine-tuned BERT模型做多分类
- **下一步**：实现 `IntentClassifier` 类：
  - `load_model(model_path)` — 加载fine-tuned BERT
  - `predict(text: str) -> (label, confidence)` — 推理
  - 分类标签：business_register, fund_query, property_service, restaurant_license...
  - 训练数据准备逻辑

### agents/intent/schema.py
- **用途**：Intent Agent的数据模型（Pydantic v2）
- **下一步**：定义 Pydantic 模型：
  - `IntentLabel` — {label_id, label_name, category}
  - `IntentResult` — {label, confidence, source(bert|llm)}
  - `IntentClassification` — {user_query, results: List[IntentResult]}

### agents/intent/prompts.py
- **用途**：Intent Agent的Prompt模板
- **下一步**：定义 `INTENT_CLASSIFICATION_PROMPT`：
  - 包含few-shot示例（"开餐馆" → business_license）
  - 约束：只从预定义标签中选择

---

## agents/policy/ — Policy Agent（政策检索）

### agents/policy/__init__.py
- **用途**：Policy包初始化
- **下一步**：导出 `PolicyAgent` 类

### agents/policy/agent.py
- **用途**：Policy Agent核心 —— RAG管线编排（embedding → retrieve → rerank → generate）
- **下一步**：实现 `PolicyAgent` 类：
  - `search(query: str, top_k: int) -> PolicyResult` — 完整RAG流程
  - `format_answer(retrieved_docs, query) -> str` — LLM生成答案
  - 必须返回 evidence[] 标注信息来源

### agents/policy/schema.py
- **用途**：Policy Agent的数据模型
- **下一步**：定义 Pydantic 模型：
  - `PolicyDocument` — {title, content, source, page, score}
  - `PolicyEvidence` — {document, relevant_excerpt, relevance_score}
  - `PolicyResult` — {answer: str, evidence: List[PolicyEvidence]}

### agents/policy/prompts.py
- **用途**：Policy Agent的Prompt模板
- **下一步**：定义 `POLICY_RAG_PROMPT`：
  - "你是一个政务政策问答助手。基于提供的政策条文回答问题，必须标注每条回答的来源。"
  - 输出格式：JSON with answer + evidence

---

## agents/material/ — Material Agent（材料审核）

### agents/material/__init__.py
- **用途**：Material包初始化
- **下一步**：导出 `MaterialAgent` 类

### agents/material/agent.py
- **用途**：Material Agent核心 —— OCR识别 → 实体抽取 → 规则校验 → 生成审核结果
- **下一步**：实现 `MaterialAgent` 类：
  - `review(file_path: str, business_type: str) -> MaterialResult` — 完整审核流程
  - `check_completeness(extracted, required) -> CheckResult` — 完整性检查

### agents/material/ocr.py
- **用途**：OCR识别 —— 从文档图片/PDF中提取文字
- **下一步**：实现 `OCREngine` 类：
  - `extract_text(file_path: str) -> str` — 文件→文字
  - 支持格式：jpg/png/pdf
  - 考虑集成 PaddleOCR 或 Tesseract

### agents/material/extractor.py
- **用途**：实体抽取 —— 从OCR文本中提取关键字段
- **下一步**：实现 `EntityExtractor` 类：
  - `extract(text: str, schema: Dict) -> Dict` — 提取结构化字段
  - 字段：name, id_card, business_name, address, phone...
  - 使用LLM + few-shot做信息抽取

### agents/material/validator.py
- **用途**：规则校验 —— 检查提交材料是否满足业务要求
- **下一步**：实现 `MaterialValidator` 类：
  - `validate(extracted: Dict, rules: List[Rule]) -> ValidationResult` — 逐条校验
  - Rule结构：{field, requirement, condition}
  - 输出：{passed: bool, missing: List[str], warnings: List[str]}

### agents/material/prompts.py
- **用途**：Material Agent的Prompt模板
- **下一步**：定义 `MATERIAL_EXTRACTION_PROMPT`、`MATERIAL_VALIDATION_PROMPT`

---

## agents/workflow/ — Workflow Agent（流程执行）

### agents/workflow/__init__.py
- **用途**：Workflow包初始化
- **下一步**：导出 `WorkflowAgent` 类

### agents/workflow/agent.py
- **用途**：Workflow Agent核心 —— 通过MCP Client调用业务系统创建办件、查询状态
- **下一步**：实现 `WorkflowAgent` 类：
  - `create_case(user_id, service_type, materials) -> CaseResult` — 通过MCP调用create_case
  - `query_status(case_id) -> CaseStatus` — 通过MCP调用query_status
  - 所有外部调用必须经过 `mcp_client.call_tool()`，禁止直接import业务代码

### agents/workflow/prompts.py
- **用途**：Workflow Agent的Prompt模板
- **下一步**：定义 `WORKFLOW_EXECUTION_PROMPT`

---

## agents/governance/ — Governance Agent（安全治理，旁路）

### agents/governance/__init__.py
- **用途**：Governance包初始化
- **下一步**：导出 `GovernanceAgent` 类

### agents/governance/agent.py
- **用途**：Governance Agent核心 —— 协调安全检查、行为监控、优化建议
- **下一步**：实现 `GovernanceAgent` 类：
  - `check(state: AgentState) -> RiskAssessment` — 安全风险评估
  - `monitor(trace: Trace) -> BehaviorReport` — 行为监控
  - **注意：此Agent不能参与业务回答，仅做旁路控制**

### agents/governance/security.py
- **用途**：安全检测 —— PII检测、Prompt Injection检测、敏感词过滤
- **下一步**：实现 `SecurityChecker` 类：
  - `check_input(text: str) -> SecurityResult` — 输入安全扫描
  - `check_output(text: str) -> SecurityResult` — 输出安全扫描
  - 使用正则 + 关键词库 + LLM judge

### agents/governance/behavior.py
- **用途**：行为分析 —— 循环检测、异常行为识别
- **下一步**：实现 `BehaviorAnalyzer` 类：
  - `detect_loop(tool_calls: List) -> bool` — 窗口6次，连续3次相同工具触发
  - `detect_anomaly(trace: Trace) -> AnomalyReport` — 异常检测

### agents/governance/optimizer.py
- **用途**：自动优化 —— 分析trace和evaluation结果，生成优化建议
- **下一步**：实现 `Optimizer` 类：
  - `analyze(trace: Trace, eval_result: EvaluationResult) -> OptimizationSuggestion`
  - `suggest_prompt_improvement(failure_cases) -> str`
  - `suggest_workflow_improvement(inefficient_paths) -> str`

### agents/governance/prompts.py
- **用途**：Governance Agent的Prompt模板
- **下一步**：定义安全检查和行为分析的Prompt模板

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
- **用途**：定义所有Agent节点共享的AgentState（TypedDict）
- **下一步**：实现 `AgentState(TypedDict)`:
  ```python
  class AgentState(TypedDict):
      trace_id: str          # 全链路追踪ID
      user_query: str        # 用户原始输入
      intent: str            # 识别出的意图标签
      task_plan: list        # 拆解后的子任务列表
      current_agent: str     # 当前执行的Agent名称
      messages: list         # 对话消息历史
      tool_calls: list       # MCP工具调用历史
      mcp_history: list      # MCP调用详细记录
      a2a_tasks: list        # A2A跨域任务列表
      evidence: list         # 政策证据引用
      final_answer: str      # 最终回答
      risk_level: str        # 风险等级 (low/medium/high)
  ```

### orchestration/langgraph/graph.py
- **用途**：构建完整的LangGraph StateGraph
- **下一步**：实现 `build_graph() -> StateGraph`:
  - 添加节点：supervisor → intent → policy/material(并行) → workflow → governance
  - 添加条件边：router决定下一个Agent
  - 注入Checkpointer用于状态持久化
  - 编译并返回 compiled graph

### orchestration/langgraph/nodes.py
- **用途**：LangGraph节点函数 —— 每个节点包装一个Agent调用
- **下一步**：实现各节点函数：
  - `supervisor_node(state: AgentState) -> AgentState` — 调用Supervisor Agent
  - `intent_node(state: AgentState) -> AgentState` — 调用Intent Agent
  - `policy_node(state: AgentState) -> AgentState` — 调用Policy Agent
  - `material_node(state: AgentState) -> AgentState` — 调用Material Agent
  - `workflow_node(state: AgentState) -> AgentState` — 调用Workflow Agent
  - `governance_node(state: AgentState) -> AgentState` — 调用Governance Agent

### orchestration/langgraph/edges.py
- **用途**：条件路由函数 —— 根据state决定下一个节点
- **下一步**：实现条件路由：
  - `route_after_supervisor(state) -> str` — 根据task_plan返回下一个Agent节点名
  - `route_after_intent(state) -> str` — 返回"supervisor"做二次规划
  - `route_after_policy_or_material(state) -> str` — 判断是否需要继续

### orchestration/langgraph/checkpointer.py
- **用途**：PostgreSQL Checkpointer —— LangGraph状态持久化
- **下一步**：实现 `PostgresCheckpointer`:
  - `save(state: AgentState, checkpoint_id: str)` — 保存状态快照
  - `load(checkpoint_id: str) -> AgentState` — 恢复状态
  - 使用 `langgraph-checkpoint-postgres` 库
  - 支持A2A异步任务挂起/恢复

### orchestration/langgraph/runtime.py
- **用途**：Agent Runtime安全控制 —— 步骤限制、循环检测、超时控制
- **下一步**：实现 `AgentRuntime` 类：
  - `max_steps = 10` — 超过则优雅终止
  - `loop_window = 6` — 滑动窗口大小
  - `loop_threshold = 3` — 连续3次相同tool触发re-plan
  - `timeout = 30` — Agent执行超时
  - `execute(graph, state) -> AgentState` — 带安全控制的执行器

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
- **用途**：文本向量化 —— 使用BGE模型生成embedding
- **下一步**：实现 `EmbeddingEngine` 类：
  - `load_model(model_name)` — 加载BGE模型（默认 BAAI/bge-large-zh-v1.5）
  - `encode_query(text: str) -> ndarray` — 查询向量化
  - `encode_documents(texts: List[str]) -> ndarray` — 批量文档向量化
  - 支持GPU加速

### rag/retriever.py
- **用途**：混合检索 —— Milvus密集检索 + BM25稀疏检索 + 融合排序
- **下一步**：实现 `HybridRetriever` 类：
  - `dense_search(query_embedding, top_k) -> List[Document]` — Milvus向量检索
  - `sparse_search(query, top_k) -> List[Document]` — BM25关键词检索
  - `hybrid_search(query, query_embedding, top_k) -> List[Document]` — 融合两种结果
  - 使用 RRF (Reciprocal Rank Fusion) 融合排序

### rag/reranker.py
- **用途**：重排序 —— 使用BGE Reranker对检索结果精排
- **下一步**：实现 `Reranker` 类：
  - `load_model(model_name)` — 加载BGE Reranker（默认 BAAI/bge-reranker-v2-m3）
  - `rerank(query, documents, top_k) -> List[Document]` — 重排序
  - 返回带 relevance_score 的文档列表

### rag/generator.py
- **用途**：LLM答案生成 —— 基于检索到的文档生成带evidence的答案
- **下一步**：实现 `Generator` 类：
  - `generate(query, context_docs, chat_history) -> GeneratedAnswer` — LLM生成
  - 输出格式：{answer, evidence: [{source, excerpt, score}]}
  - 使用LangChain的ChatOpenAI兼容接口

### rag/knowledge_base.py
- **用途**：知识库管理 —— 文档加载、切分、索引
- **下一步**：实现 `KnowledgeBase` 类：
  - `load_documents(path) -> List[Document]` — 加载政策文件（PDF/DOCX/TXT）
  - `split_documents(docs, chunk_size, overlap)` — 文本切分
  - `index_documents(docs)` — 写入Milvus
  - `rebuild_index()` — 重建索引

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
- **下一步**：实现：
  - `create_engine(url) -> AsyncEngine` — 创建异步引擎
  - `get_session() -> AsyncSession` — 获取会话（FastAPI依赖注入用）
  - `init_db()` — 初始化数据库表

### database/models.py
- **用途**：SQLAlchemy ORM模型
- **下一步**：定义5个核心表：
  - **Trace表**：trace_id, span_id, agent_name, tool_name, input, output, latency_ms, token_usage, status, created_at
  - **Agent表**：agent_id, name, type, version, config, status, created_at
  - **Prompt表**：prompt_id, agent_name, version, content, is_active, created_at
  - **Evaluation表**：eval_id, version, task_success_rate, rag_faithfulness, tool_accuracy, report_json, created_at
  - **Checkpoint表**：checkpoint_id, task_id, state_json, created_at

### database/schemas.py
- **用途**：Pydantic v2序列化模型（与ORM模型对应）
- **下一步**：定义与models.py对应的Pydantic模型，用于API序列化

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
- **下一步**：实现 `create_app() -> FastAPI`:
  - CORS配置
  - 注册中间件（auth → rbac → logging → tracing）
  - 挂载路由（/api/chat, /api/agent, /api/evaluation, /api/a2a/callback）
  - 启动/关闭事件（数据库连接池初始化/释放）

### backend/config.py
- **用途**：应用配置管理 —— 基于pydantic-settings读.env
- **下一步**：实现 `Settings` 类：
  - 数据库URL、Redis URL、Milvus URL
  - LLM API URL/Key/Model
  - JWT Secret/Algorithm
  - Agent Runtime参数（max_steps, timeout）
  - OpenTelemetry端点
  - 每个字段从环境变量读取，有默认值

---

## backend/api/

### backend/api/__init__.py
- **用途**：API包初始化
- **下一步**：导出所有router

### backend/api/routes.py
- **用途**：API端点定义
- **下一步**：实现以下端点：
  - `POST /api/chat` — 用户对话（调用LangGraph Agent流程）
  - `GET /api/agent/status/{trace_id}` — 查询Agent执行状态
  - `POST /api/a2a/callback` — A2A外部Agent回调
  - `GET /api/evaluation/report/{version}` — 获取评测报告
  - `GET /api/dashboard/overview` — 运维看板概览

### backend/api/dependencies.py
- **用途**：FastAPI依赖注入 —— DB session, current user, agent runtime
- **下一步**：实现：
  - `get_db() -> AsyncSession` — 数据库会话
  - `get_current_user(token) -> User` — JWT用户解析
  - `get_agent_runtime() -> AgentRuntime` — Agent运行时实例

### backend/api/schemas.py
- **用途**：API请求/响应的Pydantic模型
- **下一步**：定义：
  - `ChatRequest` — {user_query: str, user_id: str}
  - `ChatResponse` — {trace_id: str, answer: str, evidence: List}
  - `AgentStatusResponse` — {trace_id, status, current_agent, steps}
  - `A2ACallbackRequest` — {task_id, status, artifact}
  - `EvaluationReportResponse` — {version, metrics, created_at}

---

## backend/middleware/

### backend/middleware/__init__.py
- **用途**：中间件包初始化
- **下一步**：导出所有中间件

### backend/middleware/auth.py
- **用途**：JWT认证中间件
- **下一步**：实现：
  - 从Authorization header提取Bearer token
  - 使用python-jose验证JWT
  - 将user_id注入request.state

### backend/middleware/rbac.py
- **用途**：RBAC权限中间件
- **下一步**：实现：
  - 定义角色：admin, agent, user
  - 定义权限映射：哪些角色可以调用哪些API/MCP工具
  - 在请求处理前检查权限

### backend/middleware/logging.py
- **用途**：请求日志中间件
- **下一步**：实现：
  - 为每个请求生成/提取trace_id
  - 使用loguru记录请求信息（method, path, user_id, trace_id, latency）
  - 将trace_id注入到响应头

### backend/middleware/tracing.py
- **用途**：OpenTelemetry链路追踪中间件
- **下一步**：实现：
  - 为每个HTTP请求创建OpenTelemetry span
  - 将trace context传播到下游Agent调用
  - 使用OTLP exporter导出到collector

---

## backend/services/

### backend/services/__init__.py
- **用途**：服务层包初始化
- **下一步**：导出 `AgentService`

### backend/services/agent_service.py
- **用途**：Agent编排服务 —— 管理Agent生命周期
- **下一步**：实现 `AgentService` 类：
  - `execute(user_query, user_id) -> AgentState` — 执行Agent工作流
  - `resume(checkpoint_id, callback_result) -> AgentState` — 恢复A2A挂起的流程
  - `get_status(trace_id) -> ExecutionStatus` — 查询执行状态

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

# 12. requirements/ — 依赖管理

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

# 13. docs/ — 设计文档

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

# 14. 开发优先级总结

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
