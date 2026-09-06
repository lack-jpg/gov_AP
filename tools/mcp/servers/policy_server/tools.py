"""
mcp.servers.policy_server.tools - Policy MCP Tools: search_policy, get_policy_detail

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement search_policy and get_policy_detail using RAG stubs + template fallback
"""
from __future__ import annotations

from typing import Any

from tools.logger import get_logger
from tools.mcp.schema import (
    SearchPolicyOutput,
    PolicyDocument,
    GetPolicyDetailOutput,
)

logger = get_logger(__name__)


# ============================================================
# Stub 政策语料库
# ============================================================

_STUB_POLICIES: list[dict[str, Any]] = [
    {
        "document_id": "POL-001",
        "title": "食品经营许可管理办法",
        "content": (
            "申请食品经营许可，应当向所在地县级以上地方食品药品监督管理部门提交下列材料：\n"
            "（一）食品经营许可申请书；\n"
            "（二）营业执照或者其他主体资格证明文件复印件；\n"
            "（三）与食品经营相适应的主要设备设施布局、操作流程等文件；\n"
            "（四）食品安全自查、从业人员健康管理、进货查验记录、食品安全事故处置等保证食品安全的规章制度。\n"
            "申请人委托他人办理食品经营许可申请的，代理人应当提交授权委托书以及代理人的身份证明文件。"
        ),
        "source": "《食品经营许可管理办法》第十二条",
        "department": "国家食品药品监督管理总局",
        "publish_date": "2015-10-01",
        "keywords": ["食品", "餐饮", "餐馆", "饭店", "经营许可", "食品安全"],
    },
    {
        "document_id": "POL-002",
        "title": "个体工商户条例",
        "content": (
            "有经营能力的公民，依照本条例规定经工商行政管理部门登记，从事工商业经营的，为个体工商户。\n"
            "申请登记为个体工商户，应当向经营场所所在地登记机关申请注册登记。\n"
            "申请人应当提交登记申请书、身份证明和经营场所证明。\n"
            "个体工商户登记事项包括经营者姓名和住所、组成形式、经营范围、经营场所。"
        ),
        "source": "《个体工商户条例》第二条、第八条",
        "department": "国务院",
        "publish_date": "2011-11-01",
        "keywords": ["个体工商户", "营业执照", "注册", "登记", "公司", "企业"],
    },
    {
        "document_id": "POL-003",
        "title": "消防安全检查规定",
        "content": (
            "公众聚集场所在投入使用、营业前，建设单位或者使用单位应当向场所所在地的县级以上地方人民政府"
            "公安机关消防机构申请消防安全检查。\n"
            "申请消防安全检查应当提供下列材料：\n"
            "（一）消防安全检查申报表；\n"
            "（二）营业执照复印件或者工商行政管理机关出具的企业名称预先核准通知书；\n"
            "（三）依法取得的建设工程消防验收或者进行竣工验收消防备案的法律文件复印件；\n"
            "（四）消防安全制度、灭火和应急疏散预案、场所平面布置图。"
        ),
        "source": "《消防监督检查规定》第八条",
        "department": "公安部",
        "publish_date": "2012-11-01",
        "keywords": ["消防", "安全检查", "餐馆", "公众聚集场所", "消防验收"],
    },
    {
        "document_id": "POL-004",
        "title": "住房公积金管理条例",
        "content": (
            "职工住房公积金的月缴存额为职工本人上一年度月平均工资乘以职工住房公积金缴存比例。\n"
            "单位为职工缴存的住房公积金的月缴存额为职工本人上一年度月平均工资乘以单位住房公积金缴存比例。\n"
            "职工有下列情形之一的，可以提取职工住房公积金账户内的存储余额：\n"
            "（一）购买、建造、翻建、大修自住住房的；\n"
            "（二）离休、退休的；\n"
            "（三）完全丧失劳动能力，并与单位终止劳动关系的。"
        ),
        "source": "《住房公积金管理条例》第十六条、第二十四条",
        "department": "国务院",
        "publish_date": "2002-03-24",
        "keywords": ["公积金", "住房", "缴存", "提取"],
    },
    {
        "document_id": "POL-005",
        "title": "不动产登记暂行条例",
        "content": (
            "不动产登记机构应当依法将各类登记事项准确、完整、清晰地记载于不动产登记簿。\n"
            "申请不动产登记，申请人应当提交下列材料：\n"
            "（一）登记申请书；\n"
            "（二）申请人、代理人身份证明材料、授权委托书；\n"
            "（三）相关的不动产权属来源证明材料、登记原因证明文件、不动产权属证书；\n"
            "（四）不动产界址、空间界限、面积等材料。"
        ),
        "source": "《不动产登记暂行条例》第十六条",
        "department": "国务院",
        "publish_date": "2015-03-01",
        "keywords": ["不动产", "房产", "房屋", "产权", "登记"],
    },
    {
        "document_id": "POL-006",
        "title": "中华人民共和国公司法（节选）",
        "content": (
            "设立有限责任公司，应当具备下列条件：\n"
            "（一）股东符合法定人数；\n"
            "（二）有符合公司章程规定的全体股东认缴的出资额；\n"
            "（三）股东共同制定公司章程；\n"
            "（四）有公司名称，建立符合有限责任公司要求的组织机构；\n"
            "（五）有公司住所。\n"
            "申请设立登记，应向公司登记机关提交公司登记申请书、公司章程、"
            "法定代表人任职文件和身份证明、公司住所证明等文件。"
        ),
        "source": "《中华人民共和国公司法》第二十三条、第二十九条",
        "department": "全国人民代表大会",
        "publish_date": "2018-10-26",
        "keywords": ["公司", "企业", "注册", "有限责任公司", "登记", "营业执照"],
    },
    {
        "document_id": "POL-007",
        "title": "成都市餐饮服务食品安全监督管理办法",
        "content": (
            "餐饮服务提供者应当依法取得食品经营许可。申请食品经营许可应当符合下列条件：\n"
            "（一）具有与经营的食品品种、数量相适应的食品原料处理和食品加工、销售、贮存等场所；\n"
            "（二）具有与经营的食品品种、数量相适应的经营设备或者设施；\n"
            "（三）有专职或者兼职的食品安全管理人员和保证食品安全的规章制度。\n"
            "成都市餐饮服务提供者还应当遵守成都市的环保、消防、卫生等相关规定。"
        ),
        "source": "《成都市餐饮服务食品安全监督管理办法》",
        "department": "成都市市场监督管理局",
        "publish_date": "2019-01-01",
        "keywords": ["成都", "餐饮", "食品安全", "餐馆", "饭店"],
    },
]


# ============================================================
# search_policy
# ============================================================


async def search_policy(
    query: str,
    top_k: int = 5,
    trace_id: str = "",
) -> SearchPolicyOutput:
    """
    搜索政策文档。

    主链路（P1-1）: rag.pipeline 真实检索（Embedding → Milvus/BM25 → Reranker），
    返回语料中的文档并标注 mode。无语料/检索为空时显式降级到离线关键词 stub。

    Args:
        query: 用户查询文本
        top_k: 返回文档数量
        trace_id: 链路追踪 ID（透传，供审计关联）

    Returns:
        SearchPolicyOutput（含 mode: rag | bm25 | stub）
    """
    logger.info(
        "search_policy called: query='{}' top_k={} trace={}",
        query[:80], top_k, trace_id or "-",
    )

    # ── 1. 主链路：RAG 管线（常驻化单例） ──
    try:
        import time

        from rag.pipeline import get_pipeline

        t0 = time.perf_counter()
        rag_result = await get_pipeline().retrieve(query, top_k=top_k)
        latency_ms = (time.perf_counter() - t0) * 1000

        docs = rag_result.get("documents", [])
        mode = rag_result.get("mode", "empty")
        if docs:
            documents = [
                PolicyDocument(
                    document_id=_doc_id(d, idx),
                    title=d.get("title", f"政策文档{idx + 1}"),
                    content=d.get("content", "")[:300],
                    source=d.get("source", ""),
                    score=_normalize_score(d.get("score", d.get("relevance_score", 0.5))),
                )
                for idx, d in enumerate(docs[:top_k])
            ]
            logger.info(
                "RAG 检索完成: mode={} docs={} latency={:.1f}ms trace={}",
                mode, len(documents), latency_ms, trace_id or "-",
            )
            return SearchPolicyOutput(
                documents=documents,
                total_found=len(docs),
                mode=mode,
            )
        logger.info(
            "RAG 检索无结果（mode={}），降级到离线关键词 stub (trace={})",
            mode, trace_id or "-",
        )
    except Exception as e:
        logger.warning("RAG 管线不可用，降级到离线关键词 stub (trace={}): {}", trace_id or "-", e)

    # ── 2. 显式降级：离线关键词匹配 ──
    scored: list[tuple[dict[str, Any], float]] = []
    query_lower = query.lower()

    for policy in _STUB_POLICIES:
        score = _compute_keyword_score(query_lower, policy.get("keywords", []))
        if score > 0:
            scored.append((policy, score))

    # 按分数排序
    scored.sort(key=lambda x: x[1], reverse=True)

    # 取 top_k
    stub_documents: list[PolicyDocument] = []
    for policy, score in scored[:top_k]:
        stub_documents.append(PolicyDocument(
            document_id=policy["document_id"],
            title=policy["title"],
            content=policy["content"][:300],
            source=policy["source"],
            score=round(score, 2),
        ))

    # 如果关键词无匹配，返回通用政策
    if not stub_documents:
        general = _STUB_POLICIES[0]  # 食品经营许可
        stub_documents.append(PolicyDocument(
            document_id=general["document_id"],
            title=general["title"],
            content=general["content"][:300],
            source=general["source"],
            score=0.3,
        ))

    return SearchPolicyOutput(
        documents=stub_documents,
        total_found=len(scored),
        mode="stub",
    )


def _doc_id(doc: dict, idx: int) -> str:
    """从检索结果提取文档 ID（语料无 document_id 时用 title 或序号兜底）。"""
    did = doc.get("document_id") or doc.get("id")
    if did:
        return str(did)
    return f"POL-{idx + 1:03d}"


def _normalize_score(raw: float) -> float:
    """将 RAG 分数规整到 [0, 1]（RRF 融合分可能小于 0.3）。"""
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return round(max(0.0, min(1.0, score)), 4)


def _compute_keyword_score(query: str, keywords: list[str]) -> float:
    """基于关键词匹配的简单评分（stub 模式）"""
    if not query or not keywords:
        return 0.0

    matches = sum(1 for kw in keywords if kw in query)
    if matches == 0:
        return 0.0

    # 匹配越多分越高，最高 0.95
    return min(0.95, 0.5 + matches * 0.15)


# ============================================================
# get_policy_detail
# ============================================================


async def get_policy_detail(document_id: str) -> GetPolicyDetailOutput:
    """
    获取指定政策文档的详细内容。

    当前为 stub 实现：从本地语料库查找。
    后续从 PostgreSQL/Milvus 获取。

    Args:
        document_id: 政策文档ID

    Returns:
        GetPolicyDetailOutput
    """
    logger.info("get_policy_detail called: document_id={}", document_id)

    # ── Stub: 从本地语料库查找 ──
    for policy in _STUB_POLICIES:
        if policy["document_id"] == document_id:
            return GetPolicyDetailOutput(
                document_id=policy["document_id"],
                title=policy["title"],
                content=policy["content"],
                source=policy["source"],
                publish_date=policy.get("publish_date", ""),
                department=policy.get("department", ""),
            )

    # 未找到
    return GetPolicyDetailOutput(
        document_id=document_id,
        title="未知文档",
        content="未找到该文档的详细内容。",
        source="",
    )
