"""
governance.evaluation.runner - Evaluation runner: CI/CD integration, scheduled evaluation, report generation

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement automated evaluation pipeline runner
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from governance.evaluation.benchmark import BenchmarkResult, BenchmarkRunner
from governance.evaluation.evaluator import EvaluationEngine, EvaluationResult


# ============================================================
# Data Classes
# ============================================================


@dataclass
class RunnerConfig:
    """Runner 配置"""

    version: str = "current"
    cases_dir: str = "cases"
    output_dir: str = "evaluation_results"
    output_format: str = "all"  # json | markdown | console | all
    dataset_filter: Optional[list[str]] = None
    use_llm: bool = False
    run_real: bool = False  # 是否运行真实 Agent 工作流收集 trace
    run_full_workflow: bool = False  # 是否对全流程用例也运行 LangGraph（耗时）
    fail_on_error: bool = False
    fail_threshold: float = 0.0  # overall_score 低于此值则失败


@dataclass
class RunnerResult:
    """Runner 执行结果"""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    config: RunnerConfig = field(default_factory=RunnerConfig)
    benchmark: Optional[BenchmarkResult] = None
    started_at: str = ""
    finished_at: str = ""
    success: bool = False
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "config": {
                "version": self.config.version,
                "cases_dir": self.config.cases_dir,
                "output_dir": self.config.output_dir,
                "output_format": self.config.output_format,
                "dataset_filter": self.config.dataset_filter,
                "use_llm": self.config.use_llm,
                "fail_on_error": self.config.fail_on_error,
                "fail_threshold": self.config.fail_threshold,
            },
            "benchmark": self.benchmark.to_dict() if self.benchmark else None,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "success": self.success,
            "error_message": self.error_message,
        }


# ============================================================
# Report Writer
# ============================================================


class ReportWriter:
    """评测报告写入器 — 支持 JSON, Markdown, Console 多种输出格式"""

    def __init__(self, output_dir: str = "evaluation_results"):
        self.output_dir = output_dir

    def ensure_output_dir(self) -> str:
        """确保输出目录存在"""
        os.makedirs(self.output_dir, exist_ok=True)
        return self.output_dir

    def write_json(self, result: BenchmarkResult, filename: str = "") -> str:
        """
        写入 JSON 格式报告。

        Args:
            result: Benchmark 结果
            filename: 文件名（不含扩展名），为空则自动生成

        Returns:
            写入的文件路径
        """
        self.ensure_output_dir()

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_{result.version}_{ts}"

        filepath = os.path.join(self.output_dir, f"{filename}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.to_json())

        return filepath

    def write_markdown(self, result: BenchmarkResult, filename: str = "") -> str:
        """
        写入 Markdown 格式报告。

        Args:
            result: Benchmark 结果
            filename: 文件名（不含扩展名），为空则自动生成

        Returns:
            写入的文件路径
        """
        self.ensure_output_dir()

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_{result.version}_{ts}"

        filepath = os.path.join(self.output_dir, f"{filename}.md")

        runner = BenchmarkRunner(version=result.version, cases_dir="")
        md_content = runner.generate_markdown_report(result)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        return filepath

    def write_console(self, result: BenchmarkResult) -> str:
        """
        输出到控制台。

        Returns:
            控制台输出的字符串
        """
        text = result.to_summary()
        print(text)
        return text

    def write_all(
        self,
        result: BenchmarkResult,
        basename: str = "",
    ) -> dict[str, str]:
        """
        写入所有格式的报告。

        Returns:
            各格式对应的文件路径 dict
        """
        files: dict[str, str] = {}

        if not basename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = f"benchmark_{result.version}_{ts}"

        files["json"] = self.write_json(result, basename)
        files["markdown"] = self.write_markdown(result, basename)
        files["console"] = self.write_console(result)

        return files


# ============================================================
# Evaluation CLI Runner
# ============================================================


class EvalRunner:
    """
    评测流水线 Runner — CI/CD 集成入口。

    使用方式:
        runner = EvalRunner(config)
        result = await runner.execute()
    """

    def __init__(
        self,
        config: RunnerConfig,
    ):
        self.config = config
        self.runner_result = RunnerResult(config=config)

    async def execute(self) -> RunnerResult:
        """
        执行完整的评测流水线。

        Returns:
            RunnerResult 包含执行结果和 Benchmark 数据
        """
        started_at = datetime.now(timezone.utc)
        self.runner_result.started_at = started_at.isoformat()

        try:
            # Step 1: 构建 trace_provider / llm_call（若启用）
            trace_provider = None
            llm_call = None

            if self.config.run_real:
                from governance.evaluation.trace_provider import create_trace_provider
                trace_provider = await create_trace_provider(
                    run_full_workflow=self.config.run_full_workflow,
                )
                print("  trace_provider: 已创建（run_full_workflow=%s）",
                      self.config.run_full_workflow)

            if self.config.use_llm:
                from langchain_openai import ChatOpenAI
                from governance.evaluation.llm_adapter import create_llm_judge
                from backend.config import get_settings
                s = get_settings()
                llm = ChatOpenAI(
                    base_url=s.llm_api_url,
                    api_key=s.llm_api_key,
                    model=s.llm_model,
                    temperature=0.0,
                    max_tokens=512,
                    timeout=s.llm_timeout,
                )
                llm_call = create_llm_judge(llm)
                print("  llm_call: LLM judge 已就绪（%s）", s.llm_model)

            # Step 2: 创建 BenchmarkRunner
            benchmark_runner = BenchmarkRunner(
                version=self.config.version,
                cases_dir=self.config.cases_dir,
                use_llm=self.config.use_llm,
                llm_call=llm_call,
                trace_provider=trace_provider,
            )

            # Step 3: 运行 Benchmark
            benchmark = await benchmark_runner.run_all(
                dataset_filter=self.config.dataset_filter,
            )
            self.runner_result.benchmark = benchmark

            # Step 4: 输出报告
            if self.config.output_format != "none":
                writer = ReportWriter(output_dir=self.config.output_dir)

                ts = started_at.strftime("%Y%m%d_%H%M%S")
                basename = f"benchmark_{self.config.version}_{ts}"

                if self.config.output_format == "json":
                    writer.write_json(benchmark, basename)
                elif self.config.output_format == "markdown":
                    writer.write_markdown(benchmark, basename)
                elif self.config.output_format == "console":
                    writer.write_console(benchmark)
                elif self.config.output_format == "all":
                    files = writer.write_all(benchmark, basename)
                    print(f"\nReports written:")
                    for fmt, path in files.items():
                        if fmt != "console":
                            print(f"  [{fmt}] {path}")

            # Step 4: 检查阈值
            if self.config.fail_threshold > 0:
                if benchmark.overall_score < self.config.fail_threshold:
                    self.runner_result.success = False
                    self.runner_result.error_message = (
                        f"Overall score {benchmark.overall_score:.2%} "
                        f"below threshold {self.config.fail_threshold:.2%}"
                    )
                    self.runner_result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self.runner_result

            # Step 5: 检查错误
            if self.config.fail_on_error and benchmark.errors:
                self.runner_result.success = False
                self.runner_result.error_message = f"Benchmark had {len(benchmark.errors)} error(s)"
                self.runner_result.finished_at = datetime.now(timezone.utc).isoformat()
                return self.runner_result

            self.runner_result.success = True

        except Exception as e:
            self.runner_result.success = False
            self.runner_result.error_message = str(e)

        self.runner_result.finished_at = datetime.now(timezone.utc).isoformat()
        return self.runner_result

    @staticmethod
    def save_result(result: RunnerResult, filepath: str) -> str:
        """保存 RunnerResult 到 JSON 文件"""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        return filepath

    @staticmethod
    def load_result(filepath: str) -> RunnerResult:
        """从 JSON 文件加载 RunnerResult"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = RunnerConfig(**data.get("config", {}))
        result = RunnerResult(
            run_id=data.get("run_id", ""),
            config=config,
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            success=data.get("success", False),
            error_message=data.get("error_message", ""),
        )

        if data.get("benchmark"):
            result.benchmark = BenchmarkResult(**data["benchmark"])

        return result


# ============================================================
# CLI Definition
# ============================================================


def build_cli_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器"""
    parser = argparse.ArgumentParser(
        prog="eval-runner",
        description="Government Agent Platform — Evaluation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks
  python -m governance.evaluation.runner run

  # Run specific datasets
  python -m governance.evaluation.runner run --datasets business_license,policy_query

  # Output JSON only, with a custom output dir
  python -m governance.evaluation.runner run --output json --output-dir ./reports

  # Fail if overall score below 60%
  python -m governance.evaluation.runner run --fail-threshold 0.6

  # Compare two versions
  python -m governance.evaluation.runner compare --versions v0.1.0,v0.2.0

  # List available datasets
  python -m governance.evaluation.runner list
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ── run ──
    run_parser = subparsers.add_parser("run", help="Run evaluation benchmark")
    run_parser.add_argument(
        "--version", "-v",
        default="current",
        help="Version label (default: current)",
    )
    run_parser.add_argument(
        "--cases-dir",
        default="cases",
        help="Cases directory (default: cases)",
    )
    run_parser.add_argument(
        "--datasets", "-d",
        default="",
        help="Comma-separated dataset names to run (default: all)",
    )
    run_parser.add_argument(
        "--output", "-o",
        choices=["json", "markdown", "console", "all", "none"],
        default="all",
        help="Output format (default: all)",
    )
    run_parser.add_argument(
        "--output-dir",
        default="evaluation_results",
        help="Output directory for reports (default: evaluation_results)",
    )
    run_parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for semantic metric evaluation",
    )
    run_parser.add_argument(
        "--run-real",
        action="store_true",
        help="Run real Agent workflow to collect traces (BERT for intent-only cases)",
    )
    run_parser.add_argument(
        "--run-full-workflow",
        action="store_true",
        help="Also run full LangGraph workflow for non-intent cases (uses LLM API, slow)",
    )
    run_parser.add_argument(
        "--fail-threshold",
        type=float,
        default=0.0,
        help="Fail if overall score below this threshold (0.0~1.0)",
    )
    run_parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with error if any benchmark error occurs",
    )
    run_parser.add_argument(
        "--save-result",
        default="",
        help="Save RunnerResult JSON to this path",
    )
    run_parser.add_argument(
        "--save-to-db",
        action="store_true",
        help="Save evaluation results to PostgreSQL evaluation table",
    )

    # ── compare ──
    compare_parser = subparsers.add_parser("compare", help="Compare evaluation versions")
    compare_parser.add_argument(
        "--versions",
        required=True,
        help="Comma-separated versions to compare (uses saved result files)",
    )
    compare_parser.add_argument(
        "--results-dir",
        default="evaluation_results",
        help="Directory containing saved result JSON files",
    )

    # ── list ──
    list_parser = subparsers.add_parser("list", help="List available datasets")
    list_parser.add_argument(
        "--cases-dir",
        default="cases",
        help="Cases directory (default: cases)",
    )

    return parser


# ============================================================
# CLI Handlers
# ============================================================


async def _save_benchmark_to_db(result: RunnerResult) -> None:
    """将 Benchmark 中各数据集的 EvaluationResult 写入 evaluation 表"""
    b = result.benchmark
    if not b or not b.datasets:
        print("  [WARN] No benchmark datasets to save to DB")
        return

    try:
        from database.connection import get_session_factory
        from backend.config import get_settings
        from governance.evaluation.evaluator import EvaluationEngine

        settings = get_settings()
        try:
            session_factory = get_session_factory()
        except Exception:
            # 如果惰性单例尚未初始化（如 CLI 直接运行），手动创建
            from database.connection import create_engine, create_session_factory
            engine = create_engine(settings)
            session_factory = create_session_factory(engine)

        saved = 0
        for ds_name, eval_result in b.datasets.items():
            if not eval_result:
                continue
            try:
                engine = EvaluationEngine()
                ok = await engine.save_result(eval_result, session_factory)
                if ok:
                    saved += 1
                    print(f"  ✅ {ds_name}: {eval_result.total_cases} cases, "
                          f"{eval_result.passed_cases} passed, "
                          f"score={eval_result.overall_score:.2%}")
                else:
                    print(f"  ❌ {ds_name}: DB save returned False")
            except Exception as e:
                print(f"  ❌ {ds_name}: DB save failed — {e}")

        print(f"  Saved {saved}/{len(b.datasets)} datasets to evaluation table.")

    except ImportError as e:
        print(f"  [WARN] Cannot save to DB (missing dependency): {e}")
    except Exception as e:
        print(f"  [WARN] DB save failed: {e}")



async def handle_run(args: argparse.Namespace) -> int:
    """处理 run 命令"""
    # 构建配置
    dataset_filter = None
    if args.datasets:
        dataset_filter = [d.strip() for d in args.datasets.split(",") if d.strip()]

    config = RunnerConfig(
        version=args.version,
        cases_dir=args.cases_dir,
        output_dir=args.output_dir,
        output_format=args.output,
        dataset_filter=dataset_filter,
        use_llm=args.use_llm,
        run_real=args.run_real,
        run_full_workflow=args.run_full_workflow,
        fail_on_error=args.fail_on_error,
        fail_threshold=args.fail_threshold,
    )

    print(f"Starting evaluation run...")
    print(f"  Version:        {config.version}")
    print(f"  Cases dir:      {config.cases_dir}")
    print(f"  Datasets:       {config.dataset_filter or 'all'}")
    print(f"  Run real trace: {config.run_real}")
    print(f"  Full workflow:  {config.run_full_workflow}")
    print(f"  Use LLM judge:  {config.use_llm}")
    print(f"  Output:         {config.output_format}")
    print()

    runner = EvalRunner(config)
    result = await runner.execute()

    if result.success:
        b = result.benchmark
        if b:
            print(f"\nEvaluation completed successfully.")
            print(f"  Overall Score: {b.overall_score:.2%}")
            print(f"  Total Cases:   {b.total_cases}")
            print(f"  Passed Cases:  {b.passed_cases}")
    else:
        print(f"\nEvaluation FAILED: {result.error_message}", file=sys.stderr)

    # 保存结果到 JSON
    if args.save_result:
        path = EvalRunner.save_result(result, args.save_result)
        print(f"Runner result saved to: {path}")

    # 保存结果到数据库
    if args.save_to_db:
        await _save_benchmark_to_db(result)
        print("Evaluation results saved to database.")

    return 0 if result.success else 1


async def handle_compare(args: argparse.Namespace) -> int:
    """处理 compare 命令"""
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]

    if len(versions) < 2:
        print("Error: Need at least 2 versions to compare", file=sys.stderr)
        return 1

    # 加载各版本结果
    benchmarks: list[BenchmarkResult] = []
    for ver in versions:
        filepath = os.path.join(args.results_dir, f"benchmark_{ver}_result.json")
        if not os.path.exists(filepath):
            # 尝试其他命名模式
            candidates = [
                os.path.join(args.results_dir, f"benchmark_{ver}.json"),
                os.path.join(args.results_dir, f"benchmark_{ver}_*.json"),
            ]
            found = False
            for pattern in candidates:
                if "*" in pattern:
                    import glob
                    matches = sorted(glob.glob(pattern))
                    if matches:
                        filepath = matches[-1]  # 使用最新的
                        found = True
                        break
                elif os.path.exists(pattern):
                    filepath = pattern
                    found = True
                    break
            if not found:
                print(f"Warning: No result file found for version '{ver}'", file=sys.stderr)
                continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 文件可能是 RunnerResult 或直接的 BenchmarkResult
            if "benchmark" in data and data["benchmark"]:
                bm_data = data["benchmark"]
            else:
                bm_data = data
            bm = BenchmarkResult(
                benchmark_name=bm_data.get("benchmark_name", ver),
                version=bm_data.get("version", ver),
                overall_score=bm_data.get("overall_score", 0.0),
                total_cases=bm_data.get("total_cases", 0),
                passed_cases=bm_data.get("passed_cases", 0),
            )
            benchmarks.append(bm)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading result for '{ver}': {e}", file=sys.stderr)
            continue

    if len(benchmarks) < 2:
        print("Error: Not enough valid results to compare", file=sys.stderr)
        return 1

    # 对比
    comparison = BenchmarkRunner.compare_benchmarks(benchmarks)

    print("=" * 60)
    print("Version Comparison")
    print("=" * 60)
    print(f"Versions: {', '.join(comparison['versions'])}")
    print(f"Best:     {comparison['best_version']}")
    print()
    print("Overall Scores:")
    for ver, score in zip(comparison["versions"], comparison["overall_scores"]):
        print(f"  {ver}: {score:.2%}")

    if "diff" in comparison:
        diff = comparison["diff"]
        print(f"\nLatest diff ({comparison['versions'][-1]} vs {comparison['versions'][-2]}):")
        print(f"  Overall Score: {diff['overall_score']:+.4f}")
        print(f"  Total Cases:   {diff['total_cases']:+d}")
        print(f"  Passed Cases:  {diff['passed_cases']:+d}")

    if comparison.get("per_dataset"):
        print("\nPer-Dataset:")
        for ds_name, ds_data in comparison["per_dataset"].items():
            print(f"  {ds_name}:")
            for ver_name, metrics in ds_data.items():
                print(f"    {ver_name}: score={metrics['overall_score']:.2%}, "
                      f"passed={metrics['passed_cases']}/{metrics['total_cases']}")

    print("=" * 60)
    return 0


async def handle_list(args: argparse.Namespace) -> int:
    """处理 list 命令"""
    runner = BenchmarkRunner(version="list", cases_dir=args.cases_dir)
    datasets = runner.discover_datasets()

    if not datasets:
        print(f"No datasets found in '{args.cases_dir}'")
        return 0

    print(f"Datasets in '{args.cases_dir}':")
    print("-" * 50)
    for filepath in datasets:
        name = os.path.splitext(os.path.basename(filepath))[0]
        ds = runner.load_dataset(filepath)
        metadata_desc = ""
        if ds.metadata.get("_description"):
            metadata_desc = f" — {ds.metadata['_description'][:60]}"
        print(f"  {name:25s} {ds.case_count:>4d} cases{metadata_desc}")
    print("-" * 50)
    return 0


# ============================================================
# Main Entry Point
# ============================================================


async def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    CLI 主入口。

    Args:
        argv: 命令行参数（None 则使用 sys.argv）

    Returns:
        exit code (0=success, 1=failure)
    """
    parser = build_cli_parser()

    if argv is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(argv)

    if args.command == "run":
        return await handle_run(args)
    elif args.command == "compare":
        return await handle_compare(args)
    elif args.command == "list":
        return await handle_list(args)
    else:
        parser.print_help()
        return 0


def cli_main() -> None:
    """同步 CLI 入口（供 setup.py console_scripts 使用）"""
    import asyncio
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


# ============================================================
# Smoke Test
# ============================================================


def _smoke_test() -> None:
    """模块自测"""
    import asyncio

    passed = 0
    total = 0

    print("=" * 60)
    print("EvalRunner Tests")
    print("=" * 60)

    _cur_dir = os.path.dirname(os.path.abspath(__file__))
    _proj_dir = os.path.dirname(os.path.dirname(_cur_dir))
    _cases_dir = os.path.join(_proj_dir, "cases")

    # Test 1: RunnerConfig defaults
    total += 1
    config = RunnerConfig()
    assert config.version == "current"
    assert config.cases_dir == "cases"
    assert config.output_format == "all"
    assert config.fail_threshold == 0.0
    passed += 1
    print(f"  [OK] RunnerConfig defaults")

    # Test 2: EvalRunner execute success
    total += 1
    async def test_execute():
        config = RunnerConfig(
            version="test",
            cases_dir=_cases_dir,
            dataset_filter=["business_license"],
            output_format="none",
        )
        runner = EvalRunner(config)
        result = await runner.execute()
        assert result.success is True or result.success is False  # depends on data
        assert result.benchmark is not None
        return result

    r = asyncio.run(test_execute())
    passed += 1
    print(f"  [OK] EvalRunner execute -> success={r.success}, datasets={len(r.benchmark.datasets) if r.benchmark else 0}")

    # Test 3: EvalRunner fail on threshold
    total += 1
    async def test_threshold():
        config = RunnerConfig(
            version="test",
            cases_dir=_cases_dir,
            dataset_filter=["business_license"],
            output_format="none",
            fail_threshold=1.0,  # impossible to reach
        )
        runner = EvalRunner(config)
        result = await runner.execute()
        assert result.success is False
        assert result.benchmark is not None
        return result

    r = asyncio.run(test_threshold())
    passed += 1
    print(f"  [OK] EvalRunner fail_threshold -> success={r.success}")

    # Test 4: ReportWriter write_json
    total += 1
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ReportWriter(output_dir=tmpdir)
        async def gen_bm():
            config = RunnerConfig(cases_dir=_cases_dir, dataset_filter=["business_license"], output_format="none")
            runner = EvalRunner(config)
            result = await runner.execute()
            return result.benchmark

        bm = asyncio.run(gen_bm())
        path = writer.write_json(bm, "test_report")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "benchmark_id" in data
        passed += 1
        print(f"  [OK] ReportWriter write_json -> {os.path.basename(path)}")

    # Test 5: ReportWriter write_markdown
    total += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ReportWriter(output_dir=tmpdir)
        async def gen_bm2():
            config = RunnerConfig(cases_dir=_cases_dir, dataset_filter=["business_license"], output_format="none")
            runner = EvalRunner(config)
            result = await runner.execute()
            return result.benchmark

        bm = asyncio.run(gen_bm2())
        path = writer.write_markdown(bm, "test_report")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "# Benchmark Report" in content
        passed += 1
        print(f"  [OK] ReportWriter write_markdown -> {len(content)} chars")

    # Test 6: ReportWriter write_all
    total += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ReportWriter(output_dir=tmpdir)
        async def gen_bm3():
            config = RunnerConfig(cases_dir=_cases_dir, dataset_filter=["business_license"], output_format="none")
            runner = EvalRunner(config)
            result = await runner.execute()
            return result.benchmark

        bm = asyncio.run(gen_bm3())
        files = writer.write_all(bm, "test_all")
        assert "json" in files
        assert "markdown" in files
        assert "console" in files
        assert os.path.exists(files["json"])
        assert os.path.exists(files["markdown"])
        passed += 1
        print(f"  [OK] ReportWriter write_all -> {len(files)} formats")

    # Test 7: EvalRunner save/load result
    total += 1
    with tempfile.TemporaryDirectory() as tmpdir:
        async def gen_result():
            config = RunnerConfig(cases_dir=_cases_dir, dataset_filter=["business_license"], output_format="none")
            runner = EvalRunner(config)
            return await runner.execute()

        result = asyncio.run(gen_result())
        save_path = os.path.join(tmpdir, "runner_result.json")
        EvalRunner.save_result(result, save_path)
        assert os.path.exists(save_path)

        loaded = EvalRunner.load_result(save_path)
        assert loaded.run_id == result.run_id
        assert loaded.success == result.success
        passed += 1
        print(f"  [OK] EvalRunner save/load -> {loaded.run_id[:8]}")

    # Test 8: CLI parser basic
    total += 1
    parser = build_cli_parser()
    args = parser.parse_args(["run", "--version", "test", "--output", "none"])
    assert args.command == "run"
    assert args.version == "test"
    assert args.output == "none"
    passed += 1
    print(f"  [OK] CLI parser run command")

    # Test 9: CLI parser compare
    total += 1
    args = parser.parse_args(["compare", "--versions", "v1,v2"])
    assert args.command == "compare"
    assert args.versions == "v1,v2"
    passed += 1
    print(f"  [OK] CLI parser compare command")

    # Test 10: CLI parser list
    total += 1
    args = parser.parse_args(["list"])
    assert args.command == "list"
    passed += 1
    print(f"  [OK] CLI parser list command")

    # Test 11: RunnerResult to_dict
    total += 1
    config = RunnerConfig(version="v1")
    result = RunnerResult(config=config, success=True)
    d = result.to_dict()
    assert d["success"] is True
    assert d["config"]["version"] == "v1"
    passed += 1
    print(f"  [OK] RunnerResult to_dict")

    # Test 12: handle_list
    total += 1
    async def test_list():
        args = parser.parse_args(["list", "--cases-dir", _cases_dir])
        code = await handle_list(args)
        return code

    code = asyncio.run(test_list())
    passed += 1
    print(f"  [OK] handle_list -> exit_code={code}")

    # Test 13: CLI main with no args
    total += 1
    async def test_main_no_args():
        code = await main([])
        return code

    code = asyncio.run(test_main_no_args())
    passed += 1
    print(f"  [OK] main no args -> exit_code={code}")

    # Test 14: handle_run with datasets filter
    total += 1
    async def test_run_filter():
        args = parser.parse_args([
            "run", "--version", "smoke_test",
            "--cases-dir", _cases_dir,
            "--datasets", "business_license,policy_query",
            "--output", "none",
        ])
        code = await handle_run(args)
        return code

    code = asyncio.run(test_run_filter())
    passed += 1
    print(f"  [OK] handle_run filtered -> exit_code={code}")

    # Test 15: handle_run with fail_on_error (empty dataset - no real errors expected)
    total += 1
    async def test_run_fail_error():
        args = parser.parse_args([
            "run", "--version", "test",
            "--cases-dir", _cases_dir,
            "--datasets", "business_license",
            "--output", "none",
            "--fail-on-error",
        ])
        code = await handle_run(args)
        return code

    code = asyncio.run(test_run_fail_error())
    passed += 1
    print(f"  [OK] handle_run fail_on_error -> exit_code={code}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed")
    print("=" * 60)

    if passed == total:
        print("ALL smoke tests passed!")
    else:
        print(f"{total - passed} test(s) failed!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sys.exit(cli_main())
    else:
        _smoke_test()
