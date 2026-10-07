"""在手写留出集上评估意图 BERT。

不进入默认 pytest。模型权重不在仓库里时退出码为 2，并说明未加载。

用法:
    python scripts/eval_intent_holdout.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_HOLDOUT = _PROJECT_ROOT / "cases" / "intent_holdout.json"
_MODEL = _PROJECT_ROOT / "models" / "intent" / "bert-intent"


def load_holdout() -> list[dict[str, str]]:
    """读取留出集。训练脚本不得调用本函数。"""
    with _HOLDOUT.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    cases = payload[0]["cases"] if isinstance(payload, list) else payload["cases"]
    return [
        {"query": item["query"], "label": item["expected_intent"]}
        for item in cases
    ]


async def _run() -> int:
    if not (_MODEL / "model.safetensors").is_file() and not (_MODEL / "pytorch_model.bin").is_file():
        print(f"未加载模型: {_MODEL}")
        print("手写留出集未评分。模板验证集数字不能代替本脚本的输出。")
        return 2

    from agents.intent.classifier import IntentClassifier

    classifier = IntentClassifier(model_path=str(_MODEL), auto_load=True)
    if not classifier.is_model_loaded:
        print(f"未加载模型: {_MODEL}")
        return 2

    cases = load_holdout()
    correct = 0
    mistakes: list[str] = []
    for case in cases:
        result = await classifier.classify(case["query"])
        if result.source == "bert" and result.label == case["label"]:
            correct += 1
            continue
        mistakes.append(
            f"  {case['label']} -> {result.label} ({result.source}, {result.confidence:.2f}) | {case['query']}"
        )

    total = len(cases)
    accuracy = correct / total if total else 0.0
    print(f"手写留出集: {correct}/{total} = {accuracy:.4f} ({accuracy * 100:.1f}%)")
    print("模板验证集见 models/intent/bert-intent/training_args.json（val_accuracy，与本集不是同一批句子）。")
    if mistakes:
        print(f"分错 {len(mistakes)} 条:")
        print("\n".join(mistakes))
    return 0


def main() -> None:
    """命令行入口。"""
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
