"""留出集只检查文件本身，不加载 BERT。"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LABELS = {
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
}


def test_holdout_covers_labels_and_stays_out_of_training():
    holdout = json.loads((_ROOT / "cases" / "intent_holdout.json").read_text(encoding="utf-8"))
    cases = holdout[0]["cases"]
    assert len(cases) >= 50
    counts = {label: 0 for label in _LABELS}
    queries = []
    for case in cases:
        assert case["expected_intent"] in _LABELS
        assert case["query"].strip()
        counts[case["expected_intent"]] += 1
        queries.append(case["query"])
    assert len(queries) == len(set(queries))
    assert all(count >= 5 for count in counts.values())

    training = json.loads((_ROOT / "cases" / "intent_cases.json").read_text(encoding="utf-8"))
    trained = {item["query"] for item in training[0]["cases"]}
    leaked = [query for query in queries if query in trained]
    assert leaked == []

    train_script = (_ROOT / "scripts" / "train_intent_bert.py").read_text(encoding="utf-8")
    assert "intent_holdout.json" not in train_script
