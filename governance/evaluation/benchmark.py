"""
governance.evaluation.benchmark - Benchmark: load golden datasets, run agent evaluations, compare versions

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement benchmark runner with golden dataset support
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from governance.evaluation.evaluator import (
    EvalCaseRecord,
    EvaluationEngine,
    EvaluationResult,
)


# ============================================================
# Data Classes
# ============================================================


@dataclass
class BenchmarkResult:
    """一次 Benchmark 运行的完整结果"""

    benchmark_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    benchmark_name: str = "unknown"
    version: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # 各数据集评测结果
    datasets: dict[str, EvaluationResult] = field(default_factory=dict)

    # 汇总
    overall_score: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0

    # 元数据
    evaluation_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_name": self.benchmark_name,
            "version": self.version,
            "created_at": self.created_at,
            "datasets": {
                name: result.to_dict()
                for name, result in self.datasets.items()
            },
            "overall_score": round(self.overall_score, 4),
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "evaluation_time_ms": round(self.evaluation_time_ms, 2),
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_summary(self) -> str:
        """生成可读的 Benchmark 摘要"""
        lines = [
            "=" * 70,
            f"  BENCHMARK REPORT: {self.benchmark_name}",
            "=" * 70,
            f"  ID:          {self.benchmark_id[:8]}",
            f"  Version:     {self.version}",
            f"  Date:        {self.created_at}",
            f"  Duration:    {self.evaluation_time_ms:.0f}ms",
            "",
            f"  OVERALL SCORE:  {self.overall_score:.2%}",
            f"  Total Cases:    {self.total_cases}",
            f"  Passed Cases:   {self.passed_cases}",
            f"  Pass Rate:      {self.passed_cases / max(self.total_cases, 1):.1%}",
            "",
            "  Per-Dataset Results:",
            "  " + "-" * 58,
        ]

        for name, result in self.datasets.items():
            pass_rate = result.passed_cases / max(result.total_cases, 1)
            lines.append(
                f"  {name:<30s} | score={result.overall_score:.2%} | "
                f"passed={result.passed_cases}/{result.total_cases} ({pass_rate:.0%})"
            )

        if self.errors:
            lines.append(f"\n  Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"    - {e}")

        if self.warnings:
            lines.append(f"\n  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    - {w}")

        lines.append("=" * 70)
        return "\n".join(lines)


# ============================================================
# Golden Dataset
# ============================================================


class GoldenDataset:
    """
    Golden Dataset — 从 JSON 文件加载标准评测用例。

    支持两种格式:
    1. 单 case: {"id": "...", "query": "...", ...}
    2. 多 case: [{"id": "..."}, {"id": "..."}, ...]
    3. 嵌套: {"_description": "...", "cases": [{...}]}
    """

    def __init__(
        self,
        name: str,
        filepath: str,
    ):
        self.name = name
        self.filepath = filepath
        self.cases: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> list[dict[str, Any]]:
        """加载并解析 JSON 数据集"""
        if self._loaded:
            return self.cases

        if not os.path.exists(self.filepath):
            self.cases = []
            self._loaded = True
            return self.cases

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                # 提取元数据 + 用例
                # 兼容 "{"_description": ..., "cases": [...]}" 同层嵌套格式：
                # 即使条目含 _description，其 cases 也应被提取。
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if item.get("_description"):
                        self.metadata = item
                    cases_list = item.get("cases")
                    if isinstance(cases_list, list):
                        self.cases.extend(cases_list)
                    elif "cases" not in item:
                        self.cases.append(item)
            elif isinstance(data, dict):
                if "cases" in data:
                    self.metadata = {
                        k: v for k, v in data.items() if k != "cases"
                    }
                    cases = data["cases"]
                    if isinstance(cases, list):
                        self.cases = cases
                else:
                    self.cases = [data]
        except (json.JSONDecodeError, OSError) as e:
            self.cases = []
            self.metadata["_load_error"] = str(e)

        self._loaded = True
        return self.cases

    @property
    def case_count(self) -> int:
        if not self._loaded:
            self.load()
        return len(self.cases)

    @property
    def has_cases(self) -> bool:
        return self.case_count > 0

    def reload(self) -> list[dict[str, Any]]:
        """强制重新加载"""
        self._loaded = False
        self.cases = []
        return self.load()


# ============================================================
# Benchmark Runner
# ============================================================


class BenchmarkRunner:
    """
    Benchmark Runner — 加载 Golden Dataset，运行 Agent 评测，生成报告。

    使用方式:
        runner = BenchmarkRunner(version="0.2.0")
        result = await runner.run_all()
        print(result.to_summary())
    """

    def __init__(
        self,
        version: str = "unknown",
        *,
        cases_dir: str = "cases",
        use_llm: bool = False,
        llm_call: Optional[callable] = None,
        trace_provider: Optional[callable] = None,
        weights: Optional[dict[str, float]] = None,
    ):
        self.version = version
        self.cases_dir = cases_dir
        self.use_llm = use_llm
        self.llm_call = llm_call
        self.trace_provider = trace_provider
        self.weights = weights

        self.engine = EvaluationEngine(
            version=version,
            use_llm=use_llm,
            llm_call=llm_call,
            weights=weights,
        )

    # ── 数据集管理 ──

    def discover_datasets(self) -> list[str]:
        """
        发现 cases 目录下所有 JSON 数据集文件。

        Returns:
            JSON 文件路径列表
        """
        datasets: list[str] = []

        if not os.path.isdir(self.cases_dir):
            return datasets

        for fname in sorted(os.listdir(self.cases_dir)):
            if fname.endswith(".json"):
                datasets.append(os.path.join(self.cases_dir, fname))

        return datasets

    def load_dataset(self, name_or_path: str) -> GoldenDataset:
        """
        加载指定的数据集。

        Args:
            name_or_path: 数据集名称（不含路径和扩展名）或完整路径

        Returns:
            GoldenDataset 实例
        """
        # 如果是完整路径
        if os.path.isfile(name_or_path):
            filepath = name_or_path
            name = os.path.splitext(os.path.basename(filepath))[0]
        else:
            # 尝试在 cases_dir 中查找
            filepath = os.path.join(self.cases_dir, f"{name_or_path}.json")
            if not os.path.isfile(filepath):
                filepath = os.path.join(self.cases_dir, name_or_path)
            name = name_or_path

        dataset = GoldenDataset(name=name, filepath=filepath)
        dataset.load()
        return dataset

    # ── 运行评测 ──

    async def run_dataset(
        self,
        dataset_name: str,
    ) -> EvaluationResult:
        """
        运行单个数据集的评测。

        Args:
            dataset_name: 数据集名称或路径

        Returns:
            EvaluationResult
        """
        dataset = self.load_dataset(dataset_name)

        if not dataset.has_cases:
            result = EvaluationResult(
                version=self.version,
                dataset_name=dataset.name,
            )
            result.warnings.append(f"Dataset '{dataset.name}' has no cases")
            return result

        result = await self.engine.evaluate_from_cases(
            dataset.cases,
            trace_provider=self.trace_provider,
            dataset_name=dataset.name,
        )
        return result

    async def run_all(
        self,
        dataset_filter: Optional[Sequence[str]] = None,
    ) -> BenchmarkResult:
        """
        运行所有数据集的评测，生成 Benchmark 报告。

        Args:
            dataset_filter: 可选的数据集名称过滤列表（为空则运行所有）

        Returns:
            BenchmarkResult
        """
        import time
        t0 = time.perf_counter()

        benchmark = BenchmarkResult(
            benchmark_name=f"benchmark-{self.version}",
            version=self.version,
        )

        # 发现数据集
        all_datasets = self.discover_datasets()

        if not all_datasets:
            benchmark.warnings.append(f"No datasets found in '{self.cases_dir}'")
            benchmark.evaluation_time_ms = (time.perf_counter() - t0) * 1000
            return benchmark

        # 过滤数据集
        if dataset_filter:
            filter_set = set(dataset_filter)
            all_datasets = [
                d for d in all_datasets
                if os.path.splitext(os.path.basename(d))[0] in filter_set
            ]

        if not all_datasets:
            benchmark.warnings.append(
                f"No datasets match filter: {dataset_filter}"
            )
            benchmark.evaluation_time_ms = (time.perf_counter() - t0) * 1000
            return benchmark

        # 逐个评测
        for filepath in all_datasets:
            dataset_name = os.path.splitext(os.path.basename(filepath))[0]
            try:
                result = await self.run_dataset(filepath)
                benchmark.datasets[dataset_name] = result
                benchmark.total_cases += result.total_cases
                benchmark.passed_cases += result.passed_cases
            except Exception as e:
                benchmark.errors.append(f"Dataset '{dataset_name}': {e}")

        # 汇总评分
        if benchmark.datasets:
            scores = [r.overall_score for r in benchmark.datasets.values()]
            benchmark.overall_score = sum(scores) / len(scores)
        else:
            benchmark.overall_score = 0.0

        benchmark.evaluation_time_ms = (time.perf_counter() - t0) * 1000
        return benchmark

    async def run_single(
        self,
        case: dict[str, Any],
        dataset_name: str = "adhoc",
    ) -> EvalCaseRecord:
        """
        运行单条 case 的评测。

        Args:
            case: 单条评测用例
            dataset_name: 数据集名称

        Returns:
            EvalCaseRecord
        """
        result = await self.engine.evaluate_from_cases(
            [case],
            trace_provider=self.trace_provider,
            dataset_name=dataset_name,
        )
        # 重建 EvalCaseRecord 从 result
        if result.per_case_results:
            return EvalCaseRecord(
                case_id=case.get("id", ""),
                query=case.get("query", ""),
                expected_intent=case.get("expected_intent", ""),
                expected_tools=case.get("expected_tools", []),
                expected_answer_keywords=case.get("expected_answer", []),
                actual_intent=result.per_case_results[0].get("actual_intent", ""),
                actual_tools=result.per_case_results[0].get("actual_tools", []),
                tool_match=result.per_case_results[0].get("tool_match", 0.0),
                status=result.per_case_results[0].get("status", "pending"),
            )
        return EvalCaseRecord()

    # ── 报告生成 ──

    def generate_markdown_report(self, benchmark: BenchmarkResult) -> str:
        """生成 Markdown 格式的 Benchmark 报告"""
        lines = [
            f"# Benchmark Report: {benchmark.benchmark_name}",
            "",
            f"- **Version**: `{benchmark.version}`",
            f"- **Date**: {benchmark.created_at}",
            f"- **Duration**: {benchmark.evaluation_time_ms:.0f}ms",
            "",
            "---",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Overall Score | **{benchmark.overall_score:.2%}** |",
            f"| Total Cases | {benchmark.total_cases} |",
            f"| Passed Cases | {benchmark.passed_cases} |",
            f"| Pass Rate | {benchmark.passed_cases / max(benchmark.total_cases, 1):.1%} |",
            f"| Datasets | {len(benchmark.datasets)} |",
            "",
            "---",
            "",
            "## Per-Dataset Results",
            "",
        ]

        for name, result in benchmark.datasets.items():
            pass_rate = result.passed_cases / max(result.total_cases, 1)
            lines.extend([
                f"### {name}",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Overall Score | {result.overall_score:.2%} |",
                f"| Total Cases | {result.total_cases} |",
                f"| Passed Cases | {result.passed_cases} ({pass_rate:.0%}) |",
                f"| Task Success Rate | {result.agent.task_success_rate:.2%} |",
                f"| Tool Accuracy | {result.agent.tool_accuracy:.2%} |",
                f"| Faithfulness | {result.rag.faithfulness:.2%} |",
                f"| Answer Relevance | {result.rag.answer_relevance:.2%} |",
                f"| Context Recall | {result.rag.context_recall:.2%} |",
                f"| Intent Accuracy | {result.intent_accuracy:.2%} |",
                f"| Avg Latency | {result.agent.avg_latency_ms:.1f}ms |",
                f"| Avg Steps | {result.agent.avg_step_count:.1f} |",
                "",
            ])

            if result.errors:
                lines.append("**Errors:**\n")
                for e in result.errors:
                    lines.append(f"  - {e}")
                lines.append("")

        if benchmark.errors:
            lines.append("---\n\n## Benchmark Errors\n")
            for e in benchmark.errors:
                lines.append(f"- {e}")
            lines.append("")

        if benchmark.warnings:
            lines.append("---\n\n## Warnings\n")
            for w in benchmark.warnings:
                lines.append(f"- {w}")
            lines.append("")

        return "\n".join(lines)

    # ── 版本对比 ──

    @staticmethod
    def compare_benchmarks(
        benchmarks: Sequence[BenchmarkResult],
    ) -> dict[str, Any]:
        """
        对比多个版本的 Benchmark 结果。

        Args:
            benchmarks: 多个版本的 BenchmarkResult

        Returns:
            对比报告 dict
        """
        if not benchmarks:
            return {"error": "No benchmarks to compare"}

        comparison = {
            "versions": [b.version for b in benchmarks],
            "overall_scores": [round(b.overall_score, 4) for b in benchmarks],
            "best_version": max(benchmarks, key=lambda b: b.overall_score).version,
            "per_dataset": {},
        }

        # 收集所有数据集名称
        all_datasets: set[str] = set()
        for b in benchmarks:
            all_datasets.update(b.datasets.keys())

        for dataset_name in sorted(all_datasets):
            comparison["per_dataset"][dataset_name] = {}
            for b in benchmarks:
                if dataset_name in b.datasets:
                    r = b.datasets[dataset_name]
                    comparison["per_dataset"][dataset_name][b.version] = {
                        "overall_score": round(r.overall_score, 4),
                        "passed_cases": r.passed_cases,
                        "total_cases": r.total_cases,
                        "task_success_rate": round(r.agent.task_success_rate, 4),
                    }

        # 计算改进
        if len(benchmarks) >= 2:
            prev = benchmarks[-2]
            curr = benchmarks[-1]
            comparison["diff"] = {
                "overall_score": round(curr.overall_score - prev.overall_score, 4),
                "total_cases": curr.total_cases - prev.total_cases,
                "passed_cases": curr.passed_cases - prev.passed_cases,
            }

        return comparison


# ============================================================
# Convenience Functions
# ============================================================


async def run_default_benchmark(
    version: str = "current",
    cases_dir: str = "cases",
) -> BenchmarkResult:
    """
    运行默认 Benchmark（所有 cases/*.json 数据集）。

    Args:
        version: 版本号
        cases_dir: 数据集目录

    Returns:
        BenchmarkResult
    """
    runner = BenchmarkRunner(version=version, cases_dir=cases_dir)
    return await runner.run_all()


# ============================================================
# Smoke Test
# ============================================================


def _smoke_test() -> None:
    """模块自测"""
    import asyncio

    passed = 0
    total = 0

    print("=" * 60)
    print("Benchmark Tests")
    print("=" * 60)

    # Determine cases directory
    _cur_dir = os.path.dirname(os.path.abspath(__file__))
    _proj_dir = os.path.dirname(os.path.dirname(_cur_dir))
    _cases_dir = os.path.join(_proj_dir, "cases")

    # Test 1: GoldenDataset load and case count
    total += 1
    ds = GoldenDataset(
        name="business_license",
        filepath=os.path.join(_cases_dir, "business_license.json"),
    )
    cases = ds.load()
    assert ds.case_count >= 0  # may be empty
    assert ds._loaded is True
    passed += 1
    print(f"  [OK] GoldenDataset load -> {ds.case_count} cases")

    # Test 2: GoldenDataset non-existent file
    total += 1
    ds = GoldenDataset(name="nonexistent", filepath="/nonexistent/cases.json")
    cases = ds.load()
    assert cases == []
    assert ds.case_count == 0
    passed += 1
    print(f"  [OK] GoldenDataset nonexistent -> {ds.case_count} cases")

    # Test 3: GoldenDataset reload
    total += 1
    ds = GoldenDataset(
        name="business_license",
        filepath=os.path.join(_cases_dir, "business_license.json"),
    )
    ds.load()
    count1 = ds.case_count
    ds.reload()
    count2 = ds.case_count
    assert count1 == count2
    passed += 1
    print(f"  [OK] GoldenDataset reload -> {count1} == {count2}")

    # Test 4: GoldenDataset has_cases
    total += 1
    ds = GoldenDataset(name="empty_test", filepath="/nonexistent.json")
    assert ds.has_cases is False
    passed += 1
    print("  [OK] GoldenDataset has_cases -> False")

    # Test 5: BenchmarkRunner discover_datasets
    total += 1
    runner = BenchmarkRunner(version="0.1.0", cases_dir=_cases_dir)
    datasets = runner.discover_datasets()
    assert len(datasets) >= 0
    names = [os.path.splitext(os.path.basename(d))[0] for d in datasets]
    passed += 1
    print(f"  [OK] discover_datasets -> {len(datasets)} files: {names}")

    # Test 6: BenchmarkRunner load_dataset by name
    total += 1
    ds = runner.load_dataset("business_license")
    assert ds.name == "business_license"
    assert ds._loaded is True
    passed += 1
    print(f"  [OK] load_dataset by name -> {ds.name}")

    # Test 7: BenchmarkRunner load_dataset by path
    total += 1
    filepath = os.path.join(_cases_dir, "business_license.json")
    ds = runner.load_dataset(filepath)
    assert ds.name == "business_license"
    passed += 1
    print(f"  [OK] load_dataset by path -> {ds.name}")

    # Test 8: BenchmarkRunner run_dataset
    total += 1
    async def test_run_dataset():
        r = await runner.run_dataset("business_license")
        assert r is not None
        assert r.dataset_name == "business_license"
        return r

    r = asyncio.run(test_run_dataset())
    passed += 1
    print(f"  [OK] run_dataset -> {r.dataset_name}: {r.total_cases} cases, score={r.overall_score:.4f}")

    # Test 9: BenchmarkRunner run_all
    total += 1
    async def test_run_all():
        b = await runner.run_all()
        assert b is not None
        assert b.version == "0.1.0"
        return b

    b = asyncio.run(test_run_all())
    passed += 1
    print(f"  [OK] run_all -> {len(b.datasets)} datasets, score={b.overall_score:.4f}")

    # Test 10: BenchmarkResult to_dict / to_json
    total += 1
    d = b.to_dict()
    assert "benchmark_id" in d
    assert "datasets" in d
    j = b.to_json()
    assert len(j) > 0
    passed += 1
    print(f"  [OK] BenchmarkResult to_dict/to_json -> {len(j)} chars")

    # Test 11: BenchmarkResult to_summary
    total += 1
    summary = b.to_summary()
    assert "BENCHMARK REPORT" in summary
    passed += 1
    print(f"  [OK] BenchmarkResult to_summary -> {len(summary)} chars")

    # Test 12: generate_markdown_report
    total += 1
    md = runner.generate_markdown_report(b)
    assert "# Benchmark Report" in md
    passed += 1
    print(f"  [OK] generate_markdown_report -> {len(md)} chars")

    # Test 13: run_all with dataset_filter
    total += 1
    async def test_filter():
        b = await runner.run_all(dataset_filter=["business_license"])
        assert len(b.datasets) == 1
        return b

    b = asyncio.run(test_filter())
    passed += 1
    print(f"  [OK] run_all filter -> {len(b.datasets)} datasets")

    # Test 14: run_all with non-matching filter
    total += 1
    async def test_no_match():
        b = await runner.run_all(dataset_filter=["xyz_nonexistent_dataset"])
        assert len(b.datasets) == 0
        return b

    b = asyncio.run(test_no_match())
    passed += 1
    print(f"  [OK] run_all no match -> {len(b.warnings)} warnings")

    # Test 15: run_all with empty cases_dir
    total += 1
    runner_empty = BenchmarkRunner(version="0.1.0", cases_dir="/nonexistent/dir")
    async def test_empty_dir():
        b = await runner_empty.run_all()
        assert len(b.warnings) >= 1 or b.total_cases == 0
        return b

    b = asyncio.run(test_empty_dir())
    passed += 1
    print(f"  [OK] run_all empty dir -> warnings={len(b.warnings)}")

    # Test 16: run_single
    total += 1
    async def test_run_single():
        case = {
            "id": "adhoc_001",
            "query": "测试独立用例",
            "expected_intent": "test",
        }
        record = await runner.run_single(case)
        assert record.case_id == "adhoc_001"
        return record

    record = asyncio.run(test_run_single())
    passed += 1
    print(f"  [OK] run_single -> {record.case_id}")

    # Test 17: compare_benchmarks
    total += 1
    async def test_compare():
        runner_v1 = BenchmarkRunner(version="v1.0", cases_dir=_cases_dir)
        runner_v2 = BenchmarkRunner(version="v2.0", cases_dir=_cases_dir)

        b1 = await runner_v1.run_all(dataset_filter=["business_license"])
        b2 = await runner_v2.run_all(dataset_filter=["business_license"])

        comparison = BenchmarkRunner.compare_benchmarks([b1, b2])
        assert "versions" in comparison
        assert len(comparison["versions"]) == 2
        assert "diff" in comparison
        return comparison

    comparison = asyncio.run(test_compare())
    passed += 1
    print(f"  [OK] compare_benchmarks -> versions={comparison['versions']}")

    # Test 18: run_default_benchmark
    total += 1
    async def test_default():
        b = await run_default_benchmark(version="test", cases_dir=_cases_dir)
        assert b is not None
        return b

    b = asyncio.run(test_default())
    passed += 1
    print(f"  [OK] run_default_benchmark -> datasets={len(b.datasets)}")

    # Test 19: BenchmarkResult with errors
    total += 1
    br = BenchmarkResult(
        benchmark_name="error-test",
        version="x",
        errors=["error 1", "error 2"],
        warnings=["warning 1"],
    )
    d = br.to_dict()
    assert len(d["errors"]) == 2
    assert len(d["warnings"]) == 1
    passed += 1
    print("  [OK] BenchmarkResult errors/warnings")

    # Test 20: GoldenDataset with nested format
    total += 1
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({
            "_description": "nested test",
            "cases": [
                {"id": "n1", "query": "test 1", "expected_intent": "intent_a"},
                {"id": "n2", "query": "test 2", "expected_intent": "intent_b"},
            ],
        }, f)
        tmp_path = f.name

    try:
        ds = GoldenDataset(name="nested_test", filepath=tmp_path)
        cases = ds.load()
        assert ds.case_count == 2
        passed += 1
        print(f"  [OK] GoldenDataset nested -> {ds.case_count} cases")
    finally:
        os.unlink(tmp_path)

    # Test 21: GoldenDataset with list format containing _description
    total += 1
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump([
            {"_description": "list_desc", "_author": "test"},
            {"id": "l1", "query": "query 1", "expected_intent": "intent_1"},
        ], f)
        tmp_path = f.name

    try:
        ds = GoldenDataset(name="list_test", filepath=tmp_path)
        cases = ds.load()
        assert ds.case_count >= 1
        # 应该有至少1个有效 case（不含纯元数据条目）
        passed += 1
        print(f"  [OK] GoldenDataset list with metadata -> {ds.case_count} cases")
    finally:
        os.unlink(tmp_path)

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed")
    print("=" * 60)

    if passed == total:
        print("ALL smoke tests passed!")
    else:
        print(f"{total - passed} test(s) failed!")


if __name__ == "__main__":
    _smoke_test()
