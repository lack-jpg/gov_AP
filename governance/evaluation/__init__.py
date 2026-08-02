"""
governance.evaluation - Auto-evaluation engine: RAG metrics, Agent metrics, benchmark runner

Author: le
Date: 2026/7/29
Version: 0.2
Task: Evaluation package initialization — exports all evaluation components
"""
from __future__ import annotations

from governance.evaluation.benchmark import (
    BenchmarkResult,
    BenchmarkRunner,
    GoldenDataset,
    run_default_benchmark,
)
from governance.evaluation.evaluator import (
    EvalCaseRecord,
    EvaluationEngine,
    EvaluationResult,
    evaluate_from_json_file,
)
from governance.evaluation.metrics import (
    AgentMetricResult,
    EvalReport,
    RAGMetricResult,
    compute_agent_metrics,
    compute_answer_relevance,
    compute_avg_latency_ms,
    compute_avg_step_count,
    compute_context_recall,
    compute_faithfulness,
    compute_intent_accuracy,
    compute_intent_accuracy_batch,
    compute_overall_score,
    compute_rag_metrics,
    compute_task_success_rate,
    compute_tool_accuracy,
    compute_tool_accuracy_from_mcp_history,
)
from governance.evaluation.runner import (
    EvalRunner,
    ReportWriter,
    RunnerConfig,
    RunnerResult,
    build_cli_parser,
    cli_main,
    main,
)

__all__ = [
    # ── Metrics ──
    "RAGMetricResult",
    "AgentMetricResult",
    "EvalReport",
    "compute_faithfulness",
    "compute_answer_relevance",
    "compute_context_recall",
    "compute_rag_metrics",
    "compute_task_success_rate",
    "compute_tool_accuracy",
    "compute_tool_accuracy_from_mcp_history",
    "compute_avg_latency_ms",
    "compute_avg_step_count",
    "compute_agent_metrics",
    "compute_intent_accuracy",
    "compute_intent_accuracy_batch",
    "compute_overall_score",
    # ── Evaluator ──
    "EvaluationEngine",
    "EvaluationResult",
    "EvalCaseRecord",
    "evaluate_from_json_file",
    # ── Benchmark ──
    "BenchmarkResult",
    "BenchmarkRunner",
    "GoldenDataset",
    "run_default_benchmark",
    # ── Runner ──
    "RunnerConfig",
    "RunnerResult",
    "EvalRunner",
    "ReportWriter",
    "build_cli_parser",
    "main",
    "cli_main",
]
