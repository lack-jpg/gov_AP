"""
agents - Multi-Agent system package

Author: le
Date: 2026/7/29
Version: 0.1
Task: Agent package initialization and registry
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# AgentRegistry
# ============================================================


class AgentRegistry:
    """
    全局 Agent 注册中心。

    负责所有 Agent 的注册、发现、健康检查和生命周期管理。
    新增 Agent 只需调用 register()，无需修改任何编排层代码。

    用法:
        registry = AgentRegistry()

        # 注册
        registry.register("policy", PolicyAgent(llm=llm))

        # 获取
        agent = registry.get("policy")
        result = await agent.process(state)

        # 列表
        print(registry.list())  # ["supervisor", "intent", "policy", ...]
    """

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._status: dict[str, str] = {}
        self._metadata: dict[str, dict] = {}

    def register(
        self,
        name: str,
        agent: Any,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        注册一个 Agent。

        Args:
            name: Agent 名称（如 "policy", "intent"）
            agent: Agent 实例
            metadata: Agent 元数据（如 {version: "0.1.0", description: "..."}）
        """
        if name in self._agents:
            logger.warning("Agent {} 已注册，将被覆盖", name)

        self._agents[name] = agent
        self._status[name] = "active"
        self._metadata[name] = metadata or {}
        logger.info(
            "Agent 已注册: {} (version={})",
            name, self._metadata[name].get("version", "unknown"),
        )

    def get(self, name: str) -> Any:
        """
        获取指定 Agent 实例。

        Args:
            name: Agent 名称

        Returns:
            Agent 实例

        Raises:
            KeyError: Agent 未注册
        """
        if name not in self._agents:
            raise KeyError(
                f"Agent '{name}' 未注册。可用 Agent: {list(self._agents.keys())}"
            )
        return self._agents[name]

    def list(self) -> list[str]:
        """列出所有已注册的 Agent 名称"""
        return list(self._agents.keys())

    def list_active(self) -> list[str]:
        """列出所有活跃的 Agent 名称"""
        return [k for k, v in self._status.items() if v == "active"]

    def health_check(self, name: str) -> bool:
        """
        检查指定 Agent 是否可用。

        Args:
            name: Agent 名称

        Returns:
            True 表示 Agent 已注册且状态为 active
        """
        return name in self._agents and self._status.get(name) == "active"

    def set_status(self, name: str, status: str) -> None:
        """
        设置 Agent 状态。

        Args:
            name: Agent 名称
            status: 状态（active, inactive, testing, error）
        """
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' 未注册")
        old = self._status.get(name, "?")
        self._status[name] = status
        logger.info("Agent {} 状态变更: {} → {}", name, old, status)

    def get_metadata(self, name: str) -> dict:
        """获取 Agent 元数据"""
        return self._metadata.get(name, {})

    def unregister(self, name: str) -> None:
        """
        注销一个 Agent。

        Args:
            name: Agent 名称
        """
        if name in self._agents:
            del self._agents[name]
            self._status.pop(name, None)
            self._metadata.pop(name, None)
            logger.info("Agent 已注销: {}", name)

    def clear(self) -> None:
        """清空所有注册"""
        self._agents.clear()
        self._status.clear()
        self._metadata.clear()


# ============================================================
# 全局单例
# ============================================================

_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
