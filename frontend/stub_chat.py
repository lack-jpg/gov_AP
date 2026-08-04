"""
frontend.stub_chat — 本地 stub 对话模式（后端不可用时的降级方案）

不依赖 FastAPI 后端，直接本地运行简化 Agent 工作流：
  意图分类（BERT） → 政策检索（stub 模板） → 安全护栏（PII 脱敏） → 回答

用于演示场景：启动前端即可体验完整对话流程，无需启动后端。
后端可用时自动切换为真实 API 模式（见 api_client.chat_with_fallback）。

Author: le
Date: 2026/8/4
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

# 确保项目根目录在 sys.path 中（与 common.setup_paths 一致）
_frontend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_frontend_dir)
for _p in (_frontend_dir, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ============================================================
# 意图标签 → 中文名映射（与 agents/intent/classifier.py 同步）
# ============================================================

INTENT_LABEL_NAMES: dict[str, str] = {
    "business_license": "营业执照办理",
    "business_register": "企业注册",
    "restaurant_license": "餐饮许可",
    "fund_query": "公积金查询",
    "property_service": "不动产服务",
    "social_security": "社保服务",
    "tax_service": "税务服务",
    "medical_service": "医疗服务",
    "education_service": "教育服务",
    "other": "其他咨询",
}


# ============================================================
# Stub 政策模板（与 orchestration/langgraph/nodes._stub_policy_search 同步）
# ============================================================

_STUB_TEMPLATES: dict[str, str] = {
    "restaurant": (
        "开办餐馆需要以下手续：\n\n"
        "**1. 营业执照** — 到当地市场监管局办理\n"
        "**2. 食品经营许可证** — 到食品药品监督管理部门办理\n"
        "**3. 消防安全检查合格证** — 到消防部门办理\n"
        "**4. 环保审批** — 根据当地环保要求办理\n\n"
        "**基本材料清单：**\n"
        "- 经营者身份证原件及复印件\n"
        "- 经营场所证明（租赁合同或房产证）\n"
        "- 从业人员健康证\n"
        "- 食品安全管理制度文本\n"
        "- 经营场所平面图"
    ),
    "business_license": (
        "办理营业执照所需材料和流程：\n\n"
        "**所需材料：**\n"
        "1. 《公司登记（备案）申请书》\n"
        "2. 公司章程（全体股东签署）\n"
        "3. 股东身份证明\n"
        "4. 法定代表人、董事、监事和经理的任职文件及身份证明\n"
        "5. 经营场所使用证明（房产证或租赁合同）\n"
        "6. 名称预先核准通知书\n\n"
        "**办理流程：**\n"
        "第一步：名称预先核准（1-3个工作日）\n"
        "第二步：提交设立登记申请（5-15个工作日）\n"
        "第三步：领取营业执照\n"
        "第四步：刻制公章、财务章等\n"
        "第五步：税务登记、银行开户"
    ),
    "business_register": (
        "企业注册基本流程：\n\n"
        "**第一阶段：核名**\n"
        "1. 准备 3-5 个公司备选名称\n"
        "2. 到当地市场监管局或通过「一网通办」平台核名\n"
        "3. 领取《名称预先核准通知书》\n\n"
        "**第二阶段：设立登记**\n"
        "1. 提交设立登记申请材料\n"
        "2. 材料包括：公司章程、股东决议、法人身份证、场所证明\n"
        "3. 市场监管局审核（5-15个工作日）\n\n"
        "**第三阶段：后续手续**\n"
        "1. 领取营业执照\n"
        "2. 刻制公章（公安备案）\n"
        "3. 税务登记（税务局）\n"
        "4. 银行开立基本户\n"
        "5. 社保、公积金开户"
    ),
    "fund_query": (
        "公积金查询方式和提取条件：\n\n"
        "**查询方式：**\n"
        "1. 登录「住房公积金管理中心」官网或 APP\n"
        "2. 拨打 12329 住房公积金服务热线\n"
        "3. 持身份证到公积金服务大厅自助终端查询\n"
        "4. 支付宝/微信城市服务 → 公积金查询\n\n"
        "**提取条件（常见）：**\n"
        "- 购买、建造、翻建自住住房\n"
        "- 偿还购房贷款本息\n"
        "- 租房（需提供租赁合同）\n"
        "- 离休、退休\n"
        "- 完全丧失劳动能力\n"
        "- 出境定居"
    ),
    "property_service": (
        "不动产登记（房产过户）所需材料：\n\n"
        "**买卖过户：**\n"
        "1. 不动产登记申请书\n"
        "2. 申请人身份证明（买卖双方）\n"
        "3. 不动产权属证书（房产证）\n"
        "4. 买卖合同\n"
        "5. 契税完税证明\n"
        "6. 测绘报告（如涉及面积变更）\n\n"
        "**办理流程：**\n"
        "第一步：网签合同（不动产登记中心或中介）\n"
        "第二步：缴纳税费（契税、增值税等）\n"
        "第三步：提交登记申请\n"
        "第四步：审核（5-15个工作日）\n"
        "第五步：领取新的不动产权证书"
    ),
    "social_security": (
        "社保卡办理与服务：\n\n"
        "**社保卡办理：**\n"
        "1. 首次申领：持身份证到社保卡服务网点或合作银行\n"
        "2. 线上申领：通过「国家社会保险公共服务平台」或各地人社 APP\n"
        "3. 补换卡：到原发卡银行网点办理，立等可取\n\n"
        "**常见服务：**\n"
        "- 养老保险关系转移接续\n"
        "- 医疗保险异地就医备案\n"
        "- 失业保险金申领\n"
        "- 工伤保险待遇申请\n"
        "- 社保缴费记录查询"
    ),
    "tax_service": (
        "个人/企业税务服务指南：\n\n"
        "**个人所得税年度汇算：**\n"
        "1. 下载「个人所得税」APP\n"
        "2. 注册登录并完善个人信息\n"
        "3. 填报专项附加扣除（子女教育、房贷、租金等）\n"
        "4. 系统自动计算应退/应补税额\n"
        "5. 申请退税或补缴税款\n\n"
        "**企业税务登记：**\n"
        "1. 持营业执照到主管税务机关办理\n"
        "2. 核定税种（增值税、企业所得税等）\n"
        "3. 购买/开具发票\n"
        "4. 按期进行纳税申报（月度/季度/年度）"
    ),
    "medical_service": (
        "医疗保险服务指南：\n\n"
        "**城乡居民医保参保：**\n"
        "1. 持身份证/户口本到社区（村）委会登记\n"
        "2. 缴纳年度保费\n"
        "3. 领取社保卡（已开通医保功能）\n\n"
        "**异地就医直接结算：**\n"
        "1. 在参保地医保部门办理异地就医备案\n"
        "2. 选择就医地已开通直接结算的定点医院\n"
        "3. 持社保卡就医，出院时直接结算\n\n"
        "**门诊慢特病待遇申请：**\n"
        "1. 到定点医院开具诊断证明\n"
        "2. 填写《门诊慢特病待遇申请表》\n"
        "3. 提交到医保经办机构审核"
    ),
    "education_service": (
        "教育相关政务服务：\n\n"
        "**子女入学报名：**\n"
        "1. 关注当地教育局发布的招生政策\n"
        "2. 准备户口本、房产证（或租赁备案）、出生证明等材料\n"
        "3. 通过「义务教育招生入学平台」线上报名\n"
        "4. 现场资料核验\n"
        "5. 领取入学通知书\n\n"
        "**教师资格认定：**\n"
        "1. 通过教师资格考试（笔试+面试）\n"
        "2. 取得普通话等级证书\n"
        "3. 到指定医院体检\n"
        "4. 网上申报认定\n"
        "5. 现场确认并领取教师资格证"
    ),
}

# 默认通用回答
_DEFAULT_ANSWER = (
    "根据您的需求，建议准备以下基础材料：\n\n"
    "1. 本人有效身份证件原件及复印件\n"
    "2. 相关申请表（可在政务大厅领取或网上下载）\n"
    "3. 根据具体办理事项可能需要补充的其他材料\n\n"
    "建议先确认具体办理事项，或前往当地政务服务中心（市民中心）窗口咨询。\n"
    "也可以通过「一网通办」政务服务平台在线查询和办理。"
)


# ============================================================
# 意图关键词 → 模板映射
# ============================================================

def _match_intent_to_template(intent: str, query: str) -> str:
    """将意图标签映射到对应的 stub 模板答案"""
    # 优先用 query 中的关键词
    keywords = {
        "餐馆": "restaurant", "川菜": "restaurant", "餐饮": "restaurant",
        "饭店": "restaurant", "食品": "restaurant", "餐厅": "restaurant",
        "注册": "business_register", "公司": "business_register",
        "营业执照": "business_license", "执照": "business_license",
        "公积金": "fund_query",
        "房产": "property_service", "过户": "property_service", "买房": "property_service",
        "不动产": "property_service",
        "社保": "social_security", "医保": "medical_service",
        "医疗": "medical_service", "看病": "medical_service",
        "税务": "tax_service", "税": "tax_service", "个税": "tax_service",
        "教育": "education_service", "入学": "education_service", "上学": "education_service",
    }
    for kw, tmpl_key in keywords.items():
        if kw in query:
            return _STUB_TEMPLATES.get(tmpl_key, _DEFAULT_ANSWER)

    # fallback：按 intent 标签匹配
    intent_map = {
        "business_license": "business_license",
        "business_register": "business_register",
        "restaurant_license": "restaurant",
        "fund_query": "fund_query",
        "property_service": "property_service",
        "social_security": "social_security",
        "medical_service": "medical_service",
        "tax_service": "tax_service",
        "education_service": "education_service",
    }
    tmpl_key = intent_map.get(intent)
    if tmpl_key:
        return _STUB_TEMPLATES.get(tmpl_key, _DEFAULT_ANSWER)
    return _DEFAULT_ANSWER


# ============================================================
# 本地意图分类（BERT）
# ============================================================

# 模块级缓存
_classifier = None


def _get_classifier():
    """惰性加载 BERT IntentClassifier（单例）"""
    global _classifier
    if _classifier is None:
        from agents.intent.classifier import IntentClassifier
        _classifier = IntentClassifier()  # auto_load=True
    return _classifier


async def _classify_intent(query: str) -> dict[str, Any]:
    """使用 BERT 模型进行意图分类"""
    try:
        classifier = _get_classifier()
        result = await classifier.classify(query)
        return {
            "label": result.label,
            "label_name": result.label_name,
            "confidence": result.confidence,
            "source": result.source,
        }
    except Exception:
        # BERT 不可用时回退关键词匹配
        from agents.intent.classifier import IntentClassifier
        c = IntentClassifier(auto_load=False)
        result = c._keyword_classify(query)
        return {
            "label": result.label,
            "label_name": result.label_name,
            "confidence": result.confidence,
            "source": "keyword",
        }


# ============================================================
# 安全护栏（PII 脱敏）
# ============================================================

def _sanitize_output(text: str) -> str:
    """对输出文本进行 PII 脱敏和敏感词过滤"""
    try:
        from governance.pii import mask_pii
        return mask_pii(text)
    except ImportError:
        return text


# ============================================================
# 主入口 — 运行本地 stub 对话
# ============================================================

async def run_stub_chat(query: str, user_id: str = "demo_user") -> dict[str, Any]:
    """
    在本地运行简化的 Agent 工作流（无需后端 API）。

    流程：
      1. BERT 意图分类
      2. 策略搜索（stub 模板）
      3. 安全护栏（PII 脱敏）
      4. 组装响应

    Args:
        query: 用户输入
        user_id: 用户标识（stub 模式下用于生成 trace_id）

    Returns:
        dict，结构与后端 ChatResponse 一致：
        {
            "answer": str,
            "intent": str,
            "evidence": list[dict],
            "risk_level": str,
            "execution_steps": int,
            "elapsed_ms": float,
            "trace_id": str,
            "mode": "stub",          # 标记为 stub 模式
        }
    """
    trace_id = f"stub_{uuid.uuid4().hex[:12]}"
    t_start = time.perf_counter()

    # Step 1: 意图分类
    intent_result = await _classify_intent(query)
    intent = intent_result["label"]

    # Step 2: 政策搜索（stub 模板）
    answer = _match_intent_to_template(intent, query)
    label_name = intent_result.get("label_name") or INTENT_LABEL_NAMES.get(intent, "")

    # 构造回答（包含意图识别信息）
    full_answer = (
        f"**识别意图：{label_name}**（置信度 {intent_result['confidence']:.0%}，来源：{intent_result['source']}）\n\n"
        f"---\n\n"
        f"{answer}"
    )

    # Step 3: 安全护栏
    safe_answer = _sanitize_output(full_answer)

    # Step 4: 构造 evidence
    evidence = []
    tmpl_key = None
    intent_to_tmpl = {
        "business_license": "business_license", "business_register": "business_register",
        "restaurant_license": "restaurant", "fund_query": "fund_query",
        "property_service": "property_service", "social_security": "social_security",
        "medical_service": "medical_service", "tax_service": "tax_service",
        "education_service": "education_service",
    }
    tmpl_key = intent_to_tmpl.get(intent)
    if tmpl_key and tmpl_key in _STUB_TEMPLATES:
        evidence.append({
            "source": f"政务知识库 — {label_name}",
            "excerpt": _STUB_TEMPLATES[tmpl_key][:200],
            "relevance_score": round(intent_result["confidence"], 2),
        })

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    return {
        "answer": safe_answer,
        "intent": intent,
        "evidence": evidence,
        "risk_level": "low",
        "execution_steps": 3,  # intent + policy + guardrail
        "elapsed_ms": elapsed_ms,
        "trace_id": trace_id,
        "mode": "stub",
    }
