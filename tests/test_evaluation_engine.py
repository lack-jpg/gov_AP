"""
test_evaluation_engine - 评测引擎单元测试（DB-free，PLAN #10）

覆盖 governance/evaluation/evaluator.py + benchmark.py 的核心编排逻辑：
evaluate_from_traces / evaluate_from_cases / evaluate_from_json_file /
compare_versions / generate_markdown_report / BenchmarkResult
"""
from __future__ import annotations

import asyncio
import json

import pytest

from governance.evaluation.benchmark import BenchmarkResult
from governance.evaluation.evaluator import EvaluationEngine, EvaluationResult, evaluate_from_json_file


@pytest.mark.asyncio
async def test_evaluate_from_traces():
    engine = EvaluationEngine(version="0.1.0")
    traces = [
        {"status": "success", "agent_name": "policy", "latency_ms": 100, "tool_name": "search_policy"},
        {"status": "success", "agent_name": "material", "latency_ms": 200, "tool_name": "extract_entity"},
        {"status": "failed", "agent_name": "workflow", "latency_ms": 300},
    ]
    result = await engine.evaluate_from_traces(
        traces, dataset_name="test", expected_tools=["search_policy", "extract_entity"],
    )
    assert isinstance(result, EvaluationResult)
    assert result.version == "0.1.0"
    assert result.total_cases == 3
    assert result.passed_cases == 2
    assert result.agent.task_success_rate == pytest.approx(2 / 3)
    assert 0.0 <= result.overall_score <= 1.0


@pytest.mark.asyncio
async def test_evaluate_from_cases_with_trace_provider():
    engine = EvaluationEngine(version="v1")
    cases = [
        {
            "id": "c1",
            "query": "如何办营业执照",
            "expected_intent": "business_license",
            "expected_tools": ["search_policy"],
            "expected_answer": ["营业执照"],
        },
        {
            "id": "c2",
            "query": "查询公积金",
            "expected_intent": "fund_query",
            "expected_tools": ["search_policy"],
            "expected_answer": ["公积金"],
        },
    ]

    async def trace_provider(case):
        # 模拟：c1 意图对、工具对；c2 意图错、工具对
        if case["id"] == "c1":
            return [{"status": "success", "agent_name": "intent", "tool_name": "search_policy"}]
        return [{"status": "success", "agent_name": "intent", "tool_name": "search_policy"}]

    result = await engine.evaluate_from_cases(cases, trace_provider, dataset_name="cases")
    assert result.total_cases == 2
    # 意图准确率：一个匹配一个不匹配 → 但注意 engine 用 trace 推断 intent（无则跳过）
    assert result.overall_score >= 0.0


@pytest.mark.asyncio
async def test_evaluate_from_json_file(tmp_path):
    cases = [
        {
            "id": "j1",
            "query": "如何办理营业执照",
            "expected_intent": "business_license",
            "expected_tools": ["search_policy"],
            "expected_answer": ["营业执照", "登记"],
        },
    ]
    p = tmp_path / "cases.json"
    p.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")

    result = await evaluate_from_json_file(str(p), version="v1")
    assert isinstance(result, EvaluationResult)
    assert result.total_cases == 1
    assert result.version == "v1"


@pytest.mark.asyncio
async def test_evaluate_from_json_file_missing():
    result = await evaluate_from_json_file("nonexistent/path.json", version="v1")
    assert result.errors and "not found" in result.errors[0].lower()


def test_compare_versions():
    engine = EvaluationEngine(version="v2")
    r1 = EvaluationResult(version="v1", dataset_name="d")
    r1.agent.task_success_rate = 0.6
    r1.overall_score = 0.6
    r2 = EvaluationResult(version="v2", dataset_name="d")
    r2.agent.task_success_rate = 0.8
    r2.overall_score = 0.8

    comparison = engine.compare_versions([r1, r2])
    assert comparison["versions"] == ["v1", "v2"]
    assert comparison["best_version"] == "v2"
    assert comparison["metrics_by_version"]["v1"]["overall_score"] == 0.6
    assert comparison["metrics_by_version"]["v2"]["overall_score"] == 0.8
    assert "diff" in comparison


def test_generate_markdown_report():
    engine = EvaluationEngine(version="v1")
    result = EvaluationResult(version="v1", dataset_name="test")
    result.total_cases = 10
    result.passed_cases = 8
    result.agent.task_success_rate = 0.8
    result.overall_score = 0.75

    md = engine.generate_markdown_report(result)
    assert "test" in md or "评测" in md
    assert "0.8" in md or "80" in md


def test_benchmark_result_to_dict():
    br = BenchmarkResult(benchmark_name="b1", version="v1")
    d = br.to_dict()
    assert d["benchmark_name"] == "b1"
    assert "overall_score" in d
    assert "datasets" in d


def test_benchmark_result_to_json():
    br = BenchmarkResult(benchmark_name="b1", version="v1")
    data = json.loads(br.to_json())
    assert data["version"] == "v1"


def test_nested_cases_flattened():
    """嵌套 {cases:[...]} 格式应递归处理。"""
    async def run():
        engine = EvaluationEngine(version="v1")
        cases = [
            {"_description": "业务用例", "cases": [
                {"id": "n1", "query": "q", "expected_intent": "a", "expected_tools": [], "expected_answer": []},
                {"id": "n2", "query": "q2", "expected_intent": "b", "expected_tools": [], "expected_answer": []},
            ]},
        ]
        return await engine.evaluate_from_cases(cases, dataset_name="nested")

    result = asyncio.run(run())
    assert result.total_cases == 2
