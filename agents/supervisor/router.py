"""
supervisor.router - Agent router: route tasks to appropriate specialist agents

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement agent routing and selection logic
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.supervisor.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_PROMPT
from orchestration.langgraph.state import AgentName, Task


# ============================================================
# 路由表 — 任务类型 → Agent 映射
# ============================================================

ROUTING_TABLE: dict[str, AgentName] = {
    # Intent
    "classify_intent": AgentName.INTENT,
    "recognize_intent": AgentName.INTENT,
    # Policy
    "search_policy": AgentName.POLICY,
    "get_policy_detail": AgentName.POLICY,
    "query_policy": AgentName.POLICY,
    "rag_search": AgentName.POLICY,
    # Material
    "check_material": AgentName.MATERIAL,
    "extract_entity": AgentName.MATERIAL,
    "validate_material": AgentName.MATERIAL,
    "ocr_scan": AgentName.MATERIAL,
    # Workflow
    "create_case": AgentName.WORKFLOW,
    "query_status": AgentName.WORKFLOW,
    "submit_case": AgentName.WORKFLOW,
    "execute_workflow": AgentName.WORKFLOW,
}


# ============================================================
# Router
# ============================================================


class Router:
    """
    Agent路由器。

    根据任务类型将Task路由到最合适的专业Agent。
    支持规则表匹配 + LLM兜底的混合策略：

    - 规则模式：查询 ROUTING_TABLE，O(1)匹配
    - LLM模式：任务类型不在表中时，让LLM判断最合适的Agent
    - 兜底模式：所有判断失败时返回supivisor（人工介入）

    使用方式:
        router = Router(llm)
        agent_name = await router.route(task)
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Args:
            llm: LangChain ChatModel，用于LLM动态路由。
                 不进则只用规则表。
        """
        self._llm = llm

    # ── 公开接口 ──

    async def route(self, task: Task) -> AgentName:
        """
        将Task路由到最合适的Agent。

        Args:
            task: 要路由的子任务

        Returns:
            目标Agent名称
        """
        task_type = task.type.lower().strip()

        # 1. 规则表精确匹配
        if task_type in ROUTING_TABLE:
            return ROUTING_TABLE[task_type]

        # 2. 模糊匹配（子串）
        for key, agent in ROUTING_TABLE.items():
            if key in task_type or task_type in key:
                return agent

        # 3. LLM判断
        if self._llm is not None:
            try:
                return await self._llm_route(task)
            except Exception:
                pass

        # 4. 类型推断（基于task_type关键词）
        inferred = self._infer_by_keyword(task_type)
        if inferred is not None:
            return inferred

        # 5. 兜底 → Supervisor（人工介入）
        return AgentName.SUPERVISOR

    async def route_batch(self, tasks: list[Task]) -> dict[str, AgentName]:
        """
        批量路由，返回 {task_id: agent_name}。

        Args:
            tasks: 子任务列表

        Returns:
            {task.id: AgentName} 映射
        """
        result: dict[str, AgentName] = {}
        for task in tasks:
            result[task.id] = await self.route(task)
        return result

    # ── LLM路由 ──

    async def _llm_route(self, task: Task) -> AgentName:
        """使用LLM判断任务应该路由到哪个Agent"""
        assert self._llm is not None

        system_msg = SystemMessage(content=ROUTER_SYSTEM_PROMPT)
        user_msg = HumanMessage(content=ROUTER_USER_PROMPT.format(
            task_type=task.type,
            task_description=task.description or "无描述",
        ))

        response = await self._llm.ainvoke([system_msg, user_msg])
        content = self._extract_text(response)

        # 解析LLM输出
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                agent_str = data.get("agent", "").lower().strip()
                return self._normalize_agent_name(agent_str)
            except (json.JSONDecodeError, KeyError):
                pass

        # 无法解析 → 从原始文本提取agent名
        return self._normalize_agent_name(content.lower().strip())

    # ── 关键词推断 ──

    @staticmethod
    def _infer_by_keyword(task_type: str) -> Optional[AgentName]:
        """基于task_type中的关键词推断Agent"""
        if any(kw in task_type for kw in ("policy", "政策", "法规", "search", "查询", "检索")):
            return AgentName.POLICY
        if any(kw in task_type for kw in ("material", "材料", "check", "审核", "extract", "ocr")):
            return AgentName.MATERIAL
        if any(kw in task_type for kw in ("case", "办件", "create", "submit", "workflow", "流程")):
            return AgentName.WORKFLOW
        if any(kw in task_type for kw in ("intent", "意图", "classify", "识别")):
            return AgentName.INTENT
        return None

    # ── 归一化 ──

    @staticmethod
    def _normalize_agent_name(raw: str) -> AgentName:
        """将原始字符串归一化为AgentName枚举"""
        raw = raw.lower().strip()
        for agent in AgentName:
            if agent.value in raw:
                return agent
        # 无法归一化 → 返回supervisor
        return AgentName.SUPERVISOR

    # ── 工具 ──

    @staticmethod
    def _extract_text(response: Any) -> str:
        """从LangChain响应对象中提取文本"""
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, str):
            return response
        return str(response)
