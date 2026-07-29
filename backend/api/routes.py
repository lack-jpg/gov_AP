"""
backend.api.routes - API routes: /chat, /agent, /evaluation, /a2a/callback endpoints

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement all API endpoint routes
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import (
    execute_agent,
    get_config,
    get_trace_id,
    get_user_id,
)
from backend.api.schemas import (
    A2ACallbackRequest,
    A2ACallbackResponse,
    AgentStatusRequest,
    AgentStatusResponse,
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    EvidenceItem,
)
from backend.config import Settings
from tools.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Agent Platform"])


# ============================================================
# POST /api/chat — 用户对话（核心端点）
# ============================================================


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {"description": "Agent处理完成"},
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    },
    summary="用户对话",
    description="接收用户自然语言输入，经过多Agent协同处理后返回结构化回答。",
)
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_user_id),
    trace_id: str = Depends(get_trace_id),
    settings: Settings = Depends(get_config),
) -> ChatResponse:
    """
    用户对话端点。

    流程: User Query → Supervisor → Intent → Policy/Material → Workflow → Governance → Answer

    Args:
        request: 对话请求体
        user_id: 从Header提取的用户ID
        trace_id: 自动生成或客户端传入的trace_id
        settings: 应用配置

    Returns:
        ChatResponse (trace_id, answer, evidence, intent, risk_level, elapsed_ms)
    """
    start = time.perf_counter()

    # 使用客户端传入的trace_id（如果有）
    effective_trace_id = request.trace_id or trace_id

    try:
        # 执行Agent工作流
        result = await execute_agent(
            user_query=request.user_query,
            user_id=user_id,
            trace_id=effective_trace_id,
            settings=settings,
        )
    except Exception as e:
        logger.error(f"[{effective_trace_id}] Agent execution failed: {e}", exc_info=True)
        elapsed = (time.perf_counter() - start) * 1000
        return ChatResponse(
            trace_id=effective_trace_id,
            answer="抱歉，系统处理您的请求时遇到问题，请稍后重试。",
            evidence=[],
            intent="",
            risk_level="high",
            execution_steps=0,
            elapsed_ms=elapsed,
            error=str(e) if settings.debug else "Agent execution failed",
        )

    elapsed = (time.perf_counter() - start) * 1000

    # 从State中提取响应字段
    evidence_items: list[EvidenceItem] = []
    evidence_list = result.get("evidence", [])
    if isinstance(evidence_list, list):
        for ev in evidence_list:
            if isinstance(ev, dict):
                evidence_items.append(EvidenceItem(
                    source=ev.get("source", ""),
                    excerpt=ev.get("excerpt", ""),
                    relevance_score=ev.get("relevance_score", 0.0),
                ))

    step_count = len(result.get("mcp_history", []))

    return ChatResponse(
        trace_id=effective_trace_id,
        answer=result.get("final_answer", "抱歉，未能生成回答。"),
        evidence=evidence_items,
        intent=result.get("intent", ""),
        risk_level=result.get("risk_level", "low"),
        execution_steps=step_count,
        elapsed_ms=elapsed,
        error=result.get("error") if result.get("error") else None,
    )


# ============================================================
# GET /api/agent/status/{trace_id} — Agent执行状态查询
# ============================================================


@router.get(
    "/agent/status/{trace_id}",
    response_model=AgentStatusResponse,
    summary="查询Agent执行状态",
    description="根据trace_id查询指定Agent工作流的执行状态",
)
async def get_agent_status(
    trace_id: str,
    user_id: str = Depends(get_user_id),
    settings: Settings = Depends(get_config),
) -> AgentStatusResponse:
    """
    查询Agent执行状态。

    用于前端轮询长耗时任务（特别是A2A异步任务）的状态。

    Args:
        trace_id: 要查询的trace_id
        user_id: 用户ID
        settings: 应用配置

    Returns:
        AgentStatusResponse
    """
    # TODO: 从数据库/Redis按trace_id查询执行状态
    # 当前stub: 返回固定值
    return AgentStatusResponse(
        trace_id=trace_id,
        status="completed",
        current_node="governance_node",
        current_agent="governance",
        steps_completed=0,
        final_answer=None,
    )


# ============================================================
# POST /api/a2a/callback — A2A外部Agent回调
# ============================================================


@router.post(
    "/a2a/callback",
    response_model=A2ACallbackResponse,
    summary="A2A外部Agent回调",
    description="接收外部Agent（如不动产系统、公积金系统）的异步任务完成通知",
)
async def a2a_callback(
    request: A2ACallbackRequest,
    settings: Settings = Depends(get_config),
) -> A2ACallbackResponse:
    """
    A2A Callback端点。

    外部Agent完成任务后回调此端点：
    1. 根据task_id找到原LangGraph checkpoint
    2. 注入external_result到State
    3. 恢复LangGraph执行

    Args:
        request: 回调请求体（task_id, status, artifact, error_message）
        settings: 应用配置

    Returns:
        A2ACallbackResponse
    """
    task_id = request.task_id

    # TODO: 从数据库/Redis根据task_id查找对应的checkpoint
    # 然后恢复LangGraph执行:
    #   1. 找到原始 trace_id → checkpoint_id
    #   2. 读取AgentState checkpoint
    #   3. 注入 external_result = request.artifact
    #   4. graph.ainvoke(resumed_state, config)

    logger.info(
        f"A2A callback received: task_id={task_id}, "
        f"status={request.status}"
    )

    return A2ACallbackResponse(
        success=True,
        message=f"Callback for task {task_id} acknowledged (stub mode)",
    )


# ============================================================
# GET /api/dashboard/overview — 运维看板概览
# ============================================================


@router.get(
    "/dashboard/overview",
    summary="运维看板概览",
    description="获取Agent平台整体运行指标",
)
async def dashboard_overview(
    user_id: str = Depends(get_user_id),
    settings: Settings = Depends(get_config),
) -> dict:
    """
    运维看板数据API。

    TODO: 从数据库/Trace中统计真实数据：
        - 总请求数
        - 成功率
        - 平均耗时
        - 活跃Agent数
        - MCP调用次数
        - A2A任务数
    """
    return {
        "total_requests": 0,
        "success_rate": 0.0,
        "avg_latency_ms": 0.0,
        "active_agents": 6,
        "tool_call_count": 0,
        "a2a_task_count": 0,
    }


# ============================================================
# GET /api/evaluation/report/{version} — 评测报告
# ============================================================


@router.get(
    "/evaluation/report/{version}",
    summary="获取评测报告",
    description="获取指定版本的Agent评测报告",
)
async def evaluation_report(
    version: str,
    user_id: str = Depends(get_user_id),
    settings: Settings = Depends(get_config),
) -> dict:
    """
    评测报告API。

    TODO: 从evaluation表中读取评测数据。

    Args:
        version: 评测版本号
        user_id: 用户ID
        settings: 应用配置

    Returns:
        评测指标字典
    """
    return {
        "version": version,
        "task_success_rate": 0.0,
        "rag_faithfulness": 0.0,
        "rag_answer_relevance": 0.0,
        "tool_accuracy": 0.0,
        "avg_latency_ms": 0.0,
        "avg_step_count": 0.0,
    }
