"""
a2a.registry - Agent Registry: manage external agent discovery and health checks

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement Agent Registry for external agent registration and discovery
"""
from __future__ import annotations

from typing import Optional

from tools.logger import get_logger
from tools.a2a.protocol import AgentCard, AgentHealth

logger = get_logger(__name__)


# ============================================================
# ExternalAgentRegistry
# ============================================================


class ExternalAgentRegistry:
    """
    外部 Agent 注册中心 — 管理跨域 Agent 的注册、发现和健康检查。

    本系统（Gov AP）通过此 Registry 发现可用的外部 Agent，
    并根据技能匹配选择合适的 Agent 进行 A2A 通信。

    用法:
        registry = ExternalAgentRegistry()

        # 注册
        registry.register(AgentCard(name="housing_agent", skills=["query_property"], ...))

        # 按技能发现
        agents = registry.discover("query_property")  # → [AgentCard, ...]

        # 获取指定 Agent
        card = registry.get_agent("housing_agent")
    """

    def __init__(self):
        self._agents: dict[str, AgentCard] = {}
        self._health: dict[str, AgentHealth] = {}
        # 技能→Agent名称 索引
        self._skill_index: dict[str, list[str]] = {}

    # ── 注册/注销 ──

    def register(self, card: AgentCard) -> None:
        """
        注册一个外部 Agent。

        Args:
            card: AgentCard 实例
        """
        name = card.name

        if name in self._agents:
            logger.warning("外部 Agent {} 已注册，将被覆盖", name)

        self._agents[name] = card
        self._health[name] = AgentHealth.UNKNOWN

        # 更新技能索引
        for skill in card.skills:
            if skill not in self._skill_index:
                self._skill_index[skill] = []
            if name not in self._skill_index[skill]:
                self._skill_index[skill].append(name)

        logger.info(
            "外部 Agent 已注册: {} (skills={}, endpoint={})",
            name, card.skills, card.endpoint,
        )

    def unregister(self, name: str) -> None:
        """
        注销一个外部 Agent。

        Args:
            name: Agent 名称
        """
        card = self._agents.pop(name, None)
        self._health.pop(name, None)

        if card:
            for skill in card.skills:
                if skill in self._skill_index:
                    self._skill_index[skill] = [
                        n for n in self._skill_index[skill] if n != name
                    ]
                    if not self._skill_index[skill]:
                        del self._skill_index[skill]

        logger.info("外部 Agent 已注销: {}", name)

    # ── 发现 ──

    def discover(self, skill: str) -> list[AgentCard]:
        """
        按技能名称发现可用的外部 Agent。

        Args:
            skill: 技能名称（如 query_property, query_fund）

        Returns:
            匹配的 AgentCard 列表（按健康状态排序，healthy 在前）
        """
        agent_names = self._skill_index.get(skill, [])
        cards = [
            self._agents[name]
            for name in agent_names
            if name in self._agents and self._health.get(name) != AgentHealth.UNHEALTHY
        ]
        # healthy 优先
        cards.sort(key=lambda c: 0 if self._health.get(c.name) == AgentHealth.HEALTHY else 1)
        return cards

    def discover_all(self, skills: list[str]) -> dict[str, list[AgentCard]]:
        """
        按多个技能批量发现 Agent。

        Args:
            skills: 技能名称列表

        Returns:
            {skill: [AgentCard, ...], ...}
        """
        return {skill: self.discover(skill) for skill in skills}

    def get_agent(self, name: str) -> Optional[AgentCard]:
        """
        按名称获取外部 Agent。

        Args:
            name: Agent 名称

        Returns:
            AgentCard 或 None
        """
        return self._agents.get(name)

    def list_all(self) -> list[AgentCard]:
        """列出所有已注册的外部 Agent"""
        return list(self._agents.values())

    def list_skills(self) -> list[str]:
        """列出所有可用的技能"""
        return list(self._skill_index.keys())

    # ── 健康检查 ──

    def health_check(self, name: str) -> AgentHealth:
        """
        获取 Agent 健康状态。

        Args:
            name: Agent 名称

        Returns:
            健康状态（UNKNOWN 表示未注册）
        """
        return self._health.get(name, AgentHealth.UNKNOWN)

    def set_health(self, name: str, health: AgentHealth) -> None:
        """
        设置 Agent 健康状态。

        Args:
            name: Agent 名称
            health: 健康状态
        """
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' 未注册")
        old = self._health.get(name, AgentHealth.UNKNOWN)
        self._health[name] = health
        logger.info("Agent {} 健康状态: {} → {}", name, old.value, health.value)

    # ── 状态 ──

    @property
    def count(self) -> int:
        """已注册的外部 Agent 总数"""
        return len(self._agents)

    @property
    def healthy_count(self) -> int:
        """健康的 Agent 数量"""
        return sum(1 for h in self._health.values() if h == AgentHealth.HEALTHY)

    def reset(self) -> None:
        """清空所有注册"""
        self._agents.clear()
        self._health.clear()
        self._skill_index.clear()


# ============================================================
# 全局单例
# ============================================================

_registry: Optional[ExternalAgentRegistry] = None


def get_external_registry() -> ExternalAgentRegistry:
    """获取全局 ExternalAgentRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = ExternalAgentRegistry()
    return _registry


# ============================================================
# 预注册 — 初始化默认的外部 Agent
# ============================================================


def initialize_default_agents() -> ExternalAgentRegistry:
    """
    初始化默认外部 Agent 注册。

    在应用启动时调用，预注册 mock 外部 Agent。
    包含: housing_agent (不动产), fund_agent (公积金)

    端点优先读配置（A2A_HOUSING_URL / A2A_FUND_URL）：
    Docker 内指向 http://a2a-mock:12201/12202，本地默认 localhost。
    """
    registry = get_external_registry()

    # 从配置读取外部 Agent 端点（默认 localhost，适配 Docker 覆盖）
    housing_url = "http://localhost:12201"
    fund_url = "http://localhost:12202"
    try:
        from backend.config import get_settings

        settings = get_settings()
        housing_url = settings.a2a_housing_url or housing_url
        fund_url = settings.a2a_fund_url or fund_url
    except Exception:
        pass  # 配置不可用 → 使用默认 localhost

    # 不动产 Agent
    housing_card = AgentCard(
        name="housing_agent",
        display_name="不动产系统Agent",
        description="提供不动产登记查询、产权核验等服务",
        skills=["query_property", "register_property"],
        endpoint=housing_url,
        version="0.1.0",
        timeout_ms=15000,
    )
    registry.register(housing_card)
    registry.set_health("housing_agent", AgentHealth.HEALTHY)

    # 公积金 Agent
    fund_card = AgentCard(
        name="fund_agent",
        display_name="公积金系统Agent",
        description="提供公积金余额查询、提取记录查询等服务",
        skills=["query_fund", "query_fund_detail"],
        endpoint=fund_url,
        version="0.1.0",
        timeout_ms=10000,
    )
    registry.register(fund_card)
    registry.set_health("fund_agent", AgentHealth.HEALTHY)

    logger.info(
        "外部 Agent 初始化完成: {} 个 Agent 已注册, {} 种技能可用",
        registry.count, len(registry.list_skills()),
    )

    return registry


# ============================================================
# Smoke Test — python -m tools.a2a.registry
# ============================================================

if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    # ── 1. 注册 ──
    section("1. Register")
    reg = ExternalAgentRegistry()

    card1 = AgentCard(
        name="housing_agent",
        display_name="不动产系统Agent",
        skills=["query_property", "register_property"],
        endpoint="http://localhost:12201",
    )
    card2 = AgentCard(
        name="fund_agent",
        display_name="公积金系统Agent",
        skills=["query_fund", "query_fund_detail"],
        endpoint="http://localhost:12202",
    )
    reg.register(card1)
    reg.register(card2)

    check("count == 2", reg.count == 2)
    check("housing_agent registered", reg.get_agent("housing_agent") is not None)
    check("fund_agent registered", reg.get_agent("fund_agent") is not None)

    # ── 2. 发现 ──
    section("2. Discover")

    prop_agents = reg.discover("query_property")
    check("query_property → 1 agent", len(prop_agents) == 1)
    check("query_property → housing_agent", prop_agents[0].name == "housing_agent")

    fund_agents = reg.discover("query_fund")
    check("query_fund → 1 agent", len(fund_agents) == 1)
    check("query_fund → fund_agent", fund_agents[0].name == "fund_agent")

    none_agents = reg.discover("unknown_skill")
    check("unknown_skill → empty", len(none_agents) == 0)

    # 批量发现
    batch = reg.discover_all(["query_property", "query_fund", "unknown"])
    check("batch: 2 matches", len(batch["query_property"]) == 1 and len(batch["query_fund"]) == 1)
    check("batch: unknown empty", len(batch["unknown"]) == 0)

    # ── 3. 技能索引 ──
    section("3. Skills")
    skills = reg.list_skills()
    check("4 skills registered", len(skills) == 4)
    check("query_property in skills", "query_property" in skills)
    check("register_property in skills", "register_property" in skills)
    check("query_fund in skills", "query_fund" in skills)
    check("query_fund_detail in skills", "query_fund_detail" in skills)

    # ── 4. 健康检查 ──
    section("4. Health Check")
    check("default unknown", reg.health_check("housing_agent") == AgentHealth.UNKNOWN)

    reg.set_health("housing_agent", AgentHealth.HEALTHY)
    reg.set_health("fund_agent", AgentHealth.DEGRADED)
    check("housing healthy", reg.health_check("housing_agent") == AgentHealth.HEALTHY)
    check("fund degraded", reg.health_check("fund_agent") == AgentHealth.DEGRADED)
    check("healthy_count == 1", reg.healthy_count == 1)

    # health 影响 discover 排序
    reg.set_health("fund_agent", AgentHealth.HEALTHY)
    # 两个都能 query_fund_detail，但 fund_agent 是唯一提供者
    detail_agents = reg.discover("query_fund_detail")
    check("fund_agent for query_fund_detail", len(detail_agents) == 1 and detail_agents[0].name == "fund_agent")

    # unhealthy 不出现在 discover
    reg.set_health("fund_agent", AgentHealth.UNHEALTHY)
    fund_discover = reg.discover("query_fund")
    check("unhealthy agent excluded from discover", len(fund_discover) == 0)

    # ── 5. 注销 ──
    section("5. Unregister")
    reg.unregister("fund_agent")
    check("count == 1 after unregister", reg.count == 1)
    check("fund_agent removed", reg.get_agent("fund_agent") is None)
    check("query_fund skill removed", "query_fund" not in reg.list_skills())

    # ── 6. 预注册默认 Agent ──
    section("6. Initialize Default Agents")
    reg2 = ExternalAgentRegistry()
    reg2.register(AgentCard(
        name="housing_agent", display_name="不动产",
        skills=["query_property"], endpoint="http://loc:12201",
    ))
    reg2.register(AgentCard(
        name="fund_agent", display_name="公积金",
        skills=["query_fund"], endpoint="http://loc:12202",
    ))
    reg2.set_health("housing_agent", AgentHealth.HEALTHY)
    reg2.set_health("fund_agent", AgentHealth.HEALTHY)
    check("default init: 2 agents", reg2.count == 2)
    check("default init: housing healthy", reg2.health_check("housing_agent") == AgentHealth.HEALTHY)

    # ── Summary ──
    section("SUMMARY")
    total = passed + failed
    print(f"\n  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        exit(1)
    else:
        print(" — all good")
        print("\n  Run with: python -m tools.a2a.registry")
