"""
governance.evaluation.trace_provider — 真实 Agent 工作流 trace 提供者

为评测系统提供 trace_provider 回调，对每个 case 运行 Agent 并收集 trace。
两条路径：
  - Intent-only 用例：直接用本地 BERT 分类（快速，3500 条秒级完成）
  - 全流程用例：运行完整 LangGraph 工作流（含 LLM/MCP，~330 条）

Author: le
Date: 2026/8/4
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


async def create_trace_provider(
    *,
    settings: Any = None,
    run_full_workflow: bool = False,
) -> Callable[[dict], Any]:
    """
    创建 trace_provider 回调。

    Args:
        settings: 应用配置实例（backend.config.Settings）。
                  为 None 时从默认路径加载。
        run_full_workflow: 是否对全流程用例运行 LangGraph。
                           False 时只对 intent-only 用例跑 BERT，
                           全流程用例返回空 trace（跳过）。

    Returns:
        async (case: dict) -> list[dict] 回调
    """
    # ── lazy-init ──
    _classifier: Any = None
    _settings: Any = None

    def _get_settings():
        nonlocal _settings
        if _settings is None:
            if settings is not None:
                _settings = settings
            else:
                from backend.config import get_settings
                _settings = get_settings()
        return _settings

    def _get_classifier():
        nonlocal _classifier
        if _classifier is None:
            from agents.intent.classifier import IntentClassifier
            _classifier = IntentClassifier()  # auto_load=True，加载 BERT
            logger.info(
                "trace_provider: BERT 模型已加载={}",
                _classifier.is_model_loaded,
            )
        return _classifier

    # ── 内部：intent-only 路径 ──
    async def _run_intent_only(case: dict) -> list[dict]:
        """用 BERT 直接分类，返回简化 trace"""
        query = case.get("query", "")
        expected = case.get("expected_intent", "")

        classifier = _get_classifier()
        result = await classifier.classify(query)

        logger.debug(
            "intent case {}: {} -> {} (src={}, conf={:.2f})",
            case.get("id", "?"), query[:30], result.label,
            result.source, result.confidence,
        )

        return [{
            "agent_name": "intent",
            "node_name": "intent_node",
            "status": "success" if result.label == expected else "failed",
            "output_data": result.label,
            "input_data": query,
            "metadata_": {
                "intent": result.label,
                "confidence": result.confidence,
                "source": result.source,
            },
            "latency_ms": 0.0,
            "step_count": 1,
        }]

    # ── 内部：全流程路径 ──
    async def _run_full_workflow(case: dict) -> list[dict]:
        """运行完整 LangGraph 工作流，收集所有 trace"""
        query = case.get("query", "")
        case_id = case.get("id", "unknown")
        trace_id = f"eval_{case_id}"

        from governance.trace import reset_trace_recorder, get_trace_recorder

        # 每个 case 隔离 trace 上下文
        reset_trace_recorder()

        cfg = _get_settings()
        from backend.api.dependencies import execute_agent

        t_start = time.perf_counter()
        try:
            state = await execute_agent(
                user_query=query,
                user_id="eval_user",
                trace_id=trace_id,
                settings=cfg,
            )
            elapsed_ms = (time.perf_counter() - t_start) * 1000
        except Exception as e:
            logger.error("全流程执行失败 case {}: {}", case_id, e)
            return [{
                "agent_name": "supervisor",
                "status": "failed",
                "error_message": str(e)[:500],
                "input_data": query,
                "latency_ms": (time.perf_counter() - t_start) * 1000,
                "step_count": 0,
            }]

        # 收集 trace_recorder 中的 spans
        recorder = get_trace_recorder()
        traces: list[dict] = []
        for span in recorder.spans:
            d = span.to_db_dict()
            # 补充 created_at 时间戳
            if span.started_at:
                d["created_at"] = span.started_at.isoformat()
            traces.append(d)

        # 附加完整的状态级 trace（mcp_history / evidence / final_answer 等）
        state_trace: dict[str, Any] = {
            "agent_name": "workflow",
            "node_name": "workflow_node",
            "status": "success" if state.get("final_answer") else "failed",
            "input_data": query,
            "output_data": json.dumps(
                {
                    "final_answer": state.get("final_answer", ""),
                    "intent": state.get("intent", ""),
                    "risk_level": state.get("risk_level", "low"),
                },
                ensure_ascii=False,
            ),
            "mcp_history": state.get("mcp_history", []),
            "evidence": state.get("evidence", []),
            "metadata_": {
                "intent": state.get("intent", ""),
                "contexts": [
                    e.get("content", "")
                    for e in state.get("evidence", [])
                    if isinstance(e, dict)
                ],
            },
            "latency_ms": elapsed_ms,
            "step_count": len(state.get("mcp_history", [])),
            "created_at": None,
        }
        traces.append(state_trace)

        # 如果有 intent_result，添加独立的 intent trace
        intent_result = state.get("intent_result") or {}
        if intent_result:
            traces.append({
                "agent_name": "intent",
                "node_name": "intent_node",
                "status": "success",
                "output_data": intent_result.get("label", ""),
                "metadata_": {
                    "intent": intent_result.get("label", ""),
                    "confidence": intent_result.get("confidence", 0.0),
                    "source": intent_result.get("source", ""),
                },
                "latency_ms": 0.0,
                "step_count": 1,
            })

        logger.info(
            "全流程 case {}: {} -> intent={}, answer_len={}, traces={}",
            case_id, query[:30],
            state.get("intent", ""),
            len(state.get("final_answer", "")),
            len(traces),
        )
        return traces

    # ── 判断用例类型 ──
    def _is_intent_only(case: dict) -> bool:
        """判断是否为纯意图分类用例（无 tools/answer）"""
        has_tools = bool(case.get("expected_tools"))
        has_answer = bool(case.get("expected_answer"))
        return not has_tools and not has_answer

    # ── trace_provider 回调 ──
    async def trace_provider(case: dict) -> list[dict]:
        case_id = case.get("id", "?")

        if _is_intent_only(case):
            return await _run_intent_only(case)

        if run_full_workflow:
            return await _run_full_workflow(case)

        # 全流程用例但不跑 workflow → 返回空，跳过此 case
        logger.debug("跳过全流程 case {}（run_full_workflow=False）", case_id)
        return []

    return trace_provider
