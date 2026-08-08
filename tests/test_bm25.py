"""
test_bm25 - BM25 sparse retrieval tests
"""
from __future__ import annotations


from rag.bm25 import SimpleBM25


class TestSimpleBM25:
    def setup_method(self):
        self.docs = [
            "开办餐饮店需要营业执照和食品经营许可证",
            "公积金查询可以通过官网或12329热线",
            "不动产登记需要购房合同和完税证明",
        ]
        self.bm25 = SimpleBM25(self.docs)

    def test_doc_count(self):
        assert self.bm25.doc_count == 3

    def test_avgdl_positive(self):
        assert self.bm25.average_doc_length > 0

    def test_matching_doc_ranked_first(self):
        scores = self.bm25.score("餐饮店营业执照")
        assert len(scores) == 3
        assert max(range(3), key=lambda i: scores[i]) == 0

    def test_second_doc_ranked(self):
        scores = self.bm25.score("公积金热线查询")
        assert max(range(3), key=lambda i: scores[i]) == 1

    def test_no_match_zeros(self):
        scores = self.bm25.score("完全不相关的内容xyz")
        assert all(s == 0 for s in scores)

    def test_empty_corpus(self):
        bm25 = SimpleBM25([])
        assert bm25.score("测试") == []

    def test_empty_query(self):
        bm25 = SimpleBM25(["文档内容"])
        scores = bm25.score("")
        assert len(scores) == 1
        assert scores[0] == 0
