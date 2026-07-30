"""
rag.generator - LLM Generator: generate answers based on retrieved context with evidence

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement LLM answer generation with evidence annotation
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from tools.logger import get_logger

logger = get_logger(__name__)

GENERATOR_SYSTEM_PROMPT = """\
# 角色
你是一个政务知识问答助手。

# 任务
基于提供的政策文档，回答用户问题。每条关键信息必须标注来源。

# 要求
1. 只基于提供的内容回答，不要编造
2. 引用政策文件名称和条款
3. 回答结构清晰、条理分明
4. 如果提供的内容不足以回答问题，明确说明
5. 使用专业但平易近人的语言

# 输出格式
{
  "answer": "完整回答",
  "evidence": [{"source": "文件名", "excerpt": "引用的原文"}]
}
"""


class Generator:
    """
    LLM 答案生成器 — 基于检索到的文档生成带 evidence 的答案。

    使用方式:
        gen = Generator(llm)
        answer = await gen.generate(query, documents)
        # {"answer": "...", "evidence": [{...}, ...]}
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Args:
            llm: LangChain ChatModel
        """
        self._llm = llm

    async def generate(
        self,
        query: str,
        documents: list[dict],
    ) -> dict:
        """
        基于检索结果生成答案。

        Args:
            query: 用户查询
            documents: 检索到的文档列表 [{title, content, score, source}, ...]

        Returns:
            {"answer": str, "evidence": [{"source": str, "excerpt": str}]}
        """
        if not documents:
            return {
                "answer": "未找到相关政策信息，请尝试换个问题或联系人工客服。",
                "evidence": [],
            }

        if self._llm is not None:
            return await self._llm_generate(query, documents)

        # 无 LLM 时用简单拼接
        return self._simple_generate(query, documents)

    async def _llm_generate(self, query: str, documents: list[dict]) -> dict:
        """LLM 生成答案"""
        assert self._llm is not None

        # 构建上下文
        context_parts: list[str] = []
        for i, doc in enumerate(documents):
            title = doc.get("title", f"文档{i+1}")
            content = doc.get("content", "")
            source = doc.get("source", title)
            context_parts.append(
                f"--- 文档{i+1}: {title} (来源: {source}) ---\n{content[:2000]}"
            )
        context = "\n\n".join(context_parts)

        system_msg = SystemMessage(content=GENERATOR_SYSTEM_PROMPT)
        user_msg = HumanMessage(
            content=f"# 检索到的政策文档\n\n{context}\n\n# 用户问题\n{query}\n\n请生成回答。"
        )

        response = await self._llm.ainvoke([system_msg, user_msg])
        answer = self._extract_text(response)

        # 构建 evidence
        evidence = []
        for doc in documents[:3]:
            evidence.append({
                "source": doc.get("source", doc.get("title", "未知来源")),
                "excerpt": doc.get("content", "")[:200],
                "relevance_score": doc.get("score", doc.get("relevance_score", 0.0)),
            })

        return {"answer": answer, "evidence": evidence}

    def _simple_generate(self, query: str, documents: list[dict]) -> dict:
        """简单拼接（无 LLM 兜底）"""
        parts = ["根据相关政策文件：\n"]
        evidence = []

        for i, doc in enumerate(documents[:3]):
            title = doc.get("title", f"文档{i+1}")
            content = doc.get("content", "")
            parts.append(f"**{title}**: {content[:300]}\n")
            evidence.append({
                "source": title,
                "excerpt": content[:200],
                "relevance_score": doc.get("score", 0.5),
            })

        return {"answer": "\n".join(parts), "evidence": evidence}

    @staticmethod
    def _extract_text(response) -> str:
        if hasattr(response, "content"):
            return response.content
        return str(response)
