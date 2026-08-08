"""
backend.api.routes - API routes: /chat, /agent, /evaluation, /a2a/callback endpoints

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement all API endpoint routes
"""
from __future__ import annotations

import json
import os
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
    conversation_id = request.conversation_id or None

    # 多轮对话：加载历史上下文 + 确保会话存在
    prior_messages: list[dict] = []
    if conversation_id:
        try:
            from backend.services.conversation_service import (
                add_message,
                create_conversation,
                get_conversation,
                load_history,
            )

            prior_messages = await load_history(conversation_id)
            if await get_conversation(conversation_id) is None:
                await create_conversation(
                    user_id, title=request.user_query[:50], conversation_id=conversation_id,
                )
        except Exception:
            prior_messages = []

    try:
        # 执行Agent工作流
        result = await execute_agent(
            user_query=request.user_query,
            user_id=user_id,
            trace_id=effective_trace_id,
            settings=settings,
            conversation_id=conversation_id,
            prior_messages=prior_messages,
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

    # 多轮对话：持久化 user 问题 + assistant 回答（含 trace_id）
    if conversation_id:
        try:
            from backend.services.conversation_service import (
                add_message,
                update_conversation_title,
            )

            await add_message(conversation_id, "user", request.user_query)
            answer_text = result.get("final_answer", "")
            if answer_text:
                await add_message(conversation_id, "assistant", answer_text, trace_id=effective_trace_id)
            # 标题默认取首条用户问题
            conv = await get_conversation(conversation_id)
            if conv and conv.get("title", "新对话") == "新对话":
                await update_conversation_title(conversation_id, request.user_query[:50])
        except Exception as e:
            logger.warning("对话消息持久化失败: {}", e)

    return ChatResponse(
        trace_id=effective_trace_id,
        conversation_id=conversation_id,
        answer=result.get("final_answer", "抱歉，未能生成回答。"),
        evidence=evidence_items,
        intent=result.get("intent", ""),
        risk_level=result.get("risk_level", "low"),
        execution_steps=step_count,
        elapsed_ms=elapsed,
        error=result.get("error") if result.get("error") else None,
    )


# ============================================================
# POST /api/chat/stream — 流式对话（SSE，节点级进度）
# ============================================================

_NODE_LABELS: dict[str, str] = {
    "supervisor_node": "任务规划",
    "intent_node": "意图识别",
    "policy_node": "政策检索",
    "material_node": "材料审核",
    "workflow_node": "流程执行",
    "a2a_node": "跨域协同",
    "governance_node": "安全审查",
}


@router.post(
    "/chat/stream",
    summary="流式对话（SSE）",
    description="以 Server-Sent Events 流式返回 Agent 工作流的节点级进度与最终回答",
)
async def chat_stream(
    request: ChatRequest,
    user_id: str = Depends(get_user_id),
    trace_id: str = Depends(get_trace_id),
    settings: Settings = Depends(get_config),
):
    """
    流式对话端点。

    SSE 事件：
        data: {"event":"node","node":"intent_node","label":"意图识别"}
        data: {"event":"final","answer":..., "trace_id":..., "intent":..., "elapsed_ms":...}
        data: {"event":"error","message":...}
    """
    from fastapi.responses import StreamingResponse
    from backend.api.dependencies import stream_agent

    effective_trace_id = request.trace_id or trace_id

    async def event_generator():
        start = time.perf_counter()
        try:
            async for kind, payload in stream_agent(
                request.user_query, user_id, effective_trace_id, settings,
            ):
                if kind == "node":
                    label = _NODE_LABELS.get(payload, payload)
                    yield f"data: {json.dumps({'event': 'node', 'node': payload, 'label': label}, ensure_ascii=False)}\n\n"
                elif kind == "final":
                    elapsed = (time.perf_counter() - start) * 1000
                    final_event = {
                        "event": "final",
                        "trace_id": effective_trace_id,
                        "answer": payload.get("final_answer", "抱歉，未能生成回答。"),
                        "intent": payload.get("intent", ""),
                        "risk_level": payload.get("risk_level", "low"),
                        "execution_steps": len(payload.get("mcp_history", [])),
                        "elapsed_ms": round(elapsed, 1),
                        "evidence": payload.get("evidence", []),
                        "error": payload.get("error"),
                    }
                    yield f"data: {json.dumps(final_event, ensure_ascii=False, default=str)}\n\n"
                elif kind == "error":
                    yield f"data: {json.dumps({'event': 'error', 'message': str(payload)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("SSE 流式对话异常: {}", e)
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 多轮对话会话 — 创建 / 列表 / 消息
# ============================================================


@router.post(
    "/conversations",
    summary="创建会话",
    description="创建一个多轮对话会话，返回 conversation_id 供后续 /api/chat 关联",
)
async def create_conversation_endpoint(
    user_id: str = Depends(get_user_id),
) -> dict:
    from backend.services.conversation_service import create_conversation

    return await create_conversation(user_id)


@router.get(
    "/conversations",
    summary="会话列表",
    description="列出当前用户的多轮对话会话（按更新时间倒序）",
)
async def list_conversations_endpoint(
    user_id: str = Depends(get_user_id),
) -> dict:
    from backend.services.conversation_service import list_conversations

    items = await list_conversations(user_id)
    return {"items": items, "total": len(items)}


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="会话消息",
    description="获取指定会话的全部历史消息（按时间正序）",
)
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_user_id),
) -> dict:
    from backend.services.conversation_service import list_messages

    messages = await list_messages(conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


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

    从 trace 表按 trace_id 聚合真实执行状态；
    数据库不可用时回退到内存 TraceRecorder。

    用于前端轮询长耗时任务（特别是A2A异步任务）的状态。

    Args:
        trace_id: 要查询的trace_id
        user_id: 用户ID
        settings: 应用配置

    Returns:
        AgentStatusResponse
    """
    # ── 1. 从数据库 trace 表查询 ──
    try:
        from database.connection import get_session_factory
        from database.models import Trace
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(Trace)
                .where(Trace.trace_id == trace_id)
                .order_by(Trace.created_at.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if rows:
            return _aggregate_status_from_db(trace_id, rows)
    except Exception as e:
        logger.warning("查询 trace 表失败，回退内存: {}", e)

    # ── 2. 回退：内存 TraceRecorder ──
    try:
        from governance.trace import get_trace_recorder
        spans = get_trace_recorder().get_spans_by_trace(trace_id)
        if spans:
            return _aggregate_status_from_spans(trace_id, spans)
    except Exception:
        pass

    return AgentStatusResponse(
        trace_id=trace_id,
        status="unknown",
        current_node="",
        current_agent="",
        steps_completed=0,
        final_answer=None,
    )


def _aggregate_status_from_db(trace_id: str, rows) -> AgentStatusResponse:
    """
    从 trace 表记录聚合执行状态。

    Args:
        trace_id: 链路追踪 ID
        rows: 按时间正序排列的 Trace ORM 记录

    Returns:
        AgentStatusResponse
    """
    statuses = [r.status for r in rows if r.status]

    if any(s == "failed" for s in statuses):
        status = "failed"
    elif any(s == "running" for s in statuses):
        status = "running"
    elif all(s in ("success", "completed") for s in statuses):
        status = "completed"
    else:
        status = "pending"

    last = rows[-1]
    return AgentStatusResponse(
        trace_id=trace_id,
        status=status,
        current_node=last.node_name or "",
        current_agent=last.agent_name or "",
        steps_completed=len(rows),
        final_answer=_extract_final_answer(last.output_data),
    )


def _aggregate_status_from_spans(trace_id: str, spans) -> AgentStatusResponse:
    """
    从内存 SpanRecord 列表聚合执行状态。

    Args:
        trace_id: 链路追踪 ID
        spans: SpanRecord 列表（时间正序）

    Returns:
        AgentStatusResponse
    """
    statuses = [s.status.value for s in spans if s.status]

    if any(st == "failed" for st in statuses):
        status = "failed"
    elif any(st == "running" for st in statuses):
        status = "running"
    elif all(st in ("success", "completed") for st in statuses):
        status = "completed"
    else:
        status = "pending"

    last = spans[-1]
    return AgentStatusResponse(
        trace_id=trace_id,
        status=status,
        current_node=last.node_name or "",
        current_agent=last.agent_name or "",
        steps_completed=len(spans),
        final_answer=_extract_final_answer(last.output_data),
    )


def _extract_final_answer(output_data) -> str | None:
    """
    从 Agent 输出中提取 final_answer。

    支持 JSON 字符串或纯文本。
    """
    if not output_data:
        return None
    if isinstance(output_data, dict):
        return output_data.get("final_answer") or output_data.get("answer")

    try:
        parsed = json.loads(output_data)
        if isinstance(parsed, dict):
            return parsed.get("final_answer") or parsed.get("answer")
    except (json.JSONDecodeError, TypeError):
        pass
    return output_data if isinstance(output_data, str) else None


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
    1. HMAC 签名验证（防伪造回调）
    2. 根据task_id找到原LangGraph checkpoint
    3. 注入external_result到State
    4. 恢复LangGraph执行

    Args:
        request: 回调请求体（task_id, status, artifact, error_message, signature, timestamp）
        settings: 应用配置

    Returns:
        A2ACallbackResponse
    """
    # ── HMAC 签名验证 ──
    import hashlib
    import hmac
    import time as _time

    if settings.a2a_hmac_secret:
        now_ts = int(_time.time())
        req_ts = request.timestamp

        # 时间窗口校验（±300 秒防重放）
        if abs(now_ts - req_ts) > 300:
            logger.warning(
                "A2A callback 时间戳过期: task_id={task_id} req_ts={req_ts} now={now}",
                task_id=request.task_id, req_ts=req_ts, now=now_ts,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请求时间戳过期，请重新签名",
            )

        # 计算期望签名
        sign_payload = f"{request.task_id}|{request.status}|{request.timestamp}"
        expected_sig = hmac.new(
            settings.a2a_hmac_secret.encode("utf-8"),
            sign_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, request.signature):
            logger.warning(
                "A2A callback 签名验证失败: task_id={task_id}",
                task_id=request.task_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="HMAC 签名验证失败",
            )
    else:
        logger.warning(
            "A2A HMAC secret 未配置，跳过回调签名验证（不安全的配置）"
        )

    task_id = request.task_id

    try:
        from tools.a2a.callback import get_callback_handler

        handler = get_callback_handler()
        result = await handler.process_callback(
            task_id=task_id,
            status_str=request.status,
            artifact=request.artifact,
            error_message=request.error_message,
        )

        logger.info(
            "A2A callback processed: task_id={task_id}, status={status}, resumed={resumed}",
            task_id=task_id,
            status=request.status,
            resumed=result.get("checkpoint_resumed", False),
        )

        # 如果 checkpoint 恢复成功，尝试恢复 LangGraph 执行
        if result.get("checkpoint_resumed") and request.status == "completed":
            try:
                # 尝试恢复 Agent 工作流
                await _resume_agent_after_callback(task_id, request.artifact or {}, settings)
            except Exception as e:
                logger.error("恢复 Agent 工作流失败: {}", e)

        return A2ACallbackResponse(
            success=result["success"],
            message=result["message"],
        )

    except Exception as e:
        logger.error(f"A2A callback processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Callback processing failed: {e}",
        )


async def _resume_agent_after_callback(
    task_id: str,
    artifact: dict,
    settings: Settings,
) -> None:
    """
    在 A2A 回调后恢复 Agent 工作流执行。

    Args:
        task_id: A2A 任务 ID
        artifact: 外部 Agent 返回的结果
        settings: 应用配置
    """
    try:
        from orchestration.langgraph.checkpointer import PostgresCheckpointer
        from database.connection import get_session_factory

        factory = get_session_factory()
        if factory is None:
            logger.warning("数据库不可用，无法恢复 Agent 工作流")
            return

        checkpointer = PostgresCheckpointer()
        checkpoint_tuple = await checkpointer.resume_from_a2a(task_id)

        if checkpoint_tuple is None:
            logger.warning("未找到 A2A 挂起的 checkpoint: {task_id}", task_id=task_id)
            return

        # 从 checkpoint 恢复 state
        checkpoint_state = checkpoint_tuple.checkpoint.get("channel_values", {})

        # 注入 external_result；保留 waiting_task_id（a2a_node 凭它进入 resume 分支并清除）
        resumed_state = {
            **checkpoint_state,
            "external_result": artifact,
        }

        # 获取 graph 并恢复执行
        from backend.api.dependencies import get_agent_graph
        graph = await get_agent_graph(settings)

        config = checkpoint_tuple.config
        config["configurable"]["resumed_from_checkpoint"] = True

        await graph.ainvoke(resumed_state, config=config)
        logger.info("A2A 恢复执行完成: task_id={task_id}", task_id=task_id)

    except Exception as e:
        logger.error("A2A 恢复执行失败: {task_id} — {error}", task_id=task_id, error=e)
        raise


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

    从数据库 Trace 表统计真实指标（DB 不可用时回退内存监控数据）：
        - 总请求数
        - 成功率
        - 平均耗时
        - 活跃Agent数
        - MCP调用次数
        - A2A任务数
    """
    from governance.dashboard import get_dashboard_provider

    provider = get_dashboard_provider()

    # 优先 DB 模式；DB 无数据时回退内存监控
    try:
        summary = await provider.get_summary(use_db=True)
        if not summary.agent_stats:
            memory_summary = await provider.get_summary(use_db=False)
            if memory_summary.agent_stats:
                summary = memory_summary
    except Exception:
        summary = await provider.get_summary(use_db=False)

    agent_stats = summary.agent_stats
    total_requests = sum(a.total_calls for a in agent_stats)
    success_count = sum(a.success_count for a in agent_stats)
    success_rate = success_count / total_requests if total_requests else 0.0

    latencies = [a.avg_latency_ms for a in agent_stats if a.total_calls > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    # MCP 工具调用次数（内存 span 统计）
    tool_call_count = 0
    try:
        from governance.trace import SpanKind, get_trace_recorder
        tool_call_count = sum(
            1 for s in get_trace_recorder().spans if s.kind == SpanKind.TOOL
        )
    except Exception:
        pass

    # A2A 任务数（TaskStore 统计）
    a2a_task_count = 0
    try:
        from tools.a2a.task import get_task_store
        a2a_task_count = get_task_store().count()
    except Exception:
        pass

    # Token 用量 + 每 Agent 统计 + 评测趋势（供前端图表）
    total_tokens = sum(a.total_tokens for a in agent_stats)

    return {
        "total_requests": total_requests,
        "success_rate": round(success_rate, 4),
        "avg_latency_ms": round(avg_latency, 2),
        "active_agents": len(agent_stats),
        "tool_call_count": tool_call_count,
        "a2a_task_count": a2a_task_count,
        "total_tokens": total_tokens,
        "agent_stats": [a.to_dict() for a in agent_stats],
        "eval_trends": [e.to_dict() for e in summary.eval_trends],
    }


# ============================================================
# GET /api/evaluation/report/{version} — 评测报告
# ============================================================


# ============================================================
# 评测报告文件回退（evaluation_results/*.json）
#
# benchmark runner 支持 --save-result 写文件 / --save-to-db 写库。
# 若只写了文件（或 DB 被重建/无记录），API 直接返回 404/错误。
# 这里在 DB 无记录或 DB 不可用时，回退读取 evaluation_results/
# 下匹配 version 的 benchmark JSON，聚合各 dataset 指标返回。
# ============================================================


def _evaluation_results_dir() -> str:
    """evaluation_results 目录（项目根下，相对本文件上溯 3 层）"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "evaluation_results",
    )


def _aggregate_benchmark_report(data: dict, version: str) -> dict:
    """将 benchmark JSON（含多个 dataset）聚合成与 DB Evaluation 记录同构的 dict。

    各指标按 dataset 用例数加权平均；总用例/通过数求和。
    benchmark dataset 结构:
        agent: {task_success_rate, tool_accuracy, avg_latency_ms, avg_step_count, total_cases, passed_cases}
        rag:   {faithfulness, answer_relevance, context_recall}
    """
    datasets = data.get("datasets", {})
    total = 0
    passed = 0
    t_success = t_tool = t_faith = t_rel = t_recall = t_lat = t_steps = 0.0

    for ds in datasets.values():
        if not isinstance(ds, dict):
            continue
        agent = ds.get("agent") or {}
        rag = ds.get("rag") or {}
        n = int(agent.get("total_cases", 0) or 0)
        total += n
        passed += int(ds.get("passed_cases", 0) or 0)
        t_success += float(agent.get("task_success_rate", 0) or 0) * n
        t_tool += float(agent.get("tool_accuracy", 0) or 0) * n
        t_faith += float(rag.get("faithfulness", 0) or 0) * n
        t_rel += float(rag.get("answer_relevance", 0) or 0) * n
        t_recall += float(rag.get("context_recall", 0) or 0) * n
        t_lat += float(agent.get("avg_latency_ms", 0) or 0) * n
        t_steps += float(agent.get("avg_step_count", 0) or 0) * n

    def _avg(v: float) -> float:
        return round(v / total, 4) if total else 0.0

    return {
        "version": version,
        "task_success_rate": _avg(t_success),
        "tool_accuracy": _avg(t_tool),
        "rag_faithfulness": _avg(t_faith),
        "rag_answer_relevance": _avg(t_rel),
        "rag_context_recall": _avg(t_recall),
        "avg_latency_ms": round(_avg(t_lat), 2),
        "avg_step_count": round(_avg(t_steps), 2),
        "total_cases": total,
        "passed_cases": passed,
        "created_at": str(data.get("created_at", "")),
        "source": "file",
    }


def _load_benchmark_report_file(version: str) -> dict | None:
    """从 evaluation_results/ 读取匹配 version 的最新 benchmark JSON 并聚合。

    匹配依据为 JSON 内 version 字段（而非文件名），多个文件取 created_at 最新者。
    未找到返回 None。
    """
    results_dir = _evaluation_results_dir()
    if not os.path.isdir(results_dir):
        return None

    candidates: list[tuple[str, dict]] = []
    for name in os.listdir(results_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(results_dir, name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict) or str(data.get("version", "")) != str(version):
            continue
        candidates.append((str(data.get("created_at", "")), data))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return _aggregate_benchmark_report(candidates[0][1], version)


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

    从 evaluation 表读取指定版本最新的评测结果。
    无记录时返回 404（提示先运行评测）；
    数据库不可用时返回空指标结构。

    Args:
        version: 评测版本号
        user_id: 用户ID
        settings: 应用配置

    Returns:
        评测指标字典
    """
    try:
        from database.connection import get_session_factory
        from database.models import Evaluation
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(Evaluation)
                .where(Evaluation.version == version)
                .order_by(Evaluation.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            record = result.scalars().first()

        if record is None:
            # DB 无记录 → 回退读取 evaluation_results/ 下的 benchmark 文件
            file_report = _load_benchmark_report_file(version)
            if file_report is not None:
                return file_report
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"未找到版本 '{version}' 的评测报告。"
                    "请先运行: python -m governance.evaluation.runner run "
                    f"--version {version} --save-result evaluation_results/{version}.json"
                ),
            )

        return {
            "version": record.version,
            "task_success_rate": round(record.task_success_rate, 4),
            "rag_faithfulness": round(record.rag_faithfulness, 4),
            "rag_answer_relevance": round(record.rag_answer_relevance, 4),
            "rag_context_recall": round(record.rag_context_recall, 4),
            "tool_accuracy": round(record.tool_accuracy, 4),
            "avg_latency_ms": round(record.avg_latency_ms, 2),
            "avg_step_count": round(record.avg_step_count, 2),
            "total_cases": record.total_cases,
            "passed_cases": record.passed_cases,
            "created_at": str(record.created_at),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("查询评测报告失败 (version={}): {}", version, e)
        # DB 不可用 → 回退读取 evaluation_results/ 下的 benchmark 文件
        try:
            file_report = _load_benchmark_report_file(version)
            if file_report is not None:
                return file_report
        except Exception as fe:
            logger.warning("评测报告文件回退失败 (version={}): {}", version, fe)
        return {
            "version": version,
            "task_success_rate": 0.0,
            "rag_faithfulness": 0.0,
            "rag_answer_relevance": 0.0,
            "rag_context_recall": 0.0,
            "tool_accuracy": 0.0,
            "avg_latency_ms": 0.0,
            "avg_step_count": 0.0,
            "total_cases": 0,
            "passed_cases": 0,
            "error": str(e) if settings.debug else "评测报告暂时不可用，请稍后重试",
        }
