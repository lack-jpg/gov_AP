"""
test_evaluation_metrics - 评测系统指标计算单元测试（PLAN #10）

覆盖 governance/evaluation/metrics.py 的核心纯函数：
RAG 指标（faithfulness/relevance/recall）+ Agent 指标 + 意图准确率 + 综合评分
"""
from __future__ import annotations

import pytest

from governance.evaluation.metrics import (
    RAGMetricResult,
    AgentMetricResult,
    EvalReport,
    compute_answer_relevance,
    compute_agent_metrics,
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


# ============================================================
# RAG 指标
# ============================================================


class TestFaithfulness:
    def test_empty_contexts_zero(self):
        assert compute_faithfulness("回答内容", []) == 0.0

    def test_empty_answer_zero(self):
        assert compute_faithfulness("", ["上下文"]) == 0.0

    def test_none_contexts_graceful(self):
        assert compute_faithfulness("回答", None) == 0.0  # type: ignore

    def test_high_overlap_high_score(self):
        ctx = ["营业执照是市场主体登记管理部门依法登记注册，确认市场主体资格的法律文件。开公司必须办理营业执照。"]
        score = compute_faithfulness("开公司必须办理营业执照，营业执照是市场主体登记的法律文件。", ctx)
        assert 0.0 < score <= 1.0

    def test_low_overlap_low_score(self):
        ctx = ["营业执照是市场主体登记管理部门依法登记注册的文件。"]
        score = compute_faithfulness("开公司需要食品经营许可证", ctx)
        assert score < 1.0


class TestAnswerRelevance:
    def test_empty_answer_zero(self):
        assert compute_answer_relevance("问题", "") == 0.0

    def test_empty_question_half(self):
        assert compute_answer_relevance("", "一些回答") == 0.5

    def test_refusal_zero(self):
        assert compute_answer_relevance("如何办理营业执照？", "抱歉，我无法回答这个问题。") == 0.0

    def test_relevant_answer_positive(self):
        score = compute_answer_relevance(
            "如何办理营业执照？",
            "办理营业执照需要到当地市场监督管理局提交申请，提供身份证、经营场所证明等材料。",
        )
        assert score > 0.0


class TestContextRecall:
    def test_empty_contexts_zero(self):
        assert compute_context_recall([], "参考答案") == 0.0

    def test_empty_reference_one(self):
        assert compute_context_recall(["上下文"], "") == 1.0

    def test_match_positive(self):
        score = compute_context_recall(
            ["营业执照是市场主体登记管理部门依法登记注册的文件。"],
            "营业执照是登记注册的文件。",
        )
        assert score > 0.0


class TestComputeRagMetrics:
    def test_all_metrics_in_range(self):
        r = compute_rag_metrics(
            question="如何办理营业执照？",
            answer="办理营业执照需要到市场监督管理局提交申请。",
            contexts=["营业执照是市场主体登记管理部门依法登记注册的文件。"],
            reference_answer="营业执照需要在市场监督管理局办理。",
        )
        assert isinstance(r, RAGMetricResult)
        assert 0.0 <= r.faithfulness <= 1.0
        assert 0.0 <= r.answer_relevance <= 1.0
        assert 0.0 <= r.context_recall <= 1.0
        assert "question" in r.details


# ============================================================
# Agent 指标
# ============================================================


class TestTaskSuccessRate:
    def test_basic(self):
        traces = [
            {"status": "success"},
            {"status": "success"},
            {"status": "failed"},
            {"status": "completed"},
        ]
        assert compute_task_success_rate(traces) == 0.75

    def test_empty(self):
        assert compute_task_success_rate([]) == 0.0


class TestToolAccuracy:
    def test_partial(self):
        traces = [{"tool_name": "search_policy"}, {"tool_name": "get_policy_detail"}]
        assert compute_tool_accuracy(traces, ["search_policy", "get_policy_detail", "create_case"]) == pytest.approx(2 / 3)

    def test_no_expected_returns_one(self):
        assert compute_tool_accuracy([{"tool_name": "a"}], None) == 1.0

    def test_empty_traces(self):
        assert compute_tool_accuracy([], ["search_policy"]) == 0.0

    def test_tool_calls_list(self):
        traces = [{"tool_calls": [{"name": "search_policy"}, {"name": "extract_entity"}]}]
        assert compute_tool_accuracy(traces, ["search_policy", "extract_entity"]) == 1.0

    def test_from_mcp_history(self):
        mcp = [{"tool_name": "search_policy"}, {"name": "get_policy_detail"}]
        assert compute_tool_accuracy_from_mcp_history(mcp, ["search_policy", "get_policy_detail"]) == 1.0


class TestLatencySteps:
    def test_avg_latency(self):
        traces = [{"latency_ms": 100}, {"latency_ms": 200}, {"latency_ms": 300}]
        assert compute_avg_latency_ms(traces) == 200.0

    def test_avg_latency_empty(self):
        assert compute_avg_latency_ms([]) == 0.0

    def test_avg_steps(self):
        assert compute_avg_step_count([{"step_count": 3}, {"step_count": 5}]) == 4.0

    def test_avg_steps_from_mcp(self):
        traces = [{"mcp_history": [{"t": "a"}, {"t": "b"}]}, {"mcp_history": [{"t": "c"}]}]
        assert compute_avg_step_count(traces) == 1.5


class TestComputeAgentMetrics:
    def test_basic(self):
        traces = [
            {"status": "success", "agent_name": "policy", "latency_ms": 100, "tool_name": "search_policy"},
            {"status": "success", "agent_name": "material", "latency_ms": 200, "tool_name": "extract_entity"},
            {"status": "failed", "agent_name": "workflow", "latency_ms": 300},
        ]
        r = compute_agent_metrics(traces, expected_tools=["search_policy", "extract_entity"])
        assert isinstance(r, AgentMetricResult)
        assert r.total_cases == 3
        assert r.passed_cases == 2
        assert r.task_success_rate == pytest.approx(2 / 3)
        assert r.avg_latency_ms == pytest.approx(200.0)
        assert "per_agent" in r.details


# ============================================================
# 意图准确率
# ============================================================


class TestIntentAccuracy:
    def test_match(self):
        assert compute_intent_accuracy("business_license", "business_license") == 1.0

    def test_mismatch(self):
        assert compute_intent_accuracy("policy_query", "business_license") == 0.0

    def test_empty_expected(self):
        assert compute_intent_accuracy("business_license", "") == 1.0

    def test_case_insensitive(self):
        assert compute_intent_accuracy("Business_License", "business_license") == 1.0

    def test_batch(self):
        assert compute_intent_accuracy_batch(
            ["business_license", "policy_query", "material_check"],
            ["business_license", "policy_query", "workflow_create"],
        ) == pytest.approx(2 / 3)

    def test_batch_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_intent_accuracy_batch(["a"], ["a", "b"])


# ============================================================
# 综合评分
# ============================================================


class TestOverallScore:
    def test_score_in_range(self):
        rag = RAGMetricResult(faithfulness=0.8, answer_relevance=0.7, context_recall=0.6)
        agent = AgentMetricResult(task_success_rate=0.9, tool_accuracy=0.8, avg_latency_ms=1000, avg_step_count=3)
        score = compute_overall_score(rag, agent, intent_accuracy=0.9)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # 高质量结果综合分应偏高

    def test_zero_result(self):
        rag = RAGMetricResult()
        agent = AgentMetricResult()
        score = compute_overall_score(rag, agent, intent_accuracy=1.0)
        assert 0.0 <= score <= 1.0

    def test_eval_report_to_dict(self):
        report = EvalReport(
            rag=RAGMetricResult(faithfulness=0.9),
            agent=AgentMetricResult(task_success_rate=0.8),
            intent_accuracy=0.9,
            overall_score=0.85,
        )
        d = report.to_dict()
        assert d["overall_score"] == 0.85
        assert "rag" in d and "agent" in d and "intent_accuracy" in d
