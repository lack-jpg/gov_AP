"""
rag.bm25 - Lightweight BM25 implementation (jieba tokenization + numpy scoring)

Author: le
Date: 2026/8/2
Version: 0.1
Task: Implement BM25 sparse retrieval without external rank_bm25 dependency

Usage:
    bm25 = SimpleBM25(["文档一的内容", "文档二的内容"])
    scores = bm25.score("查询文本")
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from tools.logger import get_logger

logger = get_logger(__name__)

# 可选 jieba 分词；未安装时退化为字符二元组
try:
    import jieba

    def _tokenize(text: str) -> list[str]:
        return [t for t in jieba.lcut(text) if t.strip()]

except ImportError:  # pragma: no cover
    def _tokenize(text: str) -> list[str]:
        # 退化为字符级 n-gram（简单但可工作）
        text = "".join(c for c in text if not c.isspace())
        return [text[i : i + 2] for i in range(max(0, len(text) - 1))]


class SimpleBM25:
    """
    简易 BM25 实现。

    使用 jieba 对中文文档/查询分词，基于 BM25 公式计算文档与查询的相关性分数。

    score(d, q) = Σ_{t in q} IDF(t) * [f(t,d) * (k1 + 1)] / [f(t,d) + k1 * (1 - b + b * dl/avgdl)]

    参数:
        k1: 词频饱和因子，默认 1.5
        b: 文档长度归一化因子，默认 0.75
    """

    def __init__(
        self,
        documents: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """
        Args:
            documents: 语料文档列表
            k1: 词频饱和因子
            b: 文档长度归一化因子
        """
        self._k1 = k1
        self._b = b
        self._documents = list(documents)

        # 文档长度（token 数）
        self._doc_lengths: list[int] = []
        self._doc_freqs: list[Counter] = []

        for doc in self._documents:
            tokens = _tokenize(doc)
            self._doc_lengths.append(len(tokens))
            self._doc_freqs.append(Counter(tokens))

        self._avgdl = (
            sum(self._doc_lengths) / len(self._doc_lengths)
            if self._doc_lengths
            else 0.0
        )
        self._doc_count = len(self._documents)

        # 逆文档频率：每个 term 出现在多少个文档中
        self._df: Counter = Counter()
        for freq in self._doc_freqs:
            self._df.update(freq.keys())

    def score(self, query: str) -> list[float]:
        """
        计算查询与所有文档的相关性分数。

        Args:
            query: 查询文本

        Returns:
            与文档一一对应的分数列表（无匹配返回 0）
        """
        if not self._documents:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return [0.0] * self._doc_count

        scores = np.zeros(self._doc_count, dtype=np.float32)

        for term in set(query_tokens):
            idf = self._idf(term)
            if idf <= 0:
                continue

            for i, freq in enumerate(self._doc_freqs):
                tf = freq.get(term, 0)
                if tf == 0:
                    continue

                dl = self._doc_lengths[i]
                denominator = tf + self._k1 * (
                    1 - self._b + self._b * dl / self._avgdl
                ) if self._avgdl > 0 else tf + self._k1
                scores[i] += idf * (tf * (self._k1 + 1)) / denominator

        return scores.tolist()

    def _idf(self, term: str) -> float:
        """计算 term 的逆文档频率（平滑版）"""
        df = self._df.get(term, 0)
        return math.log(1 + (self._doc_count - df + 0.5) / (df + 0.5))

    @property
    def doc_count(self) -> int:
        """语料文档数"""
        return self._doc_count

    @property
    def average_doc_length(self) -> float:
        """平均文档长度（token 数）"""
        return self._avgdl


# ============================================================
# Smoke Test — python -m rag.bm25
# ============================================================

if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(name: str, actual: object, expected: object) -> None:
        global passed, failed
        if actual == expected:
            passed += 1
            print(f"  [OK] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected={expected!r}, got={actual!r}")

    print("=== rag.bm25 smoke test ===")

    docs = [
        "开办餐饮店需要营业执照和食品经营许可证",
        "公积金查询可以通过官网或12329热线",
        "不动产登记需要购房合同和完税证明",
    ]
    bm25 = SimpleBM25(docs)
    check("doc_count", bm25.doc_count, 3)
    check("avgdl > 0", bm25.average_doc_length > 0, True)

    # 查询匹配第一个文档
    scores = bm25.score("餐饮店营业执照")
    check("scores_len", len(scores), 3)
    check("doc0_top", max(range(3), key=lambda i: scores[i]), 0)

    # 查询匹配第二个文档
    scores2 = bm25.score("公积金热线查询")
    check("doc1_top", max(range(3), key=lambda i: scores2[i]), 1)

    # 无匹配查询 → 全 0
    scores3 = bm25.score("完全不相关的内容xyz")
    check("no_match_zeros", all(s == 0 for s in scores3), True)

    # 空语料
    bm25_empty = SimpleBM25([])
    check("empty_corpus", bm25_empty.score("测试"), [])

    total = passed + failed
    print(f"\n=== {passed}/{total} passed, {failed} failed ===")
    if failed > 0:
        raise SystemExit(1)
