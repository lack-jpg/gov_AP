"""
backend.services.agent_service - Agent orchestration service: manage agent lifecycle and graph execution

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement agent service for LangGraph execution orchestration
"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph

from agents import get_agent_registry
from agents.intent.agent import IntentAgent
from agents.intent.classifier import IntentClassifier
from agents.policy.agent import PolicyAgent
from agents.material.agent import MaterialAgent
from agents.workflow.agent import WorkflowAgent
from agents.governance.agent import GovernanceAgent
from agents.supervisor.agent import SupervisorAgent
from orchestration.langgraph.state import AgentState, create_initial_state
from orchestration.langgraph.runtime import AgentRuntime, RuntimeConfig
from tools.logger import get_logger

logger = get_logger(__name__)


class AgentService:
    """
    Agent 编排服务 — 管理 Agent 生命周期和 Graph 执行。

    职责:
    1. 注册所有 Agent 到 AgentRegistry
    2. 构建并缓存 LangGraph StateGraph
    3. 执行 Agent 工作流（带 Runtime 安全护栏）
    4. 处理 A2A 异步任务的挂起和恢复

    使用方式:
        service = AgentService(llm=llm)
        await service.initialize()
        state = await service.execute("我要开一家餐馆", user_id="001")
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        runtime_config: Optional[RuntimeConfig] = None,
    ):
        self._llm = llm
        self._runtime_config = runtime_config or RuntimeConfig()
        self._runtime = AgentRuntime(config=self._runtime_config)
        self._graph: Optional[StateGraph] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        初始化服务:
        1. 注册所有 Agent
        2. 构建 LangGraph

        应用启动时调用一次。
        """
        if self._initialized:
            return

        registry = get_agent_registry()

        # 注册 Agent
        registry.register(
            "supervisor",
            SupervisorAgent(llm=self._llm),
            {"version": "0.1.0", "description": "全局任务编排"},
        )
        registry.register(
            "intent",
            IntentAgent(
                classifier=IntentClassifier(),
                llm=self._llm,
            ),
            {"version": "0.1.0", "description": "用户意图识别"},
        )
        registry.register(
            "policy",
            PolicyAgent(llm=self._llm),
            {"version": "0.1.0", "description": "政策知识检索"},
        )
        registry.register(
            "material",
            MaterialAgent(llm=self._llm),
            {"version": "0.1.0", "description": "材料审核"},
        )
        registry.register(
            "workflow",
            WorkflowAgent(),
            {"version": "0.1.0", "description": "流程执行"},
        )
        registry.register(
            "governance",
            GovernanceAgent(llm=self._llm),
            {"version": "0.1.0", "description": "安全治理（旁路）"},
        )

        # 构建 Graph
        from orchestration.langgraph.graph import build_graph
        self._graph = build_graph(llm=self._llm)

        self._initialized = True
        logger.info(
            "AgentService 初始化完成: {} 个 Agent 已注册",
            len(registry.list()),
        )

    async def execute(
        self,
        user_query: str,
        user_id: str = "anonymous",
        trace_id: Optional[str] = None,
    ) -> AgentState:
        """
        执行一次完整的 Agent 工作流。

        Args:
            user_query: 用户输入
            user_id: 用户 ID
            trace_id: 链路追踪 ID

        Returns:
            最终 AgentState
        """
        if not self._initialized:
            await self.initialize()

        assert self._graph is not None

        state = create_initial_state(
            user_query=user_query,
            trace_id=trace_id,
        )

        config = {"configurable": {"thread_id": state["trace_id"], "user_id": user_id}}

        self._runtime.reset()
        result = await self._runtime.execute_with_safeguards(
            self._graph, state, graph_config=config
        )

        logger.info(
            "Agent 执行完成: trace_id={} steps={} answer_len={}",
            state["trace_id"],
            self._runtime.step_count,
            len(result.get("final_answer", "")),
        )

        return result

    async def resume_from_checkpoint(
        self,
        checkpoint_id: str,
        a2a_result: dict[str, Any],
    ) -> AgentState:
        """
        从 Checkpoint 恢复 A2A 挂起的流程。

        Args:
            checkpoint_id: Checkpoint ID
            a2a_result: 外部 Agent 返回的结果

        Returns:
            最终 AgentState
        """
        if not self._initialized:
            await self.initialize()

        assert self._graph is not None

        try:
            from orchestration.langgraph.checkpointer import PostgresCheckpointer

            checkpointer = PostgresCheckpointer()
            checkpoint_tuple = await checkpointer.aget_tuple({
                "configurable": {"checkpoint_id": checkpoint_id}
            })

            if checkpoint_tuple is None:
                logger.warning("Checkpoint {} 未找到，以新请求模式执行", checkpoint_id)
                return create_initial_state(user_query="resumed")

            # 从 checkpoint 恢复 state
            checkpoint_state = checkpoint_tuple.checkpoint.get("channel_values", {})

            # 注入 external_result
            resumed_state = {
                **checkpoint_state,
                "external_result": a2a_result,
                "waiting_task_id": "",
            }

            # 恢复执行
            config = checkpoint_tuple.config
            config["configurable"]["resumed_from_checkpoint"] = True

            result = await self._graph.ainvoke(resumed_state, config=config)

            logger.info(
                "A2A 恢复完成: checkpoint={}, answer_len={}",
                checkpoint_id,
                len(result.get("final_answer", "")),
            )

            return result

        except ImportError:
            logger.warning("Checkpointer 不可用，A2A 恢复以 stub 模式执行")
            return create_initial_state(user_query="resumed")
        except Exception as e:
            logger.error("A2A 恢复失败: checkpoint={} — {}", checkpoint_id, e)
            return create_initial_state(user_query="resumed")

    def get_graph(self) -> StateGraph:
        """获取已编译的 LangGraph（需先 initialize）"""
        if self._graph is None:
            raise RuntimeError("AgentService 未初始化，请先调用 initialize()")
        return self._graph
