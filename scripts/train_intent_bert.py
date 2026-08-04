"""
train_intent_bert.py — 政务意图分类 BERT 微调训练

Author: le
Date: 2026/8/4
Version: 0.1
Task: Fine-tune bert-base-chinese on augmented gov-service intent data
      for the IntentClassifier in agents/intent/classifier.py.

Usage:
    # 仅训练
    python scripts/train_intent_bert.py

    # 训练 + 预下载模型（首次需联网下载 bert-base-chinese）
    python scripts/train_intent_bert.py --download

    # 自定义输出路径
    python scripts/train_intent_bert.py --output models/intent/bert-intent-v2

Requirements:
    pip install transformers[torch] datasets accelerate scikit-learn

产物 (output_dir = models/intent/bert-intent/):
    config.json              # AutoModelForSequenceClassification config
    pytorch_model.bin        # 微调后的权重
    tokenizer.json           # tokenizer 文件
    tokenizer_config.json    # tokenizer 配置
    special_tokens_map.json  # special tokens 映射
    training_args.json       # 训练超参（可复现）

验证方式:
    from agents.intent.classifier import IntentClassifier
    c = IntentClassifier(model_path="models/intent/bert-intent")
    assert c.is_model_loaded
    for case in load_test_cases():
        r = await c.classify(case["query"])
        assert r.source == "bert"
        print(f"{r.label} | conf={r.confidence:.3f} | {case['query']}")
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

# ── project root ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ── constants aligned with agents.intent.schema ──
LABEL_IDS = [
    "business_license",
    "restaurant_license",
    "business_register",
    "fund_query",
    "property_service",
    "medical_insurance",
    "social_security",
    "tax_service",
    "policy_query",
    "other",
]

LABEL_NAMES: dict[str, str] = {
    "business_license": "营业执照办理",
    "restaurant_license": "餐饮许可",
    "business_register": "企业注册",
    "fund_query": "公积金查询",
    "property_service": "不动产服务",
    "medical_insurance": "医保服务",
    "social_security": "社保服务",
    "tax_service": "税务服务",
    "policy_query": "政策咨询",
    "other": "其他事项",
}

# index → label_id (same as IntentClassifier._id2label)
ID2LABEL: dict[int, str] = {i: lbl for i, lbl in enumerate(LABEL_IDS)}
LABEL2ID: dict[str, int] = {lbl: i for i, lbl in enumerate(LABEL_IDS)}
NUM_LABELS: int = len(LABEL_IDS)

# ============================================================
# ── Data Augmentation — 基于关键词的政务意图语料增强 ──
# ============================================================

def _build_augmented_cases() -> list[dict[str, str]]:
    """
    每个标签生成 12-18 条变体，覆盖不同口语表达。

    策略:
      - 核心关键词替换（如 餐馆/饭店/餐厅/面馆/小吃）
      - 句式变化（陈述句 / 疑问句 / 祈使句 / 口语）
      - 加入语气词和常见政务咨询用语

    Returns:
        list of {"query": str, "label": str}
    """

    variants: dict[str, list[str]] = {
        # ── business_license — 营业执照办理 ──
        "business_license": [
            "我要办理营业执照",
            "营业执照怎么办",
            "开个体户需要什么执照",
            "办个营业执照需要几天",
            "营业执照办理流程是什么",
            "怎么申请营业执照",
            "营业执照需要的材料有哪些",
            "个体户营业执照网上能办吗",
            "营业执照在哪儿办",
            "营业执照年检怎么弄",
            "我要注销营业执照",
            "营业执照变更经营范围怎么弄",
            "营业执照到期了怎么换",
            "开小店需要办执照吗",
        ],
        # ── restaurant_license — 餐饮许可 ──
        "restaurant_license": [
            "我想开个餐馆需要什么手续",
            "开饭店要办什么证",
            "餐饮许可证怎么办理",
            "食品经营许可证需要哪些材料",
            "开奶茶店需要办什么手续",
            "小吃店要办营业执照和食品证吗",
            "开火锅店需要什么证照",
            "餐厅开业的审批流程是什么",
            "开面馆需要申请什么许可",
            "做餐饮行业需要什么资质",
            "开咖啡厅需要卫生许可证吗",
            "食堂承包需要什么手续",
            "外卖店需要办什么证",
            "烧烤摊要办证吗",
            "开烘焙坊需要食品许可吗",
        ],
        # ── business_register — 企业注册 ──
        "business_register": [
            "我要注册一家公司",
            "注册科技公司需要什么材料",
            "公司注册流程是怎样的",
            "怎么开一家有限责任公司",
            "注册公司需要多少钱",
            "公司核名怎么弄",
            "企业工商注册在哪儿办",
            "注册公司需要法人到场吗",
            "新公司注册需要多长时间",
            "注册一个外贸公司要什么手续",
            "合伙企业怎么注册",
            "公司注册地址有什么要求",
            "注册电商公司需要什么",
        ],
        # ── fund_query — 公积金查询 ──
        "fund_query": [
            "公积金怎么查询余额",
            "公积金怎么提取",
            "住房公积金贷款条件是什么",
            "公积金可以取出来吗",
            "公积金最多能贷多少",
            "公积金贷款利率是多少",
            "如何办理公积金贷款",
            "公积金账户怎么激活",
            "公积金异地转移怎么弄",
            "公积金断交了怎么办",
            "离职后公积金怎么办",
            "公积金可以网上提取吗",
            "公积金缴存比例是多少",
        ],
        # ── property_service — 不动产服务 ──
        "property_service": [
            "房产过户需要什么材料",
            "不动产登记在哪儿办",
            "房屋买卖过户流程是什么",
            "二手房交易需要什么手续",
            "不动产证怎么办理",
            "房产证丢了怎么补办",
            "房屋抵押登记怎么办",
            "产权变更需要什么材料",
            "商品房网签流程是什么",
            "不动产信息怎么查询",
            "房子过户给子女要什么手续",
            "房屋赠与需要交税吗",
            "房产继承怎么办理",
        ],
        # ── medical_insurance — 医保服务 ──
        "medical_insurance": [
            "医保报销政策是什么",
            "医保卡怎么办理",
            "医疗保险报销比例是多少",
            "居民医保和职工医保有什么区别",
            "异地就医怎么报销",
            "医保报销需要什么材料",
            "门诊能报销多少",
            "住院报销流程是什么",
            "医保断缴了怎么办",
            "新生儿医保怎么办理",
            "医保个人账户怎么查询",
            "大病医保怎么申请",
            "医保是否可以家庭共用",
        ],
        # ── social_security — 社保服务 ──
        "social_security": [
            "社保卡怎么办理",
            "社会保险怎么交",
            "社保断了怎么补缴",
            "灵活就业人员怎么交社保",
            "养老金怎么计算",
            "养老保险要交多少年",
            "社保怎么转移到新单位",
            "社保卡丢了怎么补办",
            "失业保险金怎么领取",
            "生育保险怎么报销",
            "工伤认定怎么申请",
            "社保缴费基数是什么",
            "社保卡激活需要什么材料",
        ],
        # ── tax_service — 税务服务 ──
        "tax_service": [
            "发票怎么开具",
            "个人所得税怎么申报",
            "小规模纳税人怎么报税",
            "企业所得税税率是多少",
            "税务申报逾期了怎么办",
            "个体户需要交哪些税",
            "发票开错了怎么作废",
            "怎么查询纳税记录",
            "增值税怎么计算",
            "开公司需要交什么税",
            "发票增版增量怎么申请",
            "出口退税怎么办理",
            "个税专项附加扣除有哪些",
            "企业税务注销怎么办理",
        ],
        # ── policy_query — 政策咨询 ──
        "policy_query": [
            "最近有什么新的惠企政策",
            "政府补贴怎么申请",
            "小微企业有什么扶持政策",
            "创业补贴怎么领",
            "政府发布的营商环境政策有哪些",
            "招商引资有什么优惠政策",
            "人才引进有什么政策支持",
            "最新的减税降费政策是什么",
            "科技创新补贴怎么申请",
            "政府对企业有什么优惠",
            "中小企业扶持政策有哪些",
            "最新的行政审批改革是什么",
            "放管服改革具体说了什么",
        ],
        # ── other — 其他事项 ──
        "other": [
            "你好",
            "在吗",
            "今天天气怎么样",
            "帮我写一首诗",
            "推荐一个旅游景点",
            "附近有什么好玩的",
            "帮我算一下这个月的开销",
            "这个代码怎么写",
            "什么是区块链",
            "今天星期几",
            "帮我翻译一段英文",
            "告诉我一个冷笑话",
            "能帮我做个PPT吗",
        ],
    }

    cases: list[dict[str, str]] = []
    for label_id in LABEL_IDS:
        for q in variants[label_id]:
            cases.append({"query": q, "label": label_id})

    return cases


def load_golden_cases(path: str | None = None) -> list[dict[str, str]]:
    """从 cases/intent_cases.json 加载所有语料（用于训练+验证）"""
    if path is None:
        path = str(_PROJECT_ROOT / "cases" / "intent_cases.json")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases: list[dict[str, str]] = []
    for item in data:
        if "cases" in item:
            for c in item["cases"]:
                cases.append({"query": c["query"], "label": c["expected_intent"]})
        elif "query" in item and "expected_intent" in item:
            cases.append({"query": item["query"], "label": item["expected_intent"]})

    return cases


def load_anchor_cases() -> list[dict[str, str]]:
    """从 intent_cases.json 中每个标签取 1 条作为固定的验证锚点。"""
    intent_file = _PROJECT_ROOT / "cases" / "intent_cases.json"
    if not intent_file.exists():
        return []

    all_cases = load_golden_cases(str(intent_file))
    anchor: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for c in all_cases:
        label = c["label"]
        if label not in seen_labels:
            anchor.append(c)
            seen_labels.add(label)
        if len(seen_labels) >= 10:
            break
    return anchor


# ============================================================
# ── Dataset ──
# ============================================================


def build_dataset(texts: list[str], labels: list[int], tokenizer: Any):
    """Tokenize texts + labels → HuggingFace Dataset."""
    from datasets import Dataset  # type: ignore[import-untyped]

    encodings = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=64,
        return_tensors=None,  # return python lists for Dataset
    )

    return Dataset.from_dict({
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels,
    })


def split_train_val(
    cases: list[dict[str, str]],
    val_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """按标签分层切分 train/val，保证每个标签至少 1 条在 val 中。"""
    from sklearn.model_selection import train_test_split

    random.seed(seed)
    train, val = [], []

    for label_id in LABEL_IDS:
        label_cases = [c for c in cases if c["label"] == label_id]
        random.shuffle(label_cases)

        n_val = max(1, int(len(label_cases) * val_ratio))
        val.extend(label_cases[:n_val])
        train.extend(label_cases[n_val:])

    # anchor cases 固定进入 val（确保验收标准可测）
    golden = load_anchor_cases()
    golden_queries = {g["query"] for g in golden}
    val = [c for c in val if c["query"] not in golden_queries]
    val.extend(golden)
    # 从 train 中去掉 golden queries
    train = [c for c in train if c["query"] not in golden_queries]

    random.shuffle(train)
    random.shuffle(val)

    return train, val


# ============================================================
# ── Training ──
# ============================================================


def compute_metrics(eval_pred: Any):
    """HuggingFace Trainer compute_metrics callback."""
    import numpy as np
    from sklearn.metrics import accuracy_score, f1_score

    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = float(accuracy_score(labels, preds))
    f1 = float(f1_score(labels, preds, average="macro"))
    return {"accuracy": acc, "f1_macro": f1}


def train(
    output_dir: str,
    model_name: str = "bert-base-chinese",
    epochs: int = 12,
    batch_size: int = 16,
    learning_rate: float = 3e-5,
    warmup_ratio: float = 0.1,
    weight_decay: float = 0.01,
    seed: int = 42,
    offline: bool = False,
) -> float:
    """
    微调 bert-base-chinese 做政务意图分类。

    Returns:
        val_accuracy (float)
    """
    import torch
    from transformers import (  # type: ignore[import-untyped]
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(seed)

    # ── 1. 加载语料 ──
    print("=" * 60)
    print("1/5  加载训练语料 ...")

    # 优先使用 cases/intent_cases.json 的 3000+ 条语料
    intent_file = _PROJECT_ROOT / "cases" / "intent_cases.json"
    if intent_file.exists():
        cases = load_golden_cases(str(intent_file))
        print(f"     从 {intent_file.name} 加载: {len(cases)} 条")
    else:
        cases = _build_augmented_cases()
        print(f"     使用内置增强语料: {len(cases)} 条")

    # 不足时用内置模板补齐
    if len(cases) < 1000:
        print("     语料不足，补充内置增强模板 ...")
        extra = _build_augmented_cases()
        existing_queries = {c["query"] for c in cases}
        for c in extra:
            if c["query"] not in existing_queries:
                cases.append(c)
                existing_queries.add(c["query"])
        print(f"     合并后: {len(cases)} 条")

    train_cases, val_cases = split_train_val(cases)
    print(f"     训练集: {len(train_cases)} 条 | 验证集: {len(val_cases)} 条")

    # 打印每个标签的分布
    for label_id in LABEL_IDS:
        t_cnt = sum(1 for c in train_cases if c["label"] == label_id)
        v_cnt = sum(1 for c in val_cases if c["label"] == label_id)
        print(f"       {label_id:25s}  train={t_cnt:2d}  val={v_cnt:2d}")

    # ── 2. 加载预训练模型 ──
    print("\n2/5  加载 bert-base-chinese ...")
    load_kwargs = {"local_files_only": offline} if offline else {}
    tokenizer = AutoTokenizer.from_pretrained(model_name, **load_kwargs)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=NUM_LABELS,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        **load_kwargs,
    )

    # ── 3. Tokenize ──
    print("\n3/5  Tokenizing ...")
    train_texts = [c["query"] for c in train_cases]
    train_labels = [LABEL2ID[c["label"]] for c in train_cases]
    val_texts = [c["query"] for c in val_cases]
    val_labels = [LABEL2ID[c["label"]] for c in val_cases]

    train_ds = build_dataset(train_texts, train_labels, tokenizer)
    val_ds = build_dataset(val_texts, val_labels, tokenizer)
    print(f"     train={len(train_ds)}, val={len(val_ds)}")

    # ── 4. 训练 ──
    print("\n4/5  开始微调训练 ...")

    # 自动选择设备
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"     设备: {device}")

    args = TrainingArguments(
        output_dir=os.path.join(output_dir, ".checkpoints"),
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        warmup_ratio=warmup_ratio,
        weight_decay=weight_decay,
        seed=seed,
        report_to="none",  # 不上报 wandb/tensorboard
        save_total_limit=2,
        remove_unused_columns=True,
        fp16=(device == "cuda"),  # GPU 使用混合精度加速
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
    )

    trainer.train()

    # ── 5. 评估 + 保存 ──
    print("\n5/5  评估并保存模型 ...")
    eval_result = trainer.evaluate()
    acc = eval_result.get("eval_accuracy", 0.0)
    f1 = eval_result.get("eval_f1_macro", 0.0)
    loss = eval_result.get("eval_loss", float("nan"))

    print(f"      准确率 (accuracy): {acc:.4f} ({acc*100:.1f}%)")
    print(f"      Macro F1:          {f1:.4f}")
    print(f"      Loss:              {loss:.4f}")

    # 保存最终模型
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # 额外保存训练超参（可复现）
    training_config = {
        "model_name": model_name,
        "num_labels": NUM_LABELS,
        "id2label": ID2LABEL,
        "label2id": LABEL2ID,
        "label_names": LABEL_NAMES,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "warmup_ratio": warmup_ratio,
        "weight_decay": weight_decay,
        "train_size": len(train_cases),
        "val_size": len(val_cases),
        "val_accuracy": acc,
        "val_f1_macro": f1,
        "val_loss": loss,
    }
    with open(os.path.join(output_dir, "training_args.json"), "w", encoding="utf-8") as f:
        json.dump(training_config, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 模型已保存到: {output_dir}")
    print(f"   文件: {', '.join(os.listdir(output_dir))}")

    return float(acc)


# ============================================================
# ── Verification ──
# ============================================================


def verify(model_path: str) -> bool:
    """
    验证微调后的模型是否可被 IntentClassifier 正确加载，
    且 golden cases 全部推理正确。
    """
    print("\n" + "=" * 60)
    print("验证: IntentClassifier 加载微调模型 ...")

    from agents.intent.classifier import IntentClassifier

    classifier = IntentClassifier(model_path=model_path, auto_load=True)

    if not classifier.is_model_loaded:
        print("[FAIL] classifier.is_model_loaded = False — 模型未被加载")
        return False

    print(f"[OK] 模型已加载: source check OK")

    # 对 golden cases 逐个推理
    import asyncio

    anchor = load_anchor_cases()
    passed = 0
    total = len(anchor)

    async def _run():
        nonlocal passed
        for case in anchor:
            r = await classifier.classify(case["query"])
            ok = r.source == "bert" and r.label == case["label"]
            status = "[OK]" if ok else "[FAIL]"
            print(f"   {status} query='{case['query']}' → {r.label} "
                  f"(expected={case['label']}, conf={r.confidence:.3f}, source={r.source})")
            if ok:
                passed += 1
        return passed

    asyncio.run(_run())

    acc = passed / total
    print(f"\n   验证结果: {passed}/{total} ({acc:.1%})")
    if acc >= 0.9:
        print("[OK] 验收通过: 准确率 ≥ 90%")
    else:
        print(f"[WARN]  准确率 {acc:.1%} < 90%，可能需要更多训练数据或调参")

    return acc >= 0.9


# ============================================================
# ── CLI ──
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="政务意图分类 BERT 微调训练",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/train_intent_bert.py
  python scripts/train_intent_bert.py --epochs 15 --lr 2e-5
  python scripts/train_intent_bert.py --output models/intent/bert-intent-v2 --skip-verify
        """,
    )
    parser.add_argument(
        "--model-name", default="bert-base-chinese",
        help="HuggingFace 预训练模型名 (default: bert-base-chinese)",
    )
    parser.add_argument(
        "--output", default=None,
        help="模型输出目录 (default: models/intent/bert-intent/)",
    )
    parser.add_argument(
        "--epochs", type=int, default=12,
        help="训练轮数 (default: 12)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=16,
        help="batch size (default: 16)",
    )
    parser.add_argument(
        "--lr", type=float, default=3e-5,
        help="学习率 (default: 3e-5)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="随机种子 (default: 42)",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="离线模式，仅从本地缓存加载模型（不联网）",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="跳过训练后验证",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="仅验证已有模型，不训练",
    )
    args = parser.parse_args()

    output_dir = args.output or str(
        _PROJECT_ROOT / "models" / "intent" / "bert-intent"
    )

    if args.verify_only:
        ok = verify(output_dir)
        sys.exit(0 if ok else 1)
        return

    # ── 训练 ──
    acc = train(
        output_dir=output_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        seed=args.seed,
        offline=args.offline,
    )

    # ── 验证 ──
    if not args.skip_verify:
        ok = verify(output_dir)
        if not ok:
            print("\n[WARN]  验证未通过，但模型已保存。可调参后重试。")
            sys.exit(1)

    # 验收判断
    if acc >= 0.9:
        print(f"\n[DONE] 训练完成! 验证集准确率 {acc:.1%} ≥ 90%，验收通过。")
    else:
        print(f"\n[WARN]  验证集准确率 {acc:.1%} < 90%，建议: ")
        print("    1. 增加训练轮数: --epochs 15")
        print("    2. 降低学习率: --lr 2e-5")
        print("    3. 增强更多语料变体")


if __name__ == "__main__":
    main()
