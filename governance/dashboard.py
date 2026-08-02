"""
governance.dashboard - AgentOps dashboard: agent performance, evaluation results, trace visualization

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement dashboard data API for agent operations visualization
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


# ============================================================
# 数据类
# ============================================================


@dataclass
class AgentStat:
    """单个 Agent 的运行统计"""
    agent_name: str
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_step_count: float = 0.0
    total_tokens: int = 0
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "avg_step_count": round(self.avg_step_count, 2),
            "total_tokens": self.total_tokens,
            "risk_level": self.risk_level,
        }


@dataclass
class EvalTrendPoint:
    """评测趋势数据点"""
    date: str                    # ISO date
    version: str
    overall_score: float
    task_success_rate: float
    tool_accuracy: float
    rag_faithfulness: float
    total_cases: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "version": self.version,
            "overall_score": round(self.overall_score, 4),
            "task_success_rate": round(self.task_success_rate, 4),
            "tool_accuracy": round(self.tool_accuracy, 4),
            "rag_faithfulness": round(self.rag_faithfulness, 4),
            "total_cases": self.total_cases,
        }


@dataclass
class VersionComparison:
    """版本 A/B 对比"""
    version_a: str
    version_b: str
    metric: str
    value_a: float
    value_b: float
    delta: float
    delta_pct: float             # 变化百分比
    winner: str                  # "a" | "b" | "tie"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_a": self.version_a,
            "version_b": self.version_b,
            "metric": self.metric,
            "value_a": round(self.value_a, 4),
            "value_b": round(self.value_b, 4),
            "delta": round(self.delta, 4),
            "delta_pct": round(self.delta_pct, 2),
            "winner": self.winner,
        }


@dataclass
class DashboardSummary:
    """运维看板总览"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_stats: list[AgentStat] = field(default_factory=list)
    eval_trends: list[EvalTrendPoint] = field(default_factory=list)
    version_comparisons: list[VersionComparison] = field(default_factory=list)
    system_health: dict[str, Any] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "agent_stats": [a.to_dict() for a in self.agent_stats],
            "eval_trends": [e.to_dict() for e in self.eval_trends],
            "version_comparisons": [v.to_dict() for v in self.version_comparisons],
            "system_health": self.system_health,
            "alerts": self.alerts,
        }


# ============================================================
# DashboardDataProvider
# ============================================================


class DashboardDataProvider:
    """
    看板数据提供者：从数据库和内存聚合数据。

    两模式：
    1. DB 模式：查询 PostgreSQL trace/evaluation 表
    2. Memory 模式：从 MetricsCollector + TraceRecorder 聚合（无需DB）
    """

    def __init__(self) -> None:
        self._memory_traces: list[dict[str, Any]] = []
        self._memory_evals: list[dict[str, Any]] = []

    # ── Agent 统计 ──

    async def get_agent_stats(
        self,
        since: datetime | None = None,
        use_db: bool = False,
    ) -> list[AgentStat]:
        """
        获取各 Agent 运行统计。

        Args:
            since: 起始时间，None 表示最近 7 天
            use_db: 是否从数据库查询

        Returns:
            AgentStat 列表
        """
        if use_db:
            return await self._get_agent_stats_from_db(since)

        # Memory 模式：从 MetricsCollector 聚合
        try:
            from governance.monitor import get_collector
            collector = get_collector()
            stats = collector.get_stats()

            agent_stats: list[AgentStat] = []
            per_agent = stats.get("agent", {}).get("per_agent", {})

            for agent_name, data in per_agent.items():
                agent_stats.append(AgentStat(
                    agent_name=agent_name,
                    total_calls=data.get("calls", 0),
                    success_count=data.get("success", 0),
                    failure_count=data.get("failure", 0),
                    success_rate=data.get("success_rate", 0.0),
                    avg_latency_ms=data.get("avg_latency_ms", 0.0),
                ))

            # 加上 memory 中的历史数据
            for t in self._memory_traces:
                name = t.get("agent_name", "unknown")
                existing = next((a for a in agent_stats if a.agent_name == name), None)
                if existing:
                    existing.total_calls += 1
                    if t.get("success"):
                        existing.success_count += 1
                    else:
                        existing.failure_count += 1
                    existing.success_rate = (
                        existing.success_count / existing.total_calls
                        if existing.total_calls > 0 else 0.0
                    )
                else:
                    agent_stats.append(AgentStat(
                        agent_name=name, total_calls=1,
                        success_count=1 if t.get("success") else 0,
                        failure_count=0 if t.get("success") else 1,
                    ))

            return agent_stats
        except Exception:
            return []

    async def _get_agent_stats_from_db(
        self, since: datetime | None = None
    ) -> list[AgentStat]:
        """从数据库查询 Agent 统计数据"""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        try:
            from database.connection import get_session_factory
            from database.models import Trace
            from sqlalchemy import func, select

            session_factory = get_session_factory()
            async with session_factory() as session:
                stmt = (
                    select(
                        Trace.agent_name,
                        func.count(Trace.id).label("total"),
                        func.sum(
                            func.case((Trace.status == "success", 1), else_=0)
                        ).label("success_count"),
                        func.avg(Trace.latency_ms).label("avg_latency"),
                        func.sum(Trace.input_tokens + Trace.output_tokens).label("total_tokens"),
                    )
                    .where(Trace.created_at >= since)
                    .group_by(Trace.agent_name)
                )
                result = await session.execute(stmt)
                rows = result.all()

                agent_stats: list[AgentStat] = []
                for row in rows:
                    total = row.total or 0
                    success = row.success_count or 0
                    agent_stats.append(AgentStat(
                        agent_name=row.agent_name or "unknown",
                        total_calls=total,
                        success_count=success,
                        failure_count=total - success,
                        success_rate=(success / total) if total > 0 else 0.0,
                        avg_latency_ms=round(row.avg_latency or 0.0, 2),
                        total_tokens=int(row.total_tokens or 0),
                    ))
                return agent_stats
        except Exception:
            return []

    # ── 评测趋势 ──

    async def get_eval_trends(
        self,
        days: int = 30,
        use_db: bool = False,
    ) -> list[EvalTrendPoint]:
        """
        获取评测趋势数据。

        Args:
            days: 最近 N 天
            use_db: 是否从数据库查询

        Returns:
            EvalTrendPoint 列表
        """
        if use_db:
            return await self._get_eval_trends_from_db(days)

        # Memory 模式
        trends: list[EvalTrendPoint] = list(self._memory_evals)
        trends.sort(key=lambda e: e.date)
        return trends

    async def _get_eval_trends_from_db(
        self, days: int = 30
    ) -> list[EvalTrendPoint]:
        """从数据库查询评测趋势"""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            from database.connection import get_session_factory
            from database.models import Evaluation
            from sqlalchemy import select

            session_factory = get_session_factory()
            async with session_factory() as session:
                stmt = (
                    select(Evaluation)
                    .where(Evaluation.created_at >= since)
                    .order_by(Evaluation.created_at.asc())
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                trends: list[EvalTrendPoint] = []
                for row in rows:
                    trends.append(EvalTrendPoint(
                        date=row.created_at.strftime("%Y-%m-%d") if row.created_at else "",
                        version=row.version or "unknown",
                        overall_score=(
                            row.task_success_rate * 0.4 +
                            row.tool_accuracy * 0.2 +
                            row.rag_faithfulness * 0.15 +
                            row.rag_answer_relevance * 0.15 +
                            row.rag_context_recall * 0.10
                        ),
                        task_success_rate=row.task_success_rate or 0.0,
                        tool_accuracy=row.tool_accuracy or 0.0,
                        rag_faithfulness=row.rag_faithfulness or 0.0,
                        total_cases=row.total_cases or 0,
                    ))
                return trends
        except Exception:
            return []

    # ── 版本对比 ──

    def compare_versions(
        self,
        version_a: str,
        version_b: str,
        eval_data: list[dict[str, Any]] | None = None,
    ) -> list[VersionComparison]:
        """
        对比两个版本的评测指标。

        Args:
            version_a: 版本 A
            version_b: 版本 B
            eval_data: 评测数据列表（可选，从 memory 取）

        Returns:
            VersionComparison 列表
        """
        if eval_data is None:
            eval_data = [
                e if isinstance(e, dict) else e.to_dict()
                for e in self._memory_evals
            ]

        # 按版本分组
        group_a = [d for d in eval_data if d.get("version") == version_a]
        group_b = [d for d in eval_data if d.get("version") == version_b]

        metrics = [
            ("task_success_rate", "任务成功率"),
            ("tool_accuracy", "工具准确率"),
            ("rag_faithfulness", "RAG 真实性"),
            ("rag_answer_relevance", "答案相关性"),
            ("rag_context_recall", "上下文召回率"),
            ("overall_score", "综合评分"),
        ]

        comparisons: list[VersionComparison] = []
        for metric_key, metric_label in metrics:
            avg_a = (
                sum(d.get(metric_key, 0.0) for d in group_a) / len(group_a)
                if group_a else 0.0
            )
            avg_b = (
                sum(d.get(metric_key, 0.0) for d in group_b) / len(group_b)
                if group_b else 0.0
            )

            delta = avg_b - avg_a
            delta_pct = (delta / avg_a * 100.0) if avg_a > 0 else 0.0
            if abs(delta) < 0.001:
                winner = "tie"
            else:
                winner = "b" if delta > 0 else "a"

            comparisons.append(VersionComparison(
                version_a=version_a,
                version_b=version_b,
                metric=metric_label,
                value_a=avg_a,
                value_b=avg_b,
                delta=delta,
                delta_pct=delta_pct,
                winner=winner,
            ))

        return comparisons

    # ── 系统健康 ──

    def get_system_health(self) -> dict[str, Any]:
        """
        获取系统健康状态摘要。

        Returns:
            健康信息字典
        """
        health: dict[str, Any] = {
            "status": "healthy",
            "components": {},
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

        # Monitor collector health
        try:
            from governance.monitor import get_collector
            collector = get_collector()
            stats = collector.get_stats()
            success_rate = stats["agent"]["overall_success_rate"]
            health["components"]["monitor"] = {
                "status": "healthy" if success_rate > 0.5 else "degraded",
                "agent_success_rate": success_rate,
                "active_spans": stats["agent"]["active_spans"],
            }
        except Exception:
            health["components"]["monitor"] = {"status": "unavailable"}

        # Trace recorder health
        try:
            from governance.trace import get_trace_recorder
            recorder = get_trace_recorder()
            span_count = len(recorder.spans)
            health["components"]["trace"] = {
                "status": "healthy",
                "spans_in_memory": span_count,
            }
        except Exception:
            health["components"]["trace"] = {"status": "unavailable"}

        # Overall
        statuses = [c.get("status", "healthy") for c in health["components"].values()]
        if "unavailable" in statuses:
            health["status"] = "degraded"
        if all(s == "healthy" for s in statuses):
            health["status"] = "healthy"

        return health

    # ── Alerts ──

    def get_alerts(self) -> list[dict[str, Any]]:
        """
        获取告警列表。

        Returns:
            告警列表
        """
        alerts: list[dict[str, Any]] = []

        try:
            from governance.monitor import get_collector
            collector = get_collector()
            stats = collector.get_stats()

            # Agent 成功率告警
            for agent_name, data in stats.get("agent", {}).get("per_agent", {}).items():
                success_rate = data.get("success_rate", 1.0)
                if success_rate < 0.5:
                    alerts.append({
                        "level": "critical",
                        "component": f"agent:{agent_name}",
                        "message": f"Agent {agent_name} 成功率过低: {success_rate:.1%}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                elif success_rate < 0.8:
                    alerts.append({
                        "level": "warning",
                        "component": f"agent:{agent_name}",
                        "message": f"Agent {agent_name} 成功率下降: {success_rate:.1%}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            # Guardrail 阻断告警
            blocks = stats.get("guardrail", {}).get("total_blocks", 0)
            if blocks > 100:
                alerts.append({
                    "level": "warning",
                    "component": "guardrail",
                    "message": f"护栏阻断次数较高: {blocks}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception:
            pass

        return alerts

    # ── Memory 数据注入（非DB模式） ──

    def inject_trace_data(self, trace_data: dict[str, Any]) -> None:
        """注入内存 trace 数据"""
        self._memory_traces.append(trace_data)

    def inject_eval_data(self, eval_data: dict[str, Any] | EvalTrendPoint) -> None:
        """注入内存评测数据"""
        if isinstance(eval_data, dict):
            self._memory_evals.append(EvalTrendPoint(**eval_data))
        else:
            self._memory_evals.append(eval_data)

    # ── 汇总 ──

    async def get_summary(
        self,
        use_db: bool = False,
        version_a: str | None = None,
        version_b: str | None = None,
    ) -> DashboardSummary:
        """
        获取看板完整汇总。

        Args:
            use_db: 是否从数据库查询
            version_a: 版本对比 A
            version_b: 版本对比 B

        Returns:
            DashboardSummary
        """
        agent_stats = await self.get_agent_stats(use_db=use_db)
        eval_trends = await self.get_eval_trends(use_db=use_db)
        system_health = self.get_system_health()
        alerts = self.get_alerts()

        comparisons: list[VersionComparison] = []
        if version_a and version_b:
            comparisons = self.compare_versions(version_a, version_b)

        return DashboardSummary(
            agent_stats=agent_stats,
            eval_trends=eval_trends,
            version_comparisons=comparisons,
            system_health=system_health,
            alerts=alerts,
        )


# ============================================================
# 全局单例
# ============================================================


_provider: DashboardDataProvider | None = None


def get_dashboard_provider() -> DashboardDataProvider:
    """获取全局 DashboardDataProvider 单例"""
    global _provider
    if _provider is None:
        _provider = DashboardDataProvider()
    return _provider


def reset_dashboard_provider() -> None:
    """重置全局 DashboardDataProvider（测试用）"""
    global _provider
    _provider = DashboardDataProvider()


# ============================================================
# 便捷函数
# ============================================================


async def get_dashboard_summary(
    use_db: bool = False,
    version_a: str | None = None,
    version_b: str | None = None,
) -> dict[str, Any]:
    """
    获取看板汇总数据（便捷异步函数）。

    Args:
        use_db: 是否从数据库查询
        version_a: 版本 A
        version_b: 版本 B

    Returns:
        看板汇总字典
    """
    provider = get_dashboard_provider()
    summary = await provider.get_summary(
        use_db=use_db,
        version_a=version_a,
        version_b=version_b,
    )
    return summary.to_dict()


# ============================================================
# Smoke Test
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(name: str, actual: Any, expected: Any) -> None:
        global passed, failed
        if actual == expected:
            passed += 1
            print(f"  [OK] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected={expected!r}, got={actual!r}")

    def check_approx(name: str, actual: float, expected: float, tolerance: float = 0.01) -> None:
        global passed, failed
        if abs(actual - expected) <= tolerance:
            passed += 1
            print(f"  [OK] {name} (~{expected})")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected~{expected!r}, got={actual!r}")

    async def run_tests():
        global passed, failed
        print("=== governance.dashboard smoke test ===")

        # ── AgentStat ──
        print("--- AgentStat ---")
        stat = AgentStat(agent_name="supervisor", total_calls=100, success_count=95,
                         failure_count=5, success_rate=0.95, avg_latency_ms=200.0)
        d = stat.to_dict()
        check("stat_name", d["agent_name"], "supervisor")
        check("stat_rate", d["success_rate"], 0.95)
        check("stat_latency", d["avg_latency_ms"], 200.0)

        # ── EvalTrendPoint ──
        print("--- EvalTrendPoint ---")
        tp = EvalTrendPoint(date="2026-08-01", version="v1.0", overall_score=0.85,
                            task_success_rate=0.9, tool_accuracy=0.8,
                            rag_faithfulness=0.85, total_cases=50)
        td = tp.to_dict()
        check("tp_date", td["date"], "2026-08-01")
        check("tp_score", td["overall_score"], 0.85)

        # ── VersionComparison ──
        print("--- VersionComparison ---")
        vc = VersionComparison(version_a="v1.0", version_b="v2.0", metric="任务成功率",
                               value_a=0.8, value_b=0.9, delta=0.1, delta_pct=12.5,
                               winner="b")
        vd = vc.to_dict()
        check("vc_winner", vd["winner"], "b")
        check("vc_delta", vd["delta"], 0.1)

        # ── DashboardDataProvider (memory mode) ──
        print("--- DashboardDataProvider ---")
        reset_dashboard_provider()
        provider = get_dashboard_provider()

        # Inject mock data
        provider.inject_trace_data({
            "agent_name": "supervisor", "success": True, "latency_ms": 150, "step_count": 2,
        })
        provider.inject_trace_data({
            "agent_name": "supervisor", "success": True, "latency_ms": 250, "step_count": 3,
        })
        provider.inject_trace_data({
            "agent_name": "policy", "success": False, "latency_ms": 500, "step_count": 1,
        })
        provider.inject_eval_data({
            "date": "2026-08-01", "version": "v1.0", "overall_score": 0.80,
            "task_success_rate": 0.85, "tool_accuracy": 0.75,
            "rag_faithfulness": 0.80, "total_cases": 50,
        })
        provider.inject_eval_data({
            "date": "2026-08-01", "version": "v2.0", "overall_score": 0.88,
            "task_success_rate": 0.92, "tool_accuracy": 0.85,
            "rag_faithfulness": 0.87, "total_cases": 50,
        })
        provider.inject_eval_data({
            "date": "2026-08-02", "version": "v2.0", "overall_score": 0.90,
            "task_success_rate": 0.93, "tool_accuracy": 0.87,
            "rag_faithfulness": 0.89, "total_cases": 60,
        })

        # Agent stats
        agent_stats = await provider.get_agent_stats()
        check("provider_stats_len", len(agent_stats), 2)
        supervisor = next((a for a in agent_stats if a.agent_name == "supervisor"), None)
        check("provider_supervisor", supervisor is not None, True)
        if supervisor:
            check("supervisor_calls", supervisor.total_calls, 2)
            check("supervisor_success", supervisor.success_count, 2)
            check_approx("supervisor_rate", supervisor.success_rate, 1.0)

        policy = next((a for a in agent_stats if a.agent_name == "policy"), None)
        if policy:
            check("policy_calls", policy.total_calls, 1)
            check("policy_failure", policy.failure_count, 1)

        # Eval trends
        trends = await provider.get_eval_trends()
        check("trends_len", len(trends), 3)

        # Version comparison
        comparisons = provider.compare_versions("v1.0", "v2.0")
        check("comp_not_empty", len(comparisons) > 0, True)
        # v2.0 should be better
        winners = [c.winner for c in comparisons]
        check("comp_v2_wins_most", winners.count("b") >= winners.count("a"), True)

        # System health
        health = provider.get_system_health()
        check("health_status", health["status"] in ("healthy", "degraded", "unavailable"), True)
        check("health_components", "monitor" in health["components"], True)

        # Alerts (no alerts expected with mock data since no collector data)
        alerts = provider.get_alerts()
        check("alerts_is_list", isinstance(alerts, list), True)

        # Full summary
        summary = await provider.get_summary(version_a="v1.0", version_b="v2.0")
        check("summary_agent_stats", len(summary.agent_stats) > 0, True)
        check("summary_evals", len(summary.eval_trends) > 0, True)
        check("summary_comps", len(summary.version_comparisons) > 0, True)
        check("summary_health", "status" in summary.system_health, True)

        sd = summary.to_dict()
        check("sd_keys", set(sd.keys()),
              {"timestamp", "agent_stats", "eval_trends", "version_comparisons",
               "system_health", "alerts"})

        # ── DashboardSummary direct ──
        print("--- DashboardSummary ---")
        ds = DashboardSummary(
            agent_stats=[AgentStat(agent_name="test", total_calls=10)],
        )
        dsd = ds.to_dict()
        check("ds_timestamp", "timestamp" in dsd, True)
        check("ds_agent_stats", len(dsd["agent_stats"]), 1)

        # ── Convenience function ──
        print("--- Convenience ---")
        reset_dashboard_provider()
        provider2 = get_dashboard_provider()
        provider2.inject_eval_data({
            "date": "2026-08-01", "version": "v1.0", "overall_score": 0.75,
            "task_success_rate": 0.80, "tool_accuracy": 0.70,
            "rag_faithfulness": 0.75, "total_cases": 30,
        })
        summary_dict = await get_dashboard_summary()
        check("conv_summary", "agent_stats" in summary_dict, True)

        # ── Summary ──
        total = passed + failed
        print(f"\n=== {passed}/{total} passed, {failed} failed ===")
        if failed > 0:
            raise SystemExit(1)

    asyncio.run(run_tests())
