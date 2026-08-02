"""
prompts.registry - Prompt Registry: versioned prompt templates for all agents

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement Prompt Registry with version control and runtime loading
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ============================================================
# PromptTemplate
# ============================================================


@dataclass
class PromptTemplate:
    """
    版本化的 Prompt 模板。

    结构:
        Role: 角色定义
        Goal: 任务目标
        Constraints: 约束规则
        Tools: 可用工具描述
        Output Schema: 输出格式定义
        Examples: 示例（Few-shot）
    """
    name: str                              # 模板名称: SUPERVISOR_SYSTEM_PROMPT 等
    agent_name: str                        # 关联 Agent: supervisor | intent | policy | material | workflow | governance
    version: str = "v1"                    # 版本号
    role: str = ""                         # 角色
    goal: str = ""                         # 目标
    constraints: str = ""                  # 约束
    tools: str = ""                        # 可用工具
    output_schema: str = ""                # 输出格式
    examples: str = ""                     # 示例（空格分隔）
    variables: list[str] = field(default_factory=list)  # 模板变量名
    is_active: bool = True                 # 是否为活跃版本
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def render(self, **kwargs: Any) -> str:
        """
        使用变量渲染 Prompt 模板。

        支持 Jinja2 风格变量: {{ variable_name }}

        Args:
            **kwargs: 变量值

        Returns:
            渲染后的完整 Prompt 文本
        """
        # 构建各部分
        sections: list[str] = []

        if self.role:
            sections.append(f"# 角色定义\n{self._substitute(self.role, **kwargs)}")

        if self.goal:
            sections.append(f"# 任务目标\n{self._substitute(self.goal, **kwargs)}")

        if self.constraints:
            sections.append(f"# 约束规则\n{self._substitute(self.constraints, **kwargs)}")

        if self.tools:
            sections.append(f"# 可用工具\n{self._substitute(self.tools, **kwargs)}")

        if self.output_schema:
            sections.append(f"# 输出格式\n{self._substitute(self.output_schema, **kwargs)}")

        if self.examples:
            sections.append(f"# 示例\n{self._substitute(self.examples, **kwargs)}")

        return "\n\n".join(sections)

    def render_with_content(self, content: str, **kwargs: Any) -> str:
        """
        使用变量渲染完整 Prompt（包含模板正文）。

        Args:
            content: 模板正文（可含 {{ var }} 变量）
            **kwargs: 变量值

        Returns:
            渲染后的完整 Prompt 文本
        """
        rendered_content = self._substitute(content, **kwargs)
        sections = self.render(**kwargs)
        if sections:
            return sections + "\n\n# 指令\n" + rendered_content
        return rendered_content

    @staticmethod
    def _substitute(text: str, **kwargs: Any) -> str:
        """替换 {{ var }} 风格的变量"""
        def replacer(match: re.Match) -> str:
            var_name = match.group(1).strip()
            if var_name in kwargs:
                return str(kwargs[var_name])
            # 未提供变量时保留原样
            return match.group(0)
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent_name": self.agent_name,
            "version": self.version,
            "role": self.role,
            "goal": self.goal,
            "constraints": self.constraints,
            "tools": self.tools,
            "output_schema": self.output_schema,
            "examples": self.examples,
            "variables": self.variables,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    def to_db_dict(self) -> dict[str, Any]:
        """转为数据库 Prompt 模型兼容的字典"""
        return {
            "agent_name": self.agent_name,
            "name": self.name,
            "version": self.version,
            "content": self.render(),
            "variables": self.variables,
            "is_active": self.is_active,
            "created_by": self.created_by,
        }


# ============================================================
# PromptRegistry
# ============================================================


class PromptRegistry:
    """
    Prompt 注册中心 — 管理所有 Agent 的 Prompt 模板版本。

    功能:
    - register(): 注册新模板版本
    - get(): 获取指定版本
    - get_active(): 获取当前活跃版本
    - list_versions(): 列出所有版本
    - activate_version(): 激活指定版本（同时停用其他版本）
    - render(): 渲染 Prompt

    用法:
        registry = PromptRegistry()
        registry.register(template)
        prompt_text = registry.render("SUPERVISOR_SYSTEM_PROMPT", user_query="...")
    """

    def __init__(self) -> None:
        # name -> list of PromptTemplate (按版本排序)
        self._templates: dict[str, list[PromptTemplate]] = {}
        self._preload_defaults()

    # ── 注册 ──

    def register(self, template: PromptTemplate) -> PromptTemplate:
        """
        注册一个 Prompt 模板。

        如果同名同版本的模板已存在，则覆盖更新。

        Args:
            template: PromptTemplate 实例

        Returns:
            注册后的 PromptTemplate
        """
        name = template.name
        if name not in self._templates:
            self._templates[name] = []

        # 检查是否已有同版本
        existing = None
        for i, t in enumerate(self._templates[name]):
            if t.version == template.version:
                existing = i
                break

        if existing is not None:
            self._templates[name][existing] = template
        else:
            self._templates[name].append(template)

        return template

    # ── 查询 ──

    def get(self, name: str, version: str | None = None) -> PromptTemplate | None:
        """
        获取指定 Prompt 模板。

        Args:
            name: 模板名称
            version: 版本号，None 时返回活跃版本

        Returns:
            PromptTemplate 或 None
        """
        templates = self._templates.get(name, [])

        if not templates:
            return None

        if version:
            for t in templates:
                if t.version == version:
                    return t
            return None

        # 返回活跃版本
        return self.get_active(name)

    def get_active(self, name: str) -> PromptTemplate | None:
        """
        获取当前活跃版本的 Prompt 模板。

        Args:
            name: 模板名称

        Returns:
            活跃的 PromptTemplate 或 None
        """
        templates = self._templates.get(name, [])
        for t in templates:
            if t.is_active:
                return t
        # 如果没有活跃版本，返回最新版本
        if templates:
            return sorted(templates, key=lambda t: t.version)[-1]
        return None

    def list_versions(self, name: str) -> list[str]:
        """
        列出指定模板的所有版本。

        Args:
            name: 模板名称

        Returns:
            版本号列表（排序）
        """
        templates = self._templates.get(name, [])
        return sorted([t.version for t in templates])

    def list_all(self) -> dict[str, list[str]]:
        """
        列出所有模板及版本。

        Returns:
            {name: [version, ...]}
        """
        return {name: self.list_versions(name) for name in self._templates}

    def list_by_agent(self, agent_name: str) -> list[PromptTemplate]:
        """
        列出指定 Agent 的所有模板（含所有版本）。

        Args:
            agent_name: Agent 名称

        Returns:
            PromptTemplate 列表
        """
        result: list[PromptTemplate] = []
        for templates in self._templates.values():
            for t in templates:
                if t.agent_name == agent_name:
                    result.append(t)
        return result

    # ── 版本管理 ──

    def activate_version(self, name: str, version: str) -> bool:
        """
        激活指定版本的模板（同时停用其他版本）。

        Args:
            name: 模板名称
            version: 要激活的版本号

        Returns:
            是否成功
        """
        templates = self._templates.get(name, [])
        if not templates:
            return False

        target = None
        for t in templates:
            if t.version == version:
                target = t
            t.is_active = False

        if target is not None:
            target.is_active = True
            return True
        return False

    def deactivate(self, name: str) -> bool:
        """
        停用指定模板的所有版本。

        Args:
            name: 模板名称

        Returns:
            是否成功
        """
        templates = self._templates.get(name, [])
        if not templates:
            return False
        for t in templates:
            t.is_active = False
        return True

    # ── 渲染 ──

    def render(
        self, name: str, version: str | None = None, **kwargs: Any
    ) -> str:
        """
        渲染指定 Prompt 模板。

        Args:
            name: 模板名称
            version: 版本号，None 使用活跃版本
            **kwargs: 模板变量

        Returns:
            渲染后的 Prompt 文本

        Raises:
            ValueError: 模板不存在
        """
        template = self.get(name, version=version)
        if template is None:
            raise ValueError(f"Prompt template not found: {name} (version={version or 'active'})")
        return template.render(**kwargs)

    # ── 持久化 ──

    async def flush_to_db(self, name: str | None = None) -> int:
        """
        将模板写入数据库 Prompt 表。

        Args:
            name: 可选，仅写入指定模板

        Returns:
            写入的记录数
        """
        templates_to_save: list[PromptTemplate] = []
        if name:
            templates_to_save = self._templates.get(name, [])
        else:
            for ts in self._templates.values():
                templates_to_save.extend(ts)

        if not templates_to_save:
            return 0

        try:
            from database.connection import get_session_factory
            from database.models import Prompt

            session_factory = get_session_factory()
            async with session_factory() as session:
                for t in templates_to_save:
                    prompt = Prompt(**t.to_db_dict())
                    session.add(prompt)
                await session.commit()
            return len(templates_to_save)
        except Exception:
            return 0

    async def load_from_db(self) -> int:
        """
        从数据库加载 Prompt 模板到注册中心。

        Returns:
            加载的记录数
        """
        try:
            from database.connection import get_session_factory
            from database.models import Prompt
            from sqlalchemy import select

            session_factory = get_session_factory()
            async with session_factory() as session:
                result = await session.execute(select(Prompt))
                rows = result.scalars().all()

                count = 0
                for row in rows:
                    template = PromptTemplate(
                        name=row.name,
                        agent_name=row.agent_name,
                        version=row.version,
                        variables=row.variables or [],
                        is_active=row.is_active,
                        created_by=row.created_by or "system",
                    )
                    self.register(template)
                    count += 1
                return count
        except Exception:
            return 0

    # ── 预置模板 ──

    def _preload_defaults(self) -> None:
        """加载所有 Agent 的默认 Prompt 模板"""
        defaults = [
            # ── Supervisor ──
            PromptTemplate(
                name="SUPERVISOR_SYSTEM_PROMPT",
                agent_name="supervisor",
                version="v1",
                role="你是政务多智能体协同平台的Supervisor Agent，负责理解用户需求、拆解任务、协调多个专业Agent协同工作。",
                goal="根据用户请求 {{ user_query }}，将复杂任务拆解为子任务，并分配给最合适的专业Agent执行。\n\n意图分析结果: {{ intent }}",
                constraints=(
                    "1. 不要执行具体的业务逻辑，只做任务理解和分配。\n"
                    "2. 每个子任务必须有明确的目标、输入和预期输出。\n"
                    "3. 如果用户请求不明确，先澄清再规划。\n"
                    "4. 任务计划不超过5个子任务。\n"
                    "5. 对于高风险操作，需标记风险等级。"
                ),
                tools="可用Agent: intent_agent(意图识别), policy_agent(政策查询), material_agent(材料审核), workflow_agent(流程执行)",
                output_schema=(
                    "输出 JSON 格式:\n"
                    '{"plan": [{"task_id": "...", "agent": "...", "goal": "...", "input": {...}, "expected_output": "..."}], '
                    '"risk_level": "low|medium|high"}'
                ),
                examples=(
                    "用户: 我想开一家餐饮店\n"
                    "Supervisor: {\"plan\": ["
                    "{\"task_id\": \"1\", \"agent\": \"intent_agent\", \"goal\": \"识别用户意图\", ...}, "
                    "{\"task_id\": \"2\", \"agent\": \"policy_agent\", \"goal\": \"查询餐饮店开办政策\", ...}, "
                    "{\"task_id\": \"3\", \"agent\": \"material_agent\", \"goal\": \"列出所需材料清单\", ...}"
                    "], \"risk_level\": \"low\"}"
                ),
                variables=["user_query", "intent"],
            ),

            # ── Intent ──
            PromptTemplate(
                name="INTENT_CLASSIFIER_PROMPT",
                agent_name="intent",
                version="v1",
                role="你是政务意图分类Agent，负责将用户自然语言描述精准映射到标准政务事项分类。",
                goal="分析用户请求 '{{ user_query }}'，识别其对应的政务办理意图标签。",
                constraints=(
                    "1. 只输出意图标签，不要额外解释。\n"
                    "2. 如果无法确定意图，返回 'unknown'。\n"
                    "3. 支持模糊匹配，如'开饭店'→'business_license'。"
                ),
                tools="BERT分类器 + 关键词匹配",
                output_schema="{\"intent\": \"business_license\", \"confidence\": 0.95}",
                examples=(
                    "开餐饮店 → business_license\n"
                    "查询公积金 → fund_query\n"
                    "办理房产证 → property_certificate\n"
                    "营业执照变更 → business_license_change"
                ),
                variables=["user_query", "context"],
            ),

            # ── Policy ──
            PromptTemplate(
                name="POLICY_RAG_PROMPT",
                agent_name="policy",
                version="v1",
                role="你是政务政策咨询Agent，基于RAG检索到的政策文档，为用户提供准确、有据可查的政策解答。",
                goal="基于以下政策上下文:\n{{ context }}\n\n回答用户的政策咨询问题: {{ user_query }}",
                constraints=(
                    "1. 回答必须基于提供的上下文证据，不得编造。\n"
                    "2. 每条回答需引用具体的政策条款原文。\n"
                    "3. 如果上下文不足以回答，明确说明并提供建议。\n"
                    "4. 使用政务正式用语，但保持通俗易懂。\n"
                    "5. 涉及时间、金额等关键信息，必须准确。"
                ),
                tools="search_policy(keyword, category, region) — 在 Milvus + BM25 中检索政策",
                output_schema=(
                    '{"answer": "...", "evidence": [{"source": "...", "clause": "...", "content": "..."}], '
                    '"confidence": 0.0~1.0}'
                ),
                examples=(
                    "问: 开办餐饮店需要哪些许可证？\n"
                    "答: 根据《食品经营许可管理办法》第X条，开办餐饮店需要办理: 1.营业执照 2.食品经营许可证 3.消防安全检查合格证..."
                ),
                variables=["user_query", "context"],
            ),

            # ── Material ──
            PromptTemplate(
                name="MATERIAL_EXTRACTOR_PROMPT",
                agent_name="material",
                version="v1",
                role="你是材料审核Agent，负责从用户提交的材料图片/文档中提取关键字段，并进行合规性校验。",
                goal="从材料中提取关键实体字段，并对照 {{ requirement }} 进行合规性检查。",
                constraints=(
                    "1. OCR提取的字段必须保留原始格式。\n"
                    "2. 对身份证号、手机号等PII必须脱敏处理。\n"
                    "3. 证件有效期、颁发日期等时间字段需校验是否过期。\n"
                    "4. 校验不通过时，明确标注原因。"
                ),
                tools="extract_entity(image) — OCR + NER 字段抽取; check_material(entity, rules) — 规则校验",
                output_schema=(
                    '{"entities": {"name": "...", "id_card": "110***********1234", ...}, '
                    '"validation": {"passed": true, "issues": []}}'
                ),
                examples=(
                    "输入: 营业执照图片\n"
                    "输出: {\"entities\": {\"company_name\": \"XX餐饮有限公司\", \"credit_code\": \"91110000XXXXXXXXXX\", "
                    "\"legal_person\": \"张三\", \"valid_until\": \"2030-12-31\"}, \"validation\": {\"passed\": true}}"
                ),
                variables=["requirement"],
            ),

            # ── Workflow ──
            PromptTemplate(
                name="WORKFLOW_EXECUTOR_PROMPT",
                agent_name="workflow",
                version="v1",
                role="你是流程执行Agent，负责根据任务计划执行实际政务办理步骤，调用MCP工具完成具体操作。",
                goal="执行任务计划中的步骤，每个步骤完成后记录结果。当前步骤: {{ current_step }}",
                constraints=(
                    "1. 严格按照任务计划的步骤执行，不可跳过或自行添加。\n"
                    "2. 每个工具调用后，检查返回结果的正确性。\n"
                    "3. 如果工具调用失败，记录失败原因并尝试替代方案。\n"
                    "4. 步骤全部完成后，汇总执行结果。"
                ),
                tools=(
                    "create_case(type, data) — 创建政务流程实例; "
                    "query_status(case_id) — 查询流程状态; "
                    "submit_material(case_id, materials) — 提交材料"
                ),
                output_schema=(
                    '{"step_result": {"status": "completed|failed", "output": {...}, "next_step": "..."}, '
                    '"case_id": "..."}'
                ),
                examples=(
                    "步骤: 创建营业执照申请流程\n"
                    "调用: create_case(type='business_license', data={...}) → {\"case_id\": \"CASE-2026-001\"}\n"
                    "结果: {\"step_result\": {\"status\": \"completed\", \"case_id\": \"CASE-2026-001\"}}"
                ),
                variables=["current_step", "task_plan"],
            ),

            # ── Governance ──
            PromptTemplate(
                name="GOVERNANCE_MONITOR_PROMPT",
                agent_name="governance",
                version="v1",
                role="你是治理Agent，负责监控所有Agent的执行行为，检测风险、异常和性能问题。",
                goal="分析 Agent 执行日志，检测异常行为并生成治理报告。当前分析对象: {{ target_agent }}",
                constraints=(
                    "1. 不能参与业务流程的回答。\n"
                    "2. 分析结果只报告给系统管理员。\n"
                    "3. 对风险检测，必须提供具体证据。\n"
                    "4. 自动优化建议必须安全可控，不直接修改Agent配置。"
                ),
                tools=(
                    "无直接工具调用；通过 TraceRecorder 和 MetricsCollector 获取监控数据"
                ),
                output_schema=(
                    '{"risk_level": "low|medium|high|critical", "anomalies": [...], '
                    '"recommendations": [...]}'
                ),
                examples=(
                    "目标: supervisor Agent\n"
                    "监控发现: 最近10次调用中，2次超时(>30s)，1次工具选择错误。\n"
                    "建议: 增加 supervisor 超时时间至45s, 优化工具描述以减少误选。"
                ),
                variables=["target_agent", "trace_data"],
            ),

            # ── Planner (Supervisor 子模块) ──
            PromptTemplate(
                name="PLANNER_SYSTEM_PROMPT",
                agent_name="supervisor",
                version="v1",
                role="你是任务规划专家，负责将用户自然语言需求拆解为结构化的子任务序列。",
                goal="根据用户意图 '{{ intent }}' 和已有上下文信息，将任务拆解为可执行的子任务。\n\n已有信息: {{ context }}",
                constraints=(
                    "1. 从抽象到具体: 先识别意图，再查政策，再核材料，最后执行。\n"
                    "2. 考虑依赖: 后一步需要的输入必须由前一步产生。\n"
                    "3. 最小粒度: 一个子任务只做一件事。\n"
                    "4. 可验证: 每个子任务有明确的完成标准。"
                ),
                tools="支持的任务类型: search_policy(政策检索), check_material(材料审核), create_case(创建办件), query_status(查询进度), classify_intent(意图分类)",
                output_schema=(
                    "输出 JSON 格式:\n"
                    '{"reasoning": "拆解思路", "tasks": [{"type": "...", "agent": "...", '
                    '"description": "...", "input": {}, "dependencies": [], "priority": 0}]}'
                ),
                examples=(
                    "意图: 开餐饮店\n"
                    "拆解: 1.classify_intent→intent 2.search_policy→policy 3.check_material→material 4.create_case→workflow\n"
                    "输出: {\"tasks\": [{\"type\": \"classify_intent\", \"agent\": \"intent\", ...}, ...]}"
                ),
                variables=["intent", "context"],
            ),
            PromptTemplate(
                name="PLANNER_USER_PROMPT",
                agent_name="supervisor",
                version="v1",
                role="任务规划请求",
                goal="用户诉求: {{ user_query }}\n\n请将该诉求拆解为可执行的子任务序列，标注每个任务的依赖关系和优先级。",
                constraints="",
                tools="",
                output_schema="返回 JSON 任务列表",
                examples="",
                variables=["user_query"],
            ),

            # ── Router (Supervisor 子模块) ──
            PromptTemplate(
                name="ROUTER_SYSTEM_PROMPT",
                agent_name="supervisor",
                version="v1",
                role="你是Agent路由器，负责根据任务类型选择最合适的专业Agent。",
                goal="根据任务类型从以下路由表中匹配最合适的Agent:\n"
                     "| classify_intent | intent |\n"
                     "| search_policy, get_policy_detail | policy |\n"
                     "| check_material, extract_entity | material |\n"
                     "| create_case, query_status | workflow |",
                constraints=(
                    "1. 一个任务只路由到一个Agent。\n"
                    "2. 如果任务类型不在表中，选择最相近的Agent。\n"
                    "3. 如果完全无法判断，返回 supervisor（让人工介入）。"
                ),
                tools="",
                output_schema='{"agent": "policy|material|workflow|intent|supervisor", "reason": "路由理由"}',
                examples="任务类型: search_policy → 路由到 policy Agent",
                variables=[],
            ),
            PromptTemplate(
                name="ROUTER_USER_PROMPT",
                agent_name="supervisor",
                version="v1",
                role="路由请求",
                goal="任务类型: {{ task_type }}\n任务描述: {{ task_description }}\n\n请选择最合适的Agent。",
                constraints="",
                tools="",
                output_schema='{"agent": "...", "reason": "..."}',
                examples="",
                variables=["task_type", "task_description"],
            ),
        ]

        for t in defaults:
            self.register(t)


# ============================================================
# 全局单例
# ============================================================


_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry:
    """获取全局 PromptRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


def reset_registry() -> None:
    """重置全局 PromptRegistry（测试用）"""
    global _registry
    _registry = PromptRegistry()


# ============================================================
# 便捷函数
# ============================================================


def get_prompt(name: str, version: str | None = None) -> str:
    """
    获取渲染后的 Prompt（便捷函数）。

    Args:
        name: 模板名称
        version: 版本号，None 使用活跃版本

    Returns:
        渲染后的 Prompt 文本
    """
    registry = get_registry()
    return registry.render(name, version=version)


def get_prompt_with_vars(name: str, version: str | None = None, **kwargs: Any) -> str:
    """
    获取带变量替换的渲染 Prompt。

    Args:
        name: 模板名称
        version: 版本号
        **kwargs: 模板变量

    Returns:
        渲染后的 Prompt 文本
    """
    registry = get_registry()
    return registry.render(name, version=version, **kwargs)


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

    async def run_tests():
        global passed, failed
        print("=== prompts.registry smoke test ===")

        # ── PromptTemplate ──
        print("--- PromptTemplate ---")
        pt = PromptTemplate(
            name="TEST_PROMPT",
            agent_name="test_agent",
            version="v1",
            role="你是测试助手{{ role_name }}",
            goal="帮助用户完成任务: {{ task }}",
            constraints="1. 保持简洁\n2. 不要编造",
            tools="test_tool(param)",
            output_schema='{"result": "..."}',
            examples="示例: 输入A → 输出B",
            variables=["role_name", "task"],
        )

        check("pt_name", pt.name, "TEST_PROMPT")
        check("pt_agent", pt.agent_name, "test_agent")
        check("pt_version", pt.version, "v1")
        check("pt_active", pt.is_active, True)
        check("pt_vars", pt.variables, ["role_name", "task"])

        # Render
        rendered = pt.render(role_name="QA测试", task="验证功能")
        check("render_has_role", "# 角色定义" in rendered, True)
        check("render_role_value", "QA测试" in rendered, True)
        check("render_has_goal", "# 任务目标" in rendered, True)
        check("render_task_value", "验证功能" in rendered, True)
        check("render_has_constraints", "# 约束规则" in rendered, True)
        check("render_has_tools", "# 可用工具" in rendered, True)
        check("render_has_schema", "# 输出格式" in rendered, True)
        check("render_has_examples", "# 示例" in rendered, True)

        # Render without vars (keep placeholders)
        rendered_raw = pt.render()
        check("render_raw_placeholder", "{{ role_name }}" in rendered_raw, True)
        check("render_raw_task", "{{ task }}" in rendered_raw, True)

        # render_with_content
        content_text = "请根据以下信息回答: {{ info }}"
        full = pt.render_with_content(content_text, role_name="助手", task="查询", info="测试信息")
        check("full_has_sections", "# 角色定义" in full, True)
        check("full_has_content", "# 指令" in full, True)
        check("full_content_value", "测试信息" in full, True)

        # to_dict
        d = pt.to_dict()
        check("dict_name", d["name"], "TEST_PROMPT")
        check("dict_vars", d["variables"], ["role_name", "task"])

        # to_db_dict
        dbd = pt.to_db_dict()
        check("db_agent", dbd["agent_name"], "test_agent")
        check("db_active", dbd["is_active"], True)

        # ── PromptRegistry ──
        print("--- PromptRegistry ---")
        reset_registry()
        registry = get_registry()

        # All defaults loaded
        check("reg_has_supervisor", registry.get("SUPERVISOR_SYSTEM_PROMPT") is not None, True)
        check("reg_has_intent", registry.get("INTENT_CLASSIFIER_PROMPT") is not None, True)
        check("reg_has_policy", registry.get("POLICY_RAG_PROMPT") is not None, True)
        check("reg_has_material", registry.get("MATERIAL_EXTRACTOR_PROMPT") is not None, True)
        check("reg_has_workflow", registry.get("WORKFLOW_EXECUTOR_PROMPT") is not None, True)
        check("reg_has_governance", registry.get("GOVERNANCE_MONITOR_PROMPT") is not None, True)

        # Get active
        active = registry.get_active("SUPERVISOR_SYSTEM_PROMPT")
        check("active_not_none", active is not None, True)
        if active:
            check("active_version", active.version, "v1")

        # Get by name
        tmpl = registry.get("SUPERVISOR_SYSTEM_PROMPT")
        check("get_returns", tmpl is not None, True)

        # List versions
        versions = registry.list_versions("SUPERVISOR_SYSTEM_PROMPT")
        check("versions_len", len(versions), 1)
        check("versions_v1", "v1" in versions, True)

        # List all
        all_templates = registry.list_all()
        check("all_count", len(all_templates), 6)

        # List by agent
        policy_templates = registry.list_by_agent("policy")
        check("policy_list", len(policy_templates), 1)

        # ── Version management ──
        print("--- Version management ---")
        # Register v2
        v2 = PromptTemplate(
            name="SUPERVISOR_SYSTEM_PROMPT",
            agent_name="supervisor",
            version="v2",
            role="你是Supervisor Agent v2",
            goal="增强版任务拆解",
        )
        registry.register(v2)
        check("v2_registered", len(registry.list_versions("SUPERVISOR_SYSTEM_PROMPT")), 2)

        # Activate v2
        success = registry.activate_version("SUPERVISOR_SYSTEM_PROMPT", "v2")
        check("activate_success", success, True)

        active_after = registry.get_active("SUPERVISOR_SYSTEM_PROMPT")
        check("active_now_v2", active_after is not None and active_after.version == "v2", True)

        # v1 should be inactive
        v1_tmpl = registry.get("SUPERVISOR_SYSTEM_PROMPT", version="v1")
        check("v1_inactive", v1_tmpl.is_active if v1_tmpl else "N/A", False)

        # Deactivate all
        registry.deactivate("SUPERVISOR_SYSTEM_PROMPT")
        active_deact = registry.get_active("SUPERVISOR_SYSTEM_PROMPT")
        # Should return latest version since all are inactive
        check("deactivate_all_inactive", active_deact is not None, True)

        # Activate v1 again
        registry.activate_version("SUPERVISOR_SYSTEM_PROMPT", "v1")
        check("reactivate_v1", registry.get_active("SUPERVISOR_SYSTEM_PROMPT").version, "v1")

        # ── Render ──
        print("--- Render ---")
        result = registry.render("SUPERVISOR_SYSTEM_PROMPT", user_query="我想开一家餐馆", intent="business_license")
        check("render_reg_role", "# 角色定义" in result, True)
        check("render_reg_query", "我想开一家餐馆" in result, True)
        check("render_reg_intent", "business_license" in result, True)

        # Missing template
        try:
            registry.render("NONEXISTENT")
            check("missing_error", False, True)  # should not reach here
        except ValueError:
            check("missing_error", True, True)

        # ── Convenience functions ──
        print("--- Convenience ---")
        reset_registry()
        prompt = get_prompt("INTENT_CLASSIFIER_PROMPT")
        check("conv_prompt_non_empty", len(prompt) > 0, True)
        check("conv_prompt_has_role", "# 角色定义" in prompt, True)

        prompt_vars = get_prompt_with_vars("POLICY_RAG_PROMPT", user_query="如何查询公积金", context="《公积金管理条例》第X条...")
        check("conv_vars_has_query", "如何查询公积金" in prompt_vars, True)
        check("conv_vars_has_context", "《公积金管理条例》" in prompt_vars, True)

        # ── Summary ──
        total = passed + failed
        print(f"\n=== {passed}/{total} passed, {failed} failed ===")
        if failed > 0:
            raise SystemExit(1)

    asyncio.run(run_tests())
