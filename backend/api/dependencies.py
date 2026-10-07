"""
backend.api.dependencies - FastAPI dependencies: DB session, current user, agent runtime injection

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement FastAPI dependency injection for common resources
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from langgraph.graph.state import CompiledStateGraph

from backend.config import Settings, get_settings
from orchestration.langgraph.state import AgentState
from orchestration.langgraph.identity import checkpoint_thread_id
from tools.logger import get_logger


def check_input_safety(user_query: str, trace_id: str, prior_messages: list[dict] | None = None):
    """Fail closed if either input validation or PII masking is unavailable."""
    from tools.logger import get_logger

    try:
        from governance.guardrail import GuardrailRunner
        from governance.pii import detect_pii

        result = GuardrailRunner().run_input(user_query)
        pii = detect_pii(user_query)
        pii_types = [match.pii_type.value for match in pii.matches]
        safe_messages = []
        for message in prior_messages or []:
            masked = detect_pii(message.get("content", ""))
            pii_types.extend(match.pii_type.value for match in masked.matches)
            safe_messages.append({**message, "content": masked.masked_text})
        return result, sorted(set(pii_types)), pii.masked_text, safe_messages
    except Exception as error:
        # Exception messages may themselves contain the original sensitive input.
        get_logger(__name__).error(
            "Input safety check unavailable; request rejected (trace={}, type={})",
            trace_id, type(error).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="安全检查暂时不可用，请稍后重试。",
        ) from None


# ============================================================
# User ID — 从Header提取
# ============================================================


async def get_user_id(
    request: Request,
) -> str:
    """
    获取当前认证用户ID。

    依赖 AuthMiddleware 已通过 JWT Bearer Token 验证身份并将
    user_id 注入到 request.state。未认证时返回 401。

    Args:
        request: FastAPI Request对象

    Returns:
        用户ID

    Raises:
        HTTPException: 未认证时返回401
    """
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供认证凭证 (Authorization: Bearer <token>)",
        )
    return user_id


# ============================================================
# 当前用户身份 — 从 JWT 注入的 request.state 提取
# ============================================================


async def get_current_identity(request: Request) -> dict[str, str]:
    """
    获取当前认证用户完整身份（user_id / role / tenant_id）。

    身份只来自 AuthMiddleware 校验后的 JWT，不信任请求体或 Header。

    Returns:
        {"user_id": str, "role": str, "tenant_id": str}

    Raises:
        HTTPException: 未认证时返回401
    """
    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "user_tenant", "default")
    if (not isinstance(user_id, str) or not user_id.strip()
            or not isinstance(tenant_id, str) or not tenant_id.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供认证凭证 (Authorization: Bearer <token>)",
        )
    return {
        "user_id": user_id,
        "role": getattr(request.state, "user_role", "user"),
        "tenant_id": tenant_id,
    }


# ============================================================
# Trace ID — 生成或提取
# ============================================================


async def get_trace_id(
    request: Request,
    x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
) -> str:
    """
    获取或生成trace_id。

    优先级：Header X-Trace-Id > 自动生成

    Args:
        request: FastAPI Request对象
        x_trace_id: 客户端传入的trace_id

    Returns:
        trace_id字符串
    """
    if x_trace_id:
        return x_trace_id
    # 自动生成
    return f"trace_{uuid.uuid4().hex[:16]}"


# ============================================================
# Settings — 单例注入
# ============================================================


async def get_config() -> Settings:
    """
    获取应用配置单例。

    Returns:
        Settings实例
    """
    return get_settings()


# ============================================================
# A2A Connector — 单例注入
# ============================================================

_a2a_connector = None


async def get_a2a_connector():
    """
    获取或惰性创建 A2A Connector 单例。

    首次调用时初始化 A2A 基础设施（注册中心 + 默认 Agent 注册）。

    Returns:
        A2AConnector 实例
    """
    global _a2a_connector

    if _a2a_connector is not None:
        return _a2a_connector

    try:
        from backend.config import get_settings
        from tools.a2a.connector import A2AConnector
        from tools.a2a.registry import initialize_default_agents
        from tools.a2a.task import get_task_store

        settings = get_settings()

        # 初始化默认外部 Agent 注册（端点从 A2A_HOUSING_URL / A2A_FUND_URL 读取）
        initialize_default_agents()

        # 任务存储持久化恢复（重启后回调仍能定位原任务）
        store = get_task_store()
        if hasattr(store, "hydrate"):
            try:
                await store.hydrate()
            except Exception as e:
                # DB 不可用时降级为内存存储，但必须留痕：静默会导致重启后
                # A2A 回调定位不到原任务，表现为"回调来了却查无此任务"
                get_logger(__name__).warning(
                    "A2A 任务存储恢复失败，降级为内存存储（重启后回调可能丢失）: {}", e
                )

        _a2a_connector = A2AConnector(
            task_store=store,
            default_callback_url=settings.a2a_callback_url,
            allow_stub=settings.a2a_allow_stub,
            http_retries=settings.a2a_http_retries,
        )
        return _a2a_connector
    except ImportError:
        return None


# ============================================================
# Agent Graph — 单例注入（惰性初始化）
# ============================================================

_agent_graph: Optional[CompiledStateGraph] = None

# MCP Client 单例句柄：单独持有以便 lifespan shutdown 释放其 httpx 连接池
_mcp_client = None


async def _is_db_available() -> bool:
    """
    检测 PostgreSQL 是否可用（通过轻量 SELECT 1）。

    用于决定是否启用 Checkpointer 等依赖数据库的组件，
    避免无 DB 环境下 Agent 执行失败。

    Returns:
        True 表示数据库可连接
    """
    try:
        import asyncio

        from sqlalchemy import text

        from database.connection import get_engine

        async def _probe() -> None:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))

        # 2 秒超时，避免 DB 不可达时阻塞请求几十秒
        await asyncio.wait_for(_probe(), timeout=2.0)
        return True
    except Exception:
        return False


async def get_agent_graph(
    settings: Settings = Depends(get_config),
) -> CompiledStateGraph:
    """
    获取或惰性创建Agent Graph（单例）。

    首次调用时构建Graph，后续复用同一个实例。
    构建时使用LLM如果配置中提供了API Key。

    Args:
        settings: 应用配置

    Returns:
        编译好的LangGraph StateGraph
    """
    global _agent_graph, _mcp_client

    if _agent_graph is not None:
        return _agent_graph

    # 惰性构建
    from orchestration.langgraph.graph import build_graph

    # 如果有LLM配置，构建带LLM的Graph（CachingChatOpenAI 带响应缓存：相同问题复用结果）
    llm = None
    if settings.llm_api_key:
        try:
            from governance.callbacks import TokenUsageCallback
            from governance.llm_cache import CachingChatOpenAI
            llm = CachingChatOpenAI(
                base_url=settings.llm_api_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
                callbacks=[TokenUsageCallback()],
            )
        except ImportError:
            pass  # 没有langchain_openai时使用stub模式

    # 获取 A2A Connector
    a2a_conn = await get_a2a_connector()

    # 尝试获取 Checkpointer（仅 DB 可用时启用，避免无 DB 环境执行失败）
    checkpointer = None
    if await _is_db_available():
        try:
            from orchestration.langgraph.checkpointer import PostgresCheckpointer
            checkpointer = PostgresCheckpointer()
        except Exception as e:
            # 缺失 checkpointer 会让长流程与 A2A 挂起任务无法断点恢复，
            # 且表现为"重启后任务凭空消失"，必须留痕而非静默
            get_logger(__name__).warning(
                "PostgresCheckpointer 初始化失败，长流程/A2A 挂起恢复将不可用: {}", e
            )

    # MCP Client（激活整条 MCP 工具调用链路；带 admin JWT 通过 Gateway 认证/RBAC）
    #
    # 降级策略与 A2A 侧对齐：MCP_ALLOW_STUB=False（默认）时初始化失败不再静默
    # 降级为 stub，而是记录 ERROR 并向上抛出。原先 except: pass 会让整条工具
    # 调用链路悄悄退回本地模拟结果，且日志中不留痕迹。
    global _mcp_client
    mcp_client = None
    try:
        from backend.middleware.auth import create_access_token
        from tools.mcp.client import MCPClient

        mcp_token = create_access_token(user_id="mcp_client", role="admin")
        mcp_client = MCPClient(
            gateway_url=settings.mcp_gateway_url,
            auth_token=mcp_token,
        )
        _mcp_client = mcp_client
        get_logger(__name__).info("MCP Client 已初始化: {}", settings.mcp_gateway_url)
    except Exception as e:
        if settings.mcp_allow_stub:
            get_logger(__name__).warning(
                "MCP Client 初始化失败，以 stub 模式继续（MCP_ALLOW_STUB=True）: {}", e
            )
        else:
            get_logger(__name__).error(
                "MCP Client 初始化失败，拒绝静默降级为 stub。"
                "本地单机无 Gateway 时请设 MCP_ALLOW_STUB=True: {}", e
            )
            raise

    _agent_graph = build_graph(
        llm=llm,
        mcp_client=mcp_client,
        a2a_connector=a2a_conn,
        checkpointer=checkpointer,
    )
    return _agent_graph


async def close_dependencies() -> None:
    """
    释放 Agent 运行时持有的外部连接池（MCP Client / A2A Connector）。

    由 backend.main 的 lifespan shutdown 调用。此前这两个实例的 httpx 连接池
    从未被释放（A2AConnector.close 只有示例代码调用过，MCPClient 甚至没有
    close 方法），长期运行或热重载会累积半开连接与 ResourceWarning。

    幂等：可重复调用；已释放的实例会被置回 None，下次请求重新惰性创建。
    """
    global _mcp_client, _a2a_connector, _agent_graph

    logger = get_logger(__name__)

    if _mcp_client is not None:
        try:
            await _mcp_client.close()
        except Exception as e:
            logger.warning("关闭 MCP Client 时出错: {}", e)
        finally:
            _mcp_client = None

    if _a2a_connector is not None:
        try:
            await _a2a_connector.close()
        except Exception as e:
            logger.warning("关闭 A2A Connector 时出错: {}", e)
        finally:
            _a2a_connector = None

    # 图实例持有上述客户端引用，一并释放以便下次完整重建
    _agent_graph = None


# ============================================================
# Executor — Agent执行器（封装 graph.ainvoke）
# ============================================================


async def execute_agent(
    user_query: str,
    user_id: str,
    trace_id: str,
    settings: Settings,
    conversation_id: Optional[str] = None,
    prior_messages: Optional[list[dict]] = None,
    tenant_id: str = "default",
    user_role: str = "user",
) -> AgentState:
    """
    执行一次完整的Agent工作流。

    创建初始State → AgentRuntime 安全护栏 → graph.ainvoke → 返回最终State。

    AgentRuntime 提供:
    - 步骤限制（max_steps=10，超限优雅终止）
    - 循环检测（滑动窗口6，连续3次同tool触发re-plan）
    - 超时控制（单Agent 30s）
    - 错误累积（5次累计错误→终止）

    Args:
        user_query: 用户输入
        user_id: 用户ID
        trace_id: 链路追踪ID
        settings: 应用配置
        conversation_id: 会话ID（多轮对话用，作为 LangGraph thread_id 保持上下文）
        prior_messages: 历史对话消息（[{role, content}]），注入 messages 供 LLM 参考
        tenant_id: 认证用户租户ID
        user_role: 认证用户角色

    Returns:
        执行后的AgentState字典
    """
    from orchestration.langgraph.state import create_initial_state
    from orchestration.langgraph.runtime import (
        create_runtime_from_settings,
        RuntimeExceededError,
        RuntimeTimeoutError,
        RuntimeLoopDetectedError,
    )

    input_check, entry_pii, safe_query, prior_messages = check_input_safety(
        user_query, trace_id, prior_messages,
    )

    # 多轮历史 → 文本上下文（供规划/汇总 LLM 参考）
    conversation_history = ""
    if prior_messages:
        try:
            from backend.services.conversation_service import format_history_text
            conversation_history = format_history_text(prior_messages)
        except Exception:
            conversation_history = ""

    # ── 输入护栏：在 LLM 调用前检查用户输入（P1-8：脱敏后进入 LLM） ──

    # 创建初始State（携带脱敏后的 user_query 与多轮消息/历史文本）
    initial_state = create_initial_state(
        user_query=safe_query,
        trace_id=trace_id,
        messages=prior_messages or [],
        conversation_history=conversation_history,
        user_id=user_id,
        tenant_id=tenant_id,
        user_role=user_role,
    )
    if entry_pii:
        # 入口已检测并脱敏的 PII 类型，供 governance_node 合并进 safety_check 审计
        initial_state["safety_check"] = {"pii_detected": entry_pii}

    # 获取Graph
    graph = await get_agent_graph(settings)

    # 运行时安全护栏（多轮时 thread_id 用 conversation_id，保持 LangGraph 会话上下文）
    config = {
        "configurable": {
            "thread_id": checkpoint_thread_id(tenant_id, user_id, conversation_id or trace_id),
            "user_id": user_id,
            "tenant_id": tenant_id,
        },
    }

    initial_state["checkpoint_thread_id"] = config["configurable"]["thread_id"]
    try:
        if input_check is not None and input_check.blocked:
            from tools.logger import get_logger as _get_logger
            _logger = _get_logger(__name__)
            _logger.warning(
                "护栏阻断输入 (trace={}, reason={})",
                trace_id, input_check.block_reason,
            )
            return {
                **initial_state,
                "final_answer": (
                    "抱歉，您的输入包含不安全内容，系统已自动拦截。"
                    "请修改后重试，或联系人工客服获取帮助。"
                ),
                "risk_level": "high",
                "safety_check": input_check.to_dict(),
            }

        # 将认证用户身份 + 请求级 trace_id 注入 trace 上下文，
        # 保证 span 归属、数据隔离，且 span 与请求 trace_id 对齐（P2-1 落库关联）
        from governance.trace import (
            end_trace,
            flush_trace_to_db,
            reset_trace_user,
            set_trace_user,
            start_trace_with_id,
        )

        trace_tokens = set_trace_user(user_id, tenant_id)
        start_trace_with_id(trace_id, user_query=initial_state.get("user_query", ""))
        try:
            runtime = create_runtime_from_settings(settings)
            result = await runtime.execute_with_safeguards(
                graph, initial_state, graph_config=config,
            )
        finally:
            end_trace()
            reset_trace_user(trace_tokens)
            # P2-1：请求结束后批量落库；DB 不可用时 span 保留内存供状态查询降级
            try:
                await flush_trace_to_db(trace_id)
            except Exception as e:
                # trace 落库失败 = 审计数据丢失，与 AgentOps 可观测目标直接冲突
                get_logger(__name__).warning(
                    "trace 落库失败（trace_id={}），审计数据可能丢失: {}", trace_id, e
                )
        return result
    except RuntimeExceededError as e:
        from tools.logger import get_logger as _get_logger
        _logger = _get_logger(__name__)
        _logger.warning("Agent 步骤/错误超限 (trace={}): {}", trace_id, e)
        # 优雅降级：返回当前 state + 友好提示
        return {
            **initial_state,
            "final_answer": "抱歉，当前请求处理步骤较多，部分结果未能完成。请简化您的问题后重试，或联系人工客服获取帮助。",
            "risk_level": "high",
            "error": str(e),
        }
    except RuntimeTimeoutError as e:
        from tools.logger import get_logger as _get_logger
        _logger = _get_logger(__name__)
        _logger.warning("Agent 执行超时 (trace={}): {}", trace_id, e)
        return {
            **initial_state,
            "final_answer": "抱歉，请求处理超时，请稍后重试。如果是复杂业务，建议分步咨询。",
            "risk_level": "high",
            "error": str(e),
        }
    except RuntimeLoopDetectedError as e:
        from tools.logger import get_logger as _get_logger
        _logger = _get_logger(__name__)
        _logger.warning("检测到工具调用循环 (trace={}): {}", trace_id, e)
        return {
            **initial_state,
            "final_answer": "抱歉，系统检测到处理异常（重复调用），已自动终止。请尝试换一种方式描述您的需求。",
            "risk_level": "high",
            "error": str(e),
        }
    except Exception as e:
        from tools.logger import get_logger as _get_logger
        _logger = _get_logger(__name__)
        _logger.error("Agent 执行未预期异常 (trace={}): {}", trace_id, e, exc_info=True)
        return {
            **initial_state,
            "final_answer": "抱歉，系统处理您的请求时遇到技术问题。请稍后重试，或联系管理员。",
            "risk_level": "high",
            "error": str(e),
        }


# ============================================================
# Streaming Executor — SSE 节点级流式输出
# ============================================================


async def stream_agent(
    user_query: str,
    user_id: str,
    trace_id: str,
    settings: Settings,
    tenant_id: str = "default",
    user_role: str = "user",
    conversation_id: Optional[str] = None,
    prior_messages: Optional[list[dict]] = None,
):
    """
    流式执行 Agent 工作流（供 /api/chat/stream SSE 使用）。

    yield (kind, payload):
        ("node", node_name)  — 每个 LangGraph 节点进入（state.current_node）
        ("final", state)     — 最终 AgentState（含 final_answer 等）
        ("error", message)   — 执行失败

    用 graph.astream(stream_mode="values")：每个 superstep 产出完整状态，
    既拿节点名，又拿最终状态，避免重复执行。

    P1-7：支持 conversation_id / prior_messages 多轮上下文，与 /api/chat 对齐
    （多轮时 thread_id 用 conversation_id，保持 LangGraph 会话上下文）。
    """
    from orchestration.langgraph.state import create_initial_state

    input_check, entry_pii, safe_query, prior_messages = check_input_safety(
        user_query, trace_id, prior_messages,
    )

    # 多轮历史 → 文本上下文（供规划/汇总 LLM 参考），与 execute_agent 一致
    conversation_history = ""
    if prior_messages:
        try:
            from backend.services.conversation_service import format_history_text
            conversation_history = format_history_text(prior_messages)
        except Exception:
            conversation_history = ""

    # ── 输入护栏：在 LLM 调用前检查（P1-8：脱敏后进入 LLM） ──

    initial_state = create_initial_state(
        user_query=safe_query,
        trace_id=trace_id,
        messages=prior_messages or [],
        conversation_history=conversation_history,
        user_id=user_id,
        tenant_id=tenant_id,
        user_role=user_role,
    )
    if entry_pii:
        initial_state["safety_check"] = {"pii_detected": entry_pii}

    graph = await get_agent_graph(settings)
    config = {
        "configurable": {
            "thread_id": checkpoint_thread_id(tenant_id, user_id, conversation_id or trace_id),
            "user_id": user_id,
            "tenant_id": tenant_id,
        },
    }

    initial_state["checkpoint_thread_id"] = config["configurable"]["thread_id"]
    if input_check is not None and input_check.blocked:
        yield ("final", {
            **initial_state,
            "final_answer": "抱歉，您的输入包含不安全内容，系统已自动拦截。",
            "risk_level": "high",
            "safety_check": input_check.to_dict(),
        })
        return

    from governance.trace import (
        end_trace,
        flush_trace_to_db,
        reset_trace_user,
        set_trace_user,
        start_trace_with_id,
    )

    trace_tokens = set_trace_user(user_id, tenant_id)
    start_trace_with_id(trace_id, user_query=initial_state.get("user_query", ""))
    try:
        final_state = None
        # langgraph stub: stream_mode 字符串 + dict config 与 Pregel.astream 的
        # RunnableConfig/StreamMode overload 不完全匹配，运行时（SSE 流式）正常
        async for state in graph.astream(initial_state, config=config, stream_mode="values"):  # type: ignore[call-overload]
            node_name = state.get("current_node", "") or ""
            if node_name:
                yield ("node", node_name)
            final_state = state
    finally:
        end_trace()
        reset_trace_user(trace_tokens)
    # P2-1：流结束前批量落库（final 事件消费时已完成所有 span 记录）
    try:
        await flush_trace_to_db(trace_id)
    except Exception as e:
        get_logger(__name__).warning(
            "流式 trace 落库失败（trace_id={}），审计数据可能丢失: {}", trace_id, e
        )
    yield ("final", final_state if final_state is not None else initial_state)
