"""
supervisor.planner - Task planner: decompose user request into sub-tasks

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement task planning and decomposition logic
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.supervisor.prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_PROMPT
from prompts.registry import get_registry
from orchestration.langgraph.state import AgentState, Task, TaskStatus, RiskLevel


# ============================================================
# Planner
# ============================================================


class Planner:
    """
    任务规划器。

    将用户自然语言需求拆解为结构化的子任务序列。
    支持LLM动态规划 + 规则兜底的混合策略：

    - LLM模式：将state上下文注入Prompt，让LLM生成JSON任务列表
    - 规则模式：LLM不可用或输出不合法时，根据intent标签直接映射到标准任务模板

    使用方式:
        planner = Planner(llm)
        tasks = await planner.plan(state)
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Args:
            llm: LangChain ChatModel，用于LLM动态规划。
                 不进则只用规则模板。
        """
        self._llm = llm

    # ── 公开接口 ──

    async def plan(self, state: AgentState) -> list[Task]:
        """
        根据当前State生成子任务列表。

        Args:
            state: 当前AgentState

        Returns:
            规划好的Task列表，按依赖关系排序
        """
        # 如果已有task_plan且都在执行中，不重复规划
        existing = state.get("task_plan", [])
        if existing and all(
            t.get("status") != TaskStatus.PENDING.value for t in existing
        ):
            return [Task.model_validate(t) for t in existing]

        # LLM模式
        if self._llm is not None:
            try:
                return await self._llm_plan(state)
            except Exception:
                pass  # fallback to rule-based

        # 规则模式（兜底）
        return self._rule_plan(state)

    async def replan_on_error(self, state: AgentState, error: str) -> list[Task]:
        """
        执行出错时重新规划，跳过失败的任务或降级处理。

        Args:
            state: 当前AgentState
            error: 错误信息

        Returns:
            重新规划后的Task列表
        """
        task_plan = state.get("task_plan", [])

        # 标记当前失败任务
        new_plan: list[dict] = []
        for t in task_plan:
            if t.get("status") == TaskStatus.RUNNING.value:
                t = {**t, "status": TaskStatus.FAILED.value}
            new_plan.append(t)

        # 如果LLM可用，尝试生成替代方案
        if self._llm is not None:
            try:
                retry_state = {**state, "task_plan": new_plan, "error": error}
                return await self._llm_plan(retry_state)
            except Exception:
                pass

        # 简单策略：跳过失败任务，继续执行后续
        return [Task.model_validate(t) for t in new_plan]

    # ── LLM规划 ──

    async def _llm_plan(self, state: AgentState) -> list[Task]:
        """使用LLM生成任务规划"""
        assert self._llm is not None

        intent_v = state.get("intent", "unknown")
        context_v = self._build_context(state)
        query_v = state.get("user_query", "")

        # Prompt Registry 优先，硬编码常量 fallback
        try:
            registry = get_registry()
            system_content = registry.render("PLANNER_SYSTEM_PROMPT", intent=intent_v, context=context_v)
            user_content = registry.render("PLANNER_USER_PROMPT", user_query=query_v)
        except Exception:
            system_content = PLANNER_SYSTEM_PROMPT.format(intent=intent_v, context=context_v)
            user_content = PLANNER_USER_PROMPT.format(user_query=query_v)

        system_msg = SystemMessage(content=system_content)
        user_msg = HumanMessage(content=user_content)

        response = await self._llm.ainvoke([system_msg, user_msg])
        content = self._extract_text(response)

        return self._parse_llm_output(content)

    def _build_context(self, state: AgentState) -> str:
        """从State中提取上下文信息，注入Prompt"""
        parts: list[str] = []

        intent = state.get("intent", "")
        if intent:
            parts.append(f"已识别意图: {intent}")

        policy = state.get("policy_result", {})
        if isinstance(policy, dict) and policy.get("answer"):
            parts.append(f"已有政策信息: {policy['answer'][:200]}")

        material = state.get("material_result", {})
        if isinstance(material, dict):
            missing = material.get("missing", [])
            if missing:
                parts.append(f"已知缺失材料: {missing}")

        task_plan = state.get("task_plan", [])
        if task_plan:
            completed = [t for t in task_plan if t.get("status") == TaskStatus.COMPLETED.value]
            failed = [t for t in task_plan if t.get("status") == TaskStatus.FAILED.value]
            if completed:
                parts.append(f"已完成 {len(completed)} 个任务")
            if failed:
                parts.append(f"有 {len(failed)} 个任务失败，需要重新规划")

        error = state.get("error", "")
        if error:
            parts.append(f"上一步错误: {error}")

        return "\n".join(parts) if parts else "无额外上下文"

    def _parse_llm_output(self, raw: str) -> list[Task]:
        """
        解析LLM输出的JSON，严格校验后返回Task列表。

        容错：如果JSON不合法，尝试提取其中的tasks数组；
        如果完全无法解析，fallback到规则模式。
        """
        # 尝试提取JSON块
        json_match = re.search(r'\{[\s\S]*"tasks"[\s\S]*\}', raw)
        if not json_match:
            raise ValueError(f"No JSON object with 'tasks' found in LLM output: {raw[:200]}")

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse JSON from LLM output: {raw[:200]}")

        tasks_data = data.get("tasks", [])
        if not tasks_data:
            raise ValueError("LLM output has empty tasks list")

        tasks: list[Task] = []
        for i, td in enumerate(tasks_data):
            if not isinstance(td, dict):
                continue
            tasks.append(Task(
                type=td.get("type", "unknown"),
                agent=td.get("agent", "policy"),
                description=td.get("description", f"Task {i+1}"),
                input=td.get("input", {}),
                dependencies=td.get("dependencies", []),
                priority=td.get("priority", 0),
            ))

        return tasks

    # ── 规则规划（兜底） ──

    def _rule_plan(self, state: AgentState) -> list[Task]:
        """
        基于intent标签的规则模板规划。

        不依赖LLM，保证基本可用性。
        根据业务场景预定义了标准任务流程。
        """
        intent = state.get("intent", "")
        user_query = state.get("user_query", "")

        # 标准流程模板
        templates: dict[str, list[dict[str, Any]]] = {
            "business_license": [
                {"type": "search_policy", "agent": "policy",
                 "description": "查询营业执照办理政策", "priority": 10},
                {"type": "check_material", "agent": "material",
                 "description": "检查所需材料是否齐全", "priority": 5},
                {"type": "create_case", "agent": "workflow",
                 "description": "创建营业执照办理件", "priority": 0},
            ],
            "restaurant_license": [
                {"type": "search_policy", "agent": "policy",
                 "description": "查询餐饮许可政策（含消防、环保要求）", "priority": 10},
                {"type": "check_material", "agent": "material",
                 "description": "检查餐饮许可申请材料", "priority": 5},
                {"type": "create_case", "agent": "workflow",
                 "description": "创建餐饮许可办理件", "priority": 0},
            ],
            "fund_query": [
                {"type": "search_policy", "agent": "policy",
                 "description": "查询公积金政策", "priority": 10},
            ],
            "property_service": [
                {"type": "search_policy", "agent": "policy",
                 "description": "查询不动产相关政策", "priority": 10},
                {"type": "check_material", "agent": "material",
                 "description": "检查不动产办理材料", "priority": 5},
            ],
            "business_register": [
                {"type": "search_policy", "agent": "policy",
                 "description": "查询企业注册政策", "priority": 10},
                {"type": "check_material", "agent": "material",
                 "description": "检查企业注册材料", "priority": 5},
                {"type": "create_case", "agent": "workflow",
                 "description": "创建企业注册办件", "priority": 0},
            ],
        }

        template = templates.get(intent)
        if not template:
            # 未知意图：做一轮通用的政策查询
            template = [
                {"type": "search_policy", "agent": "policy",
                 "description": f"查询相关政策: {user_query[:50]}", "priority": 10},
            ]

        tasks: list[Task] = []
        for td in template:
            tasks.append(Task(
                type=td["type"],
                agent=td["agent"],
                description=td.get("description", ""),
                input=td.get("input", {"query": user_query}),
                dependencies=td.get("dependencies", []),
                priority=td.get("priority", 0),
            ))

        return tasks

    # ── 工具 ──

    @staticmethod
    def _extract_text(response: Any) -> str:
        """从LangChain响应对象中提取文本"""
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, str):
            return response
        return str(response)
