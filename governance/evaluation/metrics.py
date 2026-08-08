"""
governance.evaluation.metrics - Evaluation metrics: faithfulness, answer relevance, context recall,
task success rate, tool accuracy, latency, step count

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement all RAG and Agent evaluation metric calculations
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

# ============================================================
# Data Classes
# ============================================================


@dataclass
class RAGMetricResult:
    """RAG 评测指标结果"""

    faithfulness: float = 0.0          # 回答真实性 (0.0~1.0)
    answer_relevance: float = 0.0      # 答案相关性 (0.0~1.0)
    context_recall: float = 0.0        # 上下文召回率 (0.0~1.0)

    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevance": round(self.answer_relevance, 4),
            "context_recall": round(self.context_recall, 4),
            "details": self.details,
        }


@dataclass
class AgentMetricResult:
    """Agent 评测指标结果"""

    task_success_rate: float = 0.0     # 任务成功率 (0.0~1.0)
    tool_accuracy: float = 0.0         # 工具选择准确率 (0.0~1.0)
    avg_latency_ms: float = 0.0        # 平均延迟 (ms)
    avg_step_count: float = 0.0        # 平均执行步数
    total_cases: int = 0               # 总用例数
    passed_cases: int = 0              # 通过用例数

    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_success_rate": round(self.task_success_rate, 4),
            "tool_accuracy": round(self.tool_accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "avg_step_count": round(self.avg_step_count, 2),
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "details": self.details,
        }


# ============================================================
# RAG Metrics
# ============================================================


def compute_faithfulness(
    answer: str,
    contexts: Sequence[str],
    *,
    use_llm: bool = False,
    llm_call: Optional[callable] = None,
) -> float:
    """
    计算 Faithfulness（回答真实性）— 回答中有多少陈述可以追溯到上下文。

    无 LLM 时使用启发式规则：
    - 将 answer 拆分为句子，检查每个句子中的关键短语是否出现在 contexts 中
    - 如果 contexts 为空 → 0.0
    - 高重叠率 → 高 Faithfulness

    Args:
        answer: 模型生成的回答
        contexts: 检索到的上下文列表
        use_llm: 是否使用 LLM 进行语义评估
        llm_call: LLM 调用函数 (prompt) → str

    Returns:
        faithfulness 分数 (0.0~1.0)
    """
    if not answer or not answer.strip():
        return 0.0

    if not contexts:
        return 0.0

    if use_llm and llm_call:
        return _compute_faithfulness_llm(answer, contexts, llm_call)

    return _compute_faithfulness_rule(answer, contexts)


def _compute_faithfulness_rule(answer: str, contexts: Sequence[str]) -> float:
    """规则-based Faithfulness 计算（使用字符 bigram 重叠率）"""
    # 将回答拆分为句子
    sentences = _split_sentences(answer)
    if not sentences:
        return 0.0

    # 合并所有上下文为单个文本
    context_text = " ".join(contexts)

    supported_count = 0
    for sentence in sentences:
        # 使用 bigram 重叠率衡量句子是否被上下文支持
        overlap = _bigram_overlap(sentence, context_text)
        if overlap >= 0.3:  # 30% bigram 重叠即认为被支持
            supported_count += 1

    return supported_count / len(sentences)


def _compute_faithfulness_llm(
    answer: str,
    contexts: Sequence[str],
    llm_call: callable,
) -> float:
    """LLM-based Faithfulness 计算"""
    context_block = "\n---\n".join(contexts)
    prompt = f"""评估以下回答是否忠实于提供的上下文。对于回答中的每个陈述，判断它是否能从上下文中找到支持。

上下文：
{context_block}

回答：
{answer}

请输出一个 0.0 到 1.0 之间的分数（保留2位小数），表示回答中可被上下文支持的陈述比例：
- 1.0 = 所有陈述都能在上下文中找到
- 0.5 = 大约一半陈述有上下文支持
- 0.0 = 所有陈述都无法在上下文中找到

只输出数字，不要输出其他内容。"""
    try:
        result = llm_call(prompt).strip()
        return float(result)
    except (ValueError, TypeError):
        return _compute_faithfulness_rule(answer, contexts)


def compute_answer_relevance(
    question: str,
    answer: str,
    *,
    use_llm: bool = False,
    llm_call: Optional[callable] = None,
) -> float:
    """
    计算 Answer Relevance（答案相关性）— 回答是否直接回应了问题。

    无 LLM 时使用启发式规则：
    - 检查 question 中的关键词是否出现在 answer 中
    - 检查 answer 长度是否合理（不太短不太长）
    - 检查是否包含无关内容

    Args:
        question: 用户问题
        answer: 模型回答
        use_llm: 是否使用 LLM 进行语义评估
        llm_call: LLM 调用函数 (prompt) → str

    Returns:
        answer_relevance 分数 (0.0~1.0)
    """
    if not answer or not answer.strip():
        return 0.0
    if not question or not question.strip():
        return 0.5

    if use_llm and llm_call:
        return _compute_answer_relevance_llm(question, answer, llm_call)

    return _compute_answer_relevance_rule(question, answer)


def _compute_answer_relevance_rule(question: str, answer: str) -> float:
    """规则-based Answer Relevance 计算"""
    q_lower = question.lower()
    a_lower = answer.lower()

    # 1. 关键词重叠
    q_words = set(_tokenize_chinese(q_lower))
    a_words = set(_tokenize_chinese(a_lower))
    if not q_words:
        return 0.5
    keyword_overlap = len(q_words & a_words) / len(q_words)

    # 2. 长度合理性（回答应比问题长但不太长）
    q_len = len(question)
    a_len = len(answer)
    if a_len < q_len * 0.5:
        length_score = 0.3  # 太短
    elif a_len > q_len * 20:
        length_score = 0.5  # 太长可能包含无关内容
    else:
        length_score = 1.0

    # 3. 拒绝回答检测
    refusal_patterns = [
        "无法回答", "没有相关信息", "无法提供", "不支持",
        "sorry", "cannot answer", "unable to",
    ]
    has_refusal = any(p in a_lower for p in refusal_patterns)

    if has_refusal:
        return 0.0

    # 综合得分
    return (keyword_overlap * 0.7 + length_score * 0.3)


def _compute_answer_relevance_llm(
    question: str,
    answer: str,
    llm_call: callable,
) -> float:
    """LLM-based Answer Relevance 计算"""
    prompt = f"""评估以下回答是否直接、相关地回应了用户问题。

问题：
{question}

回答：
{answer}

请输出一个 0.0 到 1.0 之间的分数（保留2位小数）：
- 1.0 = 回答完全针对问题，无无关内容
- 0.5 = 回答部分相关，但有较多无关内容
- 0.0 = 回答与问题完全无关或拒绝回答

只输出数字，不要输出其他内容。"""
    try:
        result = llm_call(prompt).strip()
        return float(result)
    except (ValueError, TypeError):
        return _compute_answer_relevance_rule(question, answer)


def compute_context_recall(
    contexts: Sequence[str],
    reference_answer: str,
    *,
    use_llm: bool = False,
    llm_call: Optional[callable] = None,
) -> float:
    """
    计算 Context Recall（上下文召回率）— 参考回答中的信息有多少能在上下文中找到。

    无 LLM 时使用启发式规则：
    - 将 reference_answer 拆分，检查其关键短语是否出现在 contexts 中

    Args:
        contexts: 检索到的上下文列表
        reference_answer: 参考答案/标准答案
        use_llm: 是否使用 LLM 进行语义评估
        llm_call: LLM 调用函数 (prompt) → str

    Returns:
        context_recall 分数 (0.0~1.0)
    """
    if not reference_answer or not reference_answer.strip():
        return 1.0  # 无参考答案时假定满分
    if not contexts:
        return 0.0

    if use_llm and llm_call:
        return _compute_context_recall_llm(contexts, reference_answer, llm_call)

    return _compute_context_recall_rule(contexts, reference_answer)


def _compute_context_recall_rule(
    contexts: Sequence[str],
    reference_answer: str,
) -> float:
    """规则-based Context Recall 计算（使用字符 bigram 重叠率）"""
    sentences = _split_sentences(reference_answer)
    if not sentences:
        return 1.0

    context_text = " ".join(contexts)

    recalled = 0
    for sentence in sentences:
        overlap = _bigram_overlap(sentence, context_text)
        if overlap >= 0.3:
            recalled += 1

    return recalled / len(sentences)


def _compute_context_recall_llm(
    contexts: Sequence[str],
    reference_answer: str,
    llm_call: callable,
) -> float:
    """LLM-based Context Recall 计算"""
    context_block = "\n---\n".join(contexts)
    prompt = f"""评估检索到的上下文覆盖参考答案的程度。

上下文：
{context_block}

参考答案：
{reference_answer}

请输出一个 0.0 到 1.0 之间的分数（保留2位小数），表示参考答案中的信息有多少能在上下文中找到：
- 1.0 = 参考答案的所有信息都能在上下文中找到
- 0.5 = 约一半信息能在上下文中找到
- 0.0 = 上下文中完全找不到参考答案的信息

只输出数字，不要输出其他内容。"""
    try:
        result = llm_call(prompt).strip()
        return float(result)
    except (ValueError, TypeError):
        return _compute_context_recall_rule(contexts, reference_answer)


def compute_rag_metrics(
    question: str,
    answer: str,
    contexts: Sequence[str],
    reference_answer: str = "",
    *,
    use_llm: bool = False,
    llm_call: Optional[callable] = None,
) -> RAGMetricResult:
    """
    批量计算所有 RAG 指标。

    Args:
        question: 用户问题
        answer: 模型生成回答
        contexts: 检索到的上下文
        reference_answer: 参考答案（可选，用于 Context Recall）
        use_llm: 是否使用 LLM 评估
        llm_call: LLM 调用函数

    Returns:
        RAGMetricResult 包含所有 RAG 指标
    """
    faithfulness = compute_faithfulness(
        answer, contexts, use_llm=use_llm, llm_call=llm_call,
    )
    answer_relevance = compute_answer_relevance(
        question, answer, use_llm=use_llm, llm_call=llm_call,
    )
    context_recall = compute_context_recall(
        contexts, reference_answer, use_llm=use_llm, llm_call=llm_call,
    )

    return RAGMetricResult(
        faithfulness=faithfulness,
        answer_relevance=answer_relevance,
        context_recall=context_recall,
        details={
            "question": question[:200],
            "answer_preview": answer[:200],
            "num_contexts": len(contexts),
            "has_reference": bool(reference_answer),
            "use_llm": use_llm,
        },
    )


# ============================================================
# Agent Metrics
# ============================================================


def compute_task_success_rate(
    traces: Sequence[dict[str, Any]],
    success_statuses: Sequence[str] = ("success", "completed"),
) -> float:
    """
    计算 Task Success Rate（任务成功率）。

    通过 trace 的 status 字段判断每个任务是否成功。

    Args:
        traces: Agent 执行 trace 记录列表，每条包含 status 字段
        success_statuses: 被认为成功的 status 值

    Returns:
        成功率 (0.0~1.0)，无 trace 时返回 0.0
    """
    if not traces:
        return 0.0

    success_count = sum(
        1 for t in traces
        if t.get("status", "").lower() in success_statuses
    )
    return success_count / len(traces)


def compute_tool_accuracy(
    traces: Sequence[dict[str, Any]],
    expected_tools: Optional[Sequence[str]] = None,
) -> float:
    """
    计算 Tool Accuracy（工具选择准确率）。

    检查 trace 中的工具调用是否与预期工具匹配。

    Args:
        traces: Agent 执行 trace 记录列表，每条可包含 tool_calls 或 tool_name
        expected_tools: 预期应该调用的工具名称列表

    Returns:
        准确率 (0.0~1.0)，无预期工具时返回 1.0
    """
    if not traces:
        return 0.0
    if not expected_tools:
        return 1.0

    # 收集所有实际调用的工具
    actual_tools: set[str] = set()
    for t in traces:
        tool_name = t.get("tool_name", "")
        if tool_name:
            actual_tools.add(tool_name)
        # 也支持 tool_calls 列表格式
        tool_calls = t.get("tool_calls", [])
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    actual_tools.add(tc.get("name", "") or tc.get("tool_name", ""))
                elif isinstance(tc, str):
                    actual_tools.add(tc)

    expected_set = set(expected_tools)
    if not expected_set:
        return 1.0

    # 精确匹配率
    matched = len(actual_tools & expected_set)
    return matched / len(expected_set)


def compute_tool_accuracy_from_mcp_history(
    mcp_history: Sequence[dict[str, Any]],
    expected_tools: Sequence[str],
) -> float:
    """
    从 MCP 调用历史计算工具准确率。

    Args:
        mcp_history: MCP 调用记录列表，每条包含 tool_name
        expected_tools: 预期工具名称

    Returns:
        准确率 (0.0~1.0)
    """
    if not mcp_history:
        return 0.0
    if not expected_tools:
        return 1.0

    actual_tools = {
        h.get("tool_name", "") or h.get("name", "")
        for h in mcp_history
    }
    expected_set = set(expected_tools)

    matched = len(actual_tools & expected_set)
    return matched / len(expected_set)


def compute_avg_latency_ms(traces: Sequence[dict[str, Any]]) -> float:
    """
    计算平均延迟（毫秒）。

    Args:
        traces: trace 记录列表，每条包含 latency_ms 字段

    Returns:
        平均延迟毫秒数
    """
    if not traces:
        return 0.0

    latencies = [
        float(t.get("latency_ms", 0) or 0)
        for t in traces
    ]
    return sum(latencies) / len(latencies)


def compute_avg_step_count(traces: Sequence[dict[str, Any]]) -> float:
    """
    计算平均执行步数。

    步数可以通过以下方式获取（按优先级）：
    1. trace 中的 step_count 字段
    2. trace 记录的数量（每个 agent 调用计为一步）
    3. mcp_history 的长度

    Args:
        traces: trace 记录列表

    Returns:
        平均步数
    """
    if not traces:
        return 0.0

    step_counts: list[int] = []
    for t in traces:
        # 优先使用显式的 step_count
        if "step_count" in t and t["step_count"] is not None:
            step_counts.append(int(t["step_count"]))
        elif "mcp_history" in t and isinstance(t["mcp_history"], list):
            step_counts.append(len(t["mcp_history"]))
        else:
            step_counts.append(1)  # 每个 trace 至少算一步

    return sum(step_counts) / len(step_counts)


def compute_agent_metrics(
    traces: Sequence[dict[str, Any]],
    expected_tools: Optional[Sequence[str]] = None,
) -> AgentMetricResult:
    """
    批量计算所有 Agent 指标。

    Args:
        traces: Agent 执行 trace 记录列表
        expected_tools: 预期工具列表

    Returns:
        AgentMetricResult 包含所有 Agent 指标
    """
    total = len(traces)

    # Task Success Rate
    task_success_rate = compute_task_success_rate(traces)

    # Passed cases
    success_statuses = {"success", "completed"}
    passed = sum(
        1 for t in traces
        if t.get("status", "").lower() in success_statuses
    )

    # Tool Accuracy
    tool_accuracy = compute_tool_accuracy(traces, expected_tools)

    # 如果 traces 中有 mcp_history，也从中计算工具准确率
    all_mcp: list[dict] = []
    for t in traces:
        mcp = t.get("mcp_history", [])
        if isinstance(mcp, list):
            all_mcp.extend(mcp)
    if all_mcp and expected_tools:
        mcp_accuracy = compute_tool_accuracy_from_mcp_history(all_mcp, expected_tools)
        tool_accuracy = max(tool_accuracy, mcp_accuracy)

    # Latency & Steps
    avg_latency = compute_avg_latency_ms(traces)
    avg_steps = compute_avg_step_count(traces)

    # Build detail per-agent stats
    agent_stats: dict[str, dict] = {}
    for t in traces:
        agent = t.get("agent_name", "unknown")
        if agent not in agent_stats:
            agent_stats[agent] = {"count": 0, "latencies": [], "steps": []}
        agent_stats[agent]["count"] += 1
        lat = float(t.get("latency_ms", 0) or 0)
        agent_stats[agent]["latencies"].append(lat)

        if "step_count" in t:
            agent_stats[agent]["steps"].append(int(t["step_count"]))
        elif "mcp_history" in t:
            agent_stats[agent]["steps"].append(
                len(t["mcp_history"]) if isinstance(t["mcp_history"], list) else 1
            )

    detail_per_agent = {}
    for agent, stats in agent_stats.items():
        detail_per_agent[agent] = {
            "count": stats["count"],
            "avg_latency_ms": round(
                sum(stats["latencies"]) / max(len(stats["latencies"]), 1), 2
            ),
            "avg_steps": round(
                sum(stats["steps"]) / max(len(stats["steps"]), 1), 2
            ) if stats["steps"] else 0,
        }

    return AgentMetricResult(
        task_success_rate=task_success_rate,
        tool_accuracy=tool_accuracy,
        avg_latency_ms=avg_latency,
        avg_step_count=avg_steps,
        total_cases=total,
        passed_cases=passed,
        details={
            "per_agent": detail_per_agent,
            "expected_tools": list(expected_tools) if expected_tools else [],
        },
    )


# ============================================================
# Intent Accuracy
# ============================================================


def compute_intent_accuracy(
    predicted: str,
    expected: str,
) -> float:
    """
    计算意图分类准确率。

    Args:
        predicted: 预测的意图标签
        expected: 期望的意图标签

    Returns:
        1.0 或 0.0（精确匹配）
    """
    if not expected:
        return 1.0
    return 1.0 if predicted.strip().lower() == expected.strip().lower() else 0.0


def compute_intent_accuracy_batch(
    predictions: Sequence[str],
    expected_list: Sequence[str],
) -> float:
    """
    批量计算意图分类准确率。

    Args:
        predictions: 预测意图列表
        expected_list: 期望意图列表

    Returns:
        准确率 (0.0~1.0)
    """
    if not predictions or not expected_list:
        return 0.0
    if len(predictions) != len(expected_list):
        raise ValueError(
            f"predictions ({len(predictions)}) and expected ({len(expected_list)}) must have same length"
        )

    correct = sum(
        1 for p, e in zip(predictions, expected_list)
        if p.strip().lower() == e.strip().lower()
    )
    return correct / len(predictions)


# ============================================================
# Composite / Utility
# ============================================================


@dataclass
class EvalReport:
    """完整的评测报告"""

    rag: RAGMetricResult = field(default_factory=RAGMetricResult)
    agent: AgentMetricResult = field(default_factory=AgentMetricResult)
    intent_accuracy: float = 0.0
    overall_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rag": self.rag.to_dict(),
            "agent": self.agent.to_dict(),
            "intent_accuracy": round(self.intent_accuracy, 4),
            "overall_score": round(self.overall_score, 4),
        }


def compute_overall_score(
    rag: RAGMetricResult,
    agent: AgentMetricResult,
    intent_accuracy: float = 1.0,
    *,
    weights: Optional[dict[str, float]] = None,
) -> float:
    """
    计算综合评分（加权平均）。

    Args:
        rag: RAG 指标结果
        agent: Agent 指标结果
        intent_accuracy: 意图准确率
        weights: 各维度权重，默认均等

    Returns:
        综合评分 (0.0~1.0)
    """
    if weights is None:
        weights = {
            "faithfulness": 0.15,
            "answer_relevance": 0.15,
            "context_recall": 0.10,
            "task_success_rate": 0.25,
            "tool_accuracy": 0.15,
            "intent_accuracy": 0.10,
            "efficiency": 0.10,  # 基于 latency 和 steps
        }

    # 效率分：latency 越低越好，steps 越少越好
    latency_score = max(0.0, 1.0 - agent.avg_latency_ms / 30000.0)  # 30s 为基准
    step_score = max(0.0, 1.0 - agent.avg_step_count / 10.0)  # 10步为基准
    efficiency = (latency_score * 0.5 + step_score * 0.5)

    overall = (
        weights.get("faithfulness", 0.15) * rag.faithfulness
        + weights.get("answer_relevance", 0.15) * rag.answer_relevance
        + weights.get("context_recall", 0.10) * rag.context_recall
        + weights.get("task_success_rate", 0.25) * agent.task_success_rate
        + weights.get("tool_accuracy", 0.15) * agent.tool_accuracy
        + weights.get("intent_accuracy", 0.10) * intent_accuracy
        + weights.get("efficiency", 0.10) * efficiency
    )

    return max(0.0, min(1.0, overall))


# ============================================================
# Helper Functions
# ============================================================


def _bigram_overlap(text_a: str, text_b: str) -> float:
    """计算两个文本的字符 bigram Jaccard 重叠率（适用于中英文混合文本）"""
    bigrams_a = _extract_bigrams(text_a)
    bigrams_b = _extract_bigrams(text_b)

    if not bigrams_a:
        return 0.0

    intersection = len(bigrams_a & bigrams_b)
    return intersection / len(bigrams_a)


def _extract_bigrams(text: str) -> set[str]:
    """提取文本的字符级 bigram 集合"""
    # 清理文本：移除标点和空白（使用 Unicode 属性转义）
    cleaned = re.sub(r"[　-〿＀-￯\s\d]+", "", text)
    # 也移除常见中英文标点
    cleaned = re.sub(r"[,\.!\?;:'\"\-\(\)\[\]{}<>@#$%^&*+=|\\/]+", "", cleaned)
    if len(cleaned) < 2:
        return set()

    bigrams: set[str] = set()
    for i in range(len(cleaned) - 1):
        bigrams.add(cleaned[i:i + 2])
    return bigrams


def _split_sentences(text: str) -> list[str]:
    """将中文文本拆分为句子"""
    # 中英文句子分隔符
    delimiters = r"[。！？；!?;\n]+"
    parts = re.split(delimiters, text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= 2]


def _extract_key_phrases(text: str, min_len: int = 4) -> list[str]:
    """
    从文本中提取关键短语。

    使用滑动窗口提取长度 >= min_len 的连续中文字符序列。
    """
    # 提取中文字符序列
    chinese_chars = re.findall(r"[一-鿿]+", text)
    phrases: list[str] = []

    for chunk in chinese_chars:
        if len(chunk) < min_len:
            phrases.append(chunk)
        else:
            # 滑动窗口提取 min_len~8 的短语
            for w in range(min_len, min(len(chunk), 8) + 1):
                for i in range(len(chunk) - w + 1):
                    phrases.append(chunk[i:i + w])

    # 也提取连续的英文/数字短语
    en_phrases = re.findall(r"[A-Za-z0-9._-]{" + str(min_len) + r",}", text)
    phrases.extend(en_phrases)

    return list(set(phrases))  # 去重


def _tokenize_chinese(text: str) -> list[str]:
    """
    简易中文分词（字符级 bigram + 单字）。

    不依赖 jieba，使用滑动窗口 bigram 近似。
    """
    tokens: list[str] = []
    # 提取中文连续块
    chinese_blocks = re.findall(r"[一-鿿]+", text)
    for block in chinese_blocks:
        # bigram
        for i in range(len(block) - 1):
            tokens.append(block[i:i + 2])
        # 单字也加入
        tokens.extend(list(block))

    # 英文词
    en_words = re.findall(r"[A-Za-z]+", text.lower())
    tokens.extend(en_words)

    return tokens


# ============================================================
# Smoke Test
# ============================================================


def _smoke_test() -> None:
    """模块自测"""
    passed = 0
    total = 0

    # --- RAG Metrics ---
    print("=" * 60)
    print("RAG Metrics Tests")
    print("=" * 60)

    # Test 1: faithfulness - empty contexts
    total += 1
    score = compute_faithfulness("这是一段回答", [])
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] faithfulness empty contexts -> 0.0")

    # Test 2: faithfulness - empty answer
    total += 1
    score = compute_faithfulness("", ["上下文"])
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] faithfulness empty answer -> 0.0")

    # Test 3: faithfulness - perfect match
    total += 1
    score = compute_faithfulness(
        "营业执照是开公司必需的证件",
        ["营业执照是市场主体登记管理部门依法登记注册，确认市场主体资格的法律文件。开公司必须办理营业执照。"],
    )
    assert score > 0.0, f"Expected >0.0, got {score}"
    passed += 1
    print(f"  [OK] faithfulness perfect match -> {score:.4f}")

    # Test 4: faithfulness - no match
    total += 1
    score = compute_faithfulness(
        "开公司需要食品经营许可证",
        ["营业执照是市场主体登记管理部门依法登记注册的文件。"],
    )
    assert score < 1.0, f"Expected <1.0, got {score}"
    passed += 1
    print(f"  [OK] faithfulness no match -> {score:.4f}")

    # Test 5: answer_relevance - perfect match
    total += 1
    score = compute_answer_relevance(
        "如何办理营业执照？",
        "办理营业执照需要到当地市场监督管理局提交申请，提供身份证、经营场所证明等材料。",
    )
    assert score > 0.0, f"Expected >0.0, got {score}"
    passed += 1
    print(f"  [OK] answer_relevance match -> {score:.4f}")

    # Test 6: answer_relevance - refusal detected
    total += 1
    score = compute_answer_relevance(
        "如何办理营业执照？",
        "抱歉，我无法回答这个问题。",
    )
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] answer_relevance refusal -> 0.0")

    # Test 7: answer_relevance - empty answer
    total += 1
    score = compute_answer_relevance("问题", "")
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] answer_relevance empty -> 0.0")

    # Test 8: context_recall - empty contexts
    total += 1
    score = compute_context_recall([], "参考答案")
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] context_recall empty contexts -> 0.0")

    # Test 9: context_recall - empty reference
    total += 1
    score = compute_context_recall(["上下文"], "")
    assert score == 1.0, f"Expected 1.0, got {score}"
    passed += 1
    print("  [OK] context_recall empty reference -> 1.0")

    # Test 10: context_recall - match
    total += 1
    score = compute_context_recall(
        ["营业执照是市场主体登记管理部门依法登记注册的文件。"],
        "营业执照是登记注册的文件。",
    )
    assert score > 0.0, f"Expected >0.0, got {score}"
    passed += 1
    print(f"  [OK] context_recall match -> {score:.4f}")

    # Test 11: compute_rag_metrics
    total += 1
    rag_result = compute_rag_metrics(
        question="如何办理营业执照？",
        answer="办理营业执照需要到当地市场监督管理局提交申请。",
        contexts=["营业执照是市场主体登记管理部门依法登记注册的文件。"],
        reference_answer="营业执照需要在市场监督管理局办理。",
    )
    assert isinstance(rag_result, RAGMetricResult)
    assert 0.0 <= rag_result.faithfulness <= 1.0
    assert 0.0 <= rag_result.answer_relevance <= 1.0
    assert 0.0 <= rag_result.context_recall <= 1.0
    passed += 1
    print(f"  [OK] compute_rag_metrics -> {rag_result.to_dict()}")

    # --- Agent Metrics ---
    print("\n" + "=" * 60)
    print("Agent Metrics Tests")
    print("=" * 60)

    # Test 12: task_success_rate
    total += 1
    traces = [
        {"status": "success", "agent_name": "policy"},
        {"status": "success", "agent_name": "material"},
        {"status": "failed", "agent_name": "workflow"},
        {"status": "completed", "agent_name": "supervisor"},
    ]
    rate = compute_task_success_rate(traces)
    assert rate == 0.75, f"Expected 0.75, got {rate}"
    passed += 1
    print(f"  [OK] task_success_rate -> {rate}")

    # Test 13: task_success_rate - empty
    total += 1
    rate = compute_task_success_rate([])
    assert rate == 0.0, f"Expected 0.0, got {rate}"
    passed += 1
    print("  [OK] task_success_rate empty -> 0.0")

    # Test 14: tool_accuracy
    total += 1
    traces2 = [
        {"tool_name": "search_policy", "status": "success"},
        {"tool_name": "get_policy_detail", "status": "success"},
    ]
    accuracy = compute_tool_accuracy(traces2, ["search_policy", "get_policy_detail", "create_case"])
    assert accuracy == 2 / 3, f"Expected 2/3, got {accuracy}"
    passed += 1
    print(f"  [OK] tool_accuracy -> {accuracy:.4f}")

    # Test 15: tool_accuracy - empty expected
    total += 1
    accuracy = compute_tool_accuracy(traces2, None)
    assert accuracy == 1.0, f"Expected 1.0, got {accuracy}"
    passed += 1
    print("  [OK] tool_accuracy no expected -> 1.0")

    # Test 16: tool_accuracy - empty traces
    total += 1
    accuracy = compute_tool_accuracy([], ["search_policy"])
    assert accuracy == 0.0, f"Expected 0.0, got {accuracy}"
    passed += 1
    print("  [OK] tool_accuracy empty traces -> 0.0")

    # Test 17: tool_accuracy with tool_calls list
    total += 1
    traces3 = [
        {
            "tool_calls": [
                {"name": "search_policy"},
                {"name": "extract_entity"},
            ],
            "status": "success",
        },
    ]
    accuracy = compute_tool_accuracy(traces3, ["search_policy", "extract_entity"])
    assert accuracy == 1.0, f"Expected 1.0, got {accuracy}"
    passed += 1
    print(f"  [OK] tool_accuracy with tool_calls -> {accuracy}")

    # Test 18: avg_latency
    total += 1
    traces4 = [
        {"latency_ms": 100},
        {"latency_ms": 200},
        {"latency_ms": 300},
    ]
    avg_lat = compute_avg_latency_ms(traces4)
    assert avg_lat == 200.0, f"Expected 200.0, got {avg_lat}"
    passed += 1
    print(f"  [OK] avg_latency_ms -> {avg_lat}")

    # Test 19: avg_latency - empty
    total += 1
    avg_lat = compute_avg_latency_ms([])
    assert avg_lat == 0.0, f"Expected 0.0, got {avg_lat}"
    passed += 1
    print("  [OK] avg_latency_ms empty -> 0.0")

    # Test 20: avg_step_count
    total += 1
    traces5 = [
        {"step_count": 3},
        {"step_count": 5},
    ]
    avg_steps = compute_avg_step_count(traces5)
    assert avg_steps == 4.0, f"Expected 4.0, got {avg_steps}"
    passed += 1
    print(f"  [OK] avg_step_count -> {avg_steps}")

    # Test 21: avg_step_count with mcp_history
    total += 1
    traces6 = [
        {"mcp_history": [{"tool": "a"}, {"tool": "b"}]},
        {"mcp_history": [{"tool": "c"}]},
    ]
    avg_steps = compute_avg_step_count(traces6)
    assert avg_steps == 1.5, f"Expected 1.5, got {avg_steps}"
    passed += 1
    print(f"  [OK] avg_step_count mcp_history -> {avg_steps}")

    # Test 22: compute_agent_metrics
    total += 1
    agent_result = compute_agent_metrics(
        traces,
        expected_tools=["search_policy", "get_policy_detail"],
    )
    assert isinstance(agent_result, AgentMetricResult)
    assert agent_result.total_cases == 4
    assert agent_result.passed_cases == 3
    passed += 1
    print(f"  [OK] compute_agent_metrics -> {agent_result.to_dict()}")

    # --- Intent Accuracy ---
    print("\n" + "=" * 60)
    print("Intent Accuracy Tests")
    print("=" * 60)

    # Test 23: intent_accuracy match
    total += 1
    acc = compute_intent_accuracy("business_license", "business_license")
    assert acc == 1.0, f"Expected 1.0, got {acc}"
    passed += 1
    print("  [OK] intent_accuracy match -> 1.0")

    # Test 24: intent_accuracy mismatch
    total += 1
    acc = compute_intent_accuracy("policy_query", "business_license")
    assert acc == 0.0, f"Expected 0.0, got {acc}"
    passed += 1
    print("  [OK] intent_accuracy mismatch -> 0.0")

    # Test 25: intent_accuracy empty expected
    total += 1
    acc = compute_intent_accuracy("business_license", "")
    assert acc == 1.0, f"Expected 1.0, got {acc}"
    passed += 1
    print("  [OK] intent_accuracy empty expected -> 1.0")

    # Test 26: intent_accuracy_batch
    total += 1
    acc = compute_intent_accuracy_batch(
        ["business_license", "policy_query", "material_check"],
        ["business_license", "policy_query", "workflow_create"],
    )
    assert acc == 2 / 3, f"Expected 2/3, got {acc}"
    passed += 1
    print(f"  [OK] intent_accuracy_batch -> {acc:.4f}")

    # Test 27: intent_accuracy_batch length mismatch
    total += 1
    try:
        compute_intent_accuracy_batch(["a"], ["a", "b"])
        print("  [FAIL] intent_accuracy_batch should have raised ValueError")
    except ValueError:
        passed += 1
        print("  [OK] intent_accuracy_batch length mismatch -> ValueError")

    # --- Composite ---
    print("\n" + "=" * 60)
    print("Composite Tests")
    print("=" * 60)

    # Test 28: compute_overall_score
    total += 1
    score = compute_overall_score(
        rag=rag_result,
        agent=agent_result,
        intent_accuracy=0.8,
    )
    assert 0.0 <= score <= 1.0, f"Expected 0~1, got {score}"
    passed += 1
    print(f"  [OK] overall_score -> {score:.4f}")

    # Test 29: EvalReport
    total += 1
    report = EvalReport(
        rag=rag_result,
        agent=agent_result,
        intent_accuracy=0.9,
        overall_score=0.85,
    )
    d = report.to_dict()
    assert "rag" in d and "agent" in d
    assert d["overall_score"] == 0.85
    passed += 1
    print(f"  [OK] EvalReport.to_dict() -> {d}")

    # --- Edge Cases ---
    print("\n" + "=" * 60)
    print("Edge Cases")
    print("=" * 60)

    # Test 30: faithfulness with None contexts (treated as empty)
    total += 1
    score = compute_faithfulness("answer", None)  # type: ignore
    assert score == 0.0, f"Expected 0.0, got {score}"
    passed += 1
    print("  [OK] faithfulness None contexts -> 0.0 (graceful)")

    # Test 31: tool_accuracy_from_mcp_history
    total += 1
    mcp_history = [
        {"tool_name": "search_policy"},
        {"name": "get_policy_detail"},
        {"tool_name": "extract_entity"},
    ]
    acc = compute_tool_accuracy_from_mcp_history(
        mcp_history, ["search_policy", "get_policy_detail"],
    )
    assert acc == 1.0, f"Expected 1.0, got {acc}"
    passed += 1
    print(f"  [OK] tool_accuracy_from_mcp_history -> {acc}")

    # Test 32: tool_accuracy_from_mcp_history empty
    total += 1
    acc = compute_tool_accuracy_from_mcp_history([], ["search_policy"])
    assert acc == 0.0, f"Expected 0.0, got {acc}"
    passed += 1
    print("  [OK] tool_accuracy_from_mcp_history empty -> 0.0")

    # Test 33: combine all metrics with mixed case
    total += 1
    score = compute_intent_accuracy("Business_License", "business_license")
    assert score == 1.0, f"Expected 1.0, got {score}"
    passed += 1
    print(f"  [OK] intent_accuracy case insensitive -> {score}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed")
    print("=" * 60)

    if passed == total:
        print("ALL smoke tests passed!")
    else:
        print(f"{total - passed} test(s) failed!")


if __name__ == "__main__":
    _smoke_test()
