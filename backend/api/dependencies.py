"""
backend.api.dependencies - FastAPI dependencies: DB session, current user, agent runtime injection

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement FastAPI dependency injection for common resources
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from langgraph.graph import StateGraph

from backend.config import Settings, get_settings


# ============================================================
# User ID — 从Header提取
# ============================================================


async def get_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> str:
    """
    从HTTP Header提取用户ID。

    生产环境应替换为JWT验证逻辑（参考 backend/middleware/auth.py）。

    Args:
        x_user_id: 用户ID（Header: X-User-Id）
        x_user_role: 用户角色（Header: X-User-Role）

    Returns:
        用户ID

    Raises:
        HTTPException: 未认证时返回401
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )
    return x_user_id


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
# Agent Graph — 单例注入（惰性初始化）
# ============================================================

_agent_graph: Optional[StateGraph] = None


async def get_agent_graph(
    settings: Settings = Depends(get_config),
) -> StateGraph:
    """
    获取或惰性创建Agent Graph（单例）。

    首次调用时构建Graph，后续复用同一个实例。
    构建时使用LLM如果配置中提供了API Key。

    Args:
        settings: 应用配置

    Returns:
        编译好的LangGraph StateGraph
    """
    global _agent_graph

    if _agent_graph is not None:
        return _agent_graph

    # 惰性构建
    from orchestration.langgraph.graph import build_graph

    # 如果有LLM配置，构建带LLM的Graph
    llm = None
    if settings.llm_api_key:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                base_url=settings.llm_api_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
            )
        except ImportError:
            pass  # 没有langchain_openai时使用stub模式

    _agent_graph = build_graph(llm=llm)
    return _agent_graph


# ============================================================
# Executor — Agent执行器（封装 graph.ainvoke）
# ============================================================


async def execute_agent(
    user_query: str,
    user_id: str,
    trace_id: str,
    settings: Settings,
) -> dict:
    """
    执行一次完整的Agent工作流。

    创建初始State → 调用graph.ainvoke → 返回最终State。

    Args:
        user_query: 用户输入
        user_id: 用户ID
        trace_id: 链路追踪ID
        settings: 应用配置

    Returns:
        执行后的AgentState字典
    """
    from orchestration.langgraph.state import create_initial_state

    # 创建初始State
    initial_state = create_initial_state(user_query=user_query, trace_id=trace_id)

    # 获取Graph
    graph = await get_agent_graph(settings)

    # 执行（config中包含thread_id用于checkpoint）
    config = {
        "configurable": {
            "thread_id": trace_id,
            "user_id": user_id,
        },
        "recursion_limit": settings.agent_max_steps * 2,
    }
    result = await graph.ainvoke(initial_state, config=config)

    return result
