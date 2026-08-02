"""
scripts.download_models - 从 ModelScope 下载嵌入模型和重排序模型

Author: le
Date: 2026/7/30
Version: 0.2
Task: Download BGE embedding model and reranker model to models/ directory

ModelScope 是国内可访问的模型库（阿里云），速度远快于 HuggingFace。

Usage:
    python scripts/download_models.py              # 下载所有模型
    python scripts/download_models.py --dry-run    # 仅列出需要下载的模型
    python scripts/download_models.py --embedding-only  # 只下载嵌入模型
    python scripts/download_models.py --reranker-only   # 只下载重排序模型
    python scripts/download_models.py --source hf  # 从 HuggingFace 下载（需代理）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# 模型清单
# ============================================================


MODELS = [
    {
        "name": "embedding",
        "model_id": "BAAI/bge-large-zh-v1.5",
        "local_dir": "models/embedding/bge-large-zh-v1.5",
        "description": "BGE 中文嵌入模型（1024维），用于政策文档向量化和语义检索",
        "size_hint": "~1.3 GB",
    },
    {
        "name": "reranker",
        "model_id": "BAAI/bge-reranker-v2-m3",
        "local_dir": "models/reranker/bge-reranker-v2-m3",
        "description": "BGE 跨语言重排序模型，用于检索结果的精排",
        "size_hint": "~2.3 GB",
    },
]


# ============================================================
# 下载逻辑
# ============================================================


def check_model_status(model: dict) -> str:
    """
    检查模型下载状态。

    Returns:
        "ready" | "partial" | "missing"
    """
    local_path = Path(model["local_dir"])
    if not local_path.exists():
        return "missing"

    has_config = (local_path / "config.json").exists()
    has_model = (
        (local_path / "pytorch_model.bin").exists()
        or (local_path / "model.safetensors").exists()
    )

    if has_config and has_model:
        return "ready"
    elif has_config or (local_path / ".incomplete").exists():
        return "partial"
    else:
        return "missing"


def download_from_modelscope(model: dict, dry_run: bool = False) -> bool:
    """
    从 ModelScope 下载模型。

    Args:
        model: 模型定义 dict
        dry_run: True 时仅打印不下载

    Returns:
        是否成功/已就绪
    """
    from modelscope import snapshot_download

    local_path = Path(model["local_dir"])
    status = check_model_status(model)

    if status == "ready":
        print(f"  [{model['name']}] 已就绪: {local_path}")
        return True

    if dry_run:
        print(f"  [{model['name']}] 需要下载: {model['model_id']} ({model['size_hint']})")
        print(f"          目标路径: {local_path}")
        print(f"          来源: ModelScope (国内镜像)")
        return False

    print(f"  [{model['name']}] 正在从 ModelScope 下载 {model['model_id']}...")
    print(f"          目标路径: {local_path}")
    print(f"          预计大小: {model['size_hint']}")
    print(f"          首次下载需要几分钟，请耐心等待...")

    try:
        # 确保父目录存在
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # ModelScope snapshot_download（自动使用国内 CDN）
        downloaded = snapshot_download(
            model["model_id"],
            local_dir=str(local_path),
        )

        print(f"  [{model['name']}] 下载完成! -> {downloaded}")
        # 清理未完成标记（如果有）
        incomplete = local_path / ".incomplete"
        if incomplete.exists():
            incomplete.unlink()
        return True

    except Exception as e:
        print(f"  [{model['name']}] 下载失败: {e}")
        # 标记未完成
        local_path.mkdir(parents=True, exist_ok=True)
        (local_path / ".incomplete").touch()
        return False


def download_from_huggingface(model: dict, dry_run: bool = False) -> bool:
    """
    从 HuggingFace 下载模型（需要代理或 hf-mirror.com）。

    使用方式:
        set HF_ENDPOINT=https://hf-mirror.com
        python scripts/download_models.py --source hf
    """
    from huggingface_hub import snapshot_download

    local_path = Path(model["local_dir"])
    status = check_model_status(model)

    if status == "ready":
        print(f"  [{model['name']}] 已就绪: {local_path}")
        return True

    if dry_run:
        print(f"  [{model['name']}] 需要下载: {model['model_id']} ({model['size_hint']})")
        return False

    print(f"  [{model['name']}] 正在从 HuggingFace 下载 {model['model_id']}...")
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
    print(f"          端点: {endpoint}")

    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)

        snapshot_download(
            repo_id=model["model_id"],
            local_dir=str(local_path),
            local_dir_use_symlinks=False,
        )

        print(f"  [{model['name']}] 下载完成!")
        return True

    except Exception as e:
        print(f"  [{model['name']}] 下载失败: {e}")
        print(f"          提示: 设置 HF_ENDPOINT=https://hf-mirror.com 使用镜像")
        return False


# ============================================================
# 入口
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="下载模型文件")
    parser.add_argument("--dry-run", action="store_true", help="仅列出需要下载的模型")
    parser.add_argument("--embedding-only", action="store_true", help="只下载嵌入模型")
    parser.add_argument("--reranker-only", action="store_true", help="只下载重排序模型")
    parser.add_argument(
        "--source",
        choices=["modelscope", "hf"],
        default="modelscope",
        help="下载源: modelscope (默认，国内可用) | hf (HuggingFace，需代理)",
    )
    args = parser.parse_args()

    # 筛选模型
    if args.embedding_only:
        targets = [m for m in MODELS if m["name"] == "embedding"]
    elif args.reranker_only:
        targets = [m for m in MODELS if m["name"] == "reranker"]
    else:
        targets = MODELS

    # 选择下载函数
    download_fn = download_from_modelscope if args.source == "modelscope" else download_from_huggingface

    print()
    print("=" * 60)
    print(f"  模型下载 — {args.source.upper()}" + (" (预览模式)" if args.dry_run else ""))
    print("=" * 60)
    print()

    # 打印清单
    for model in targets:
        status = check_model_status(model)
        icon = {"ready": "[OK]", "partial": "[部分]", "missing": "[待下载]"}[status]
        print(f"  {icon} {model['name']}: {model['model_id']}")
        print(f"       {model['description']}")
        print(f"       大小: {model['size_hint']}")
        print(f"       本地: {model['local_dir']}")
        print()

    if args.dry_run:
        print("=" * 60)
        print("  (预览模式结束，移除 --dry-run 进行实际下载)")
        print("=" * 60)
        print()
        return

    # 下载
    print("── 开始下载 ──")
    print(f"   源: {args.source.upper()}")
    print()
    success = 0
    failed = 0

    for model in targets:
        if download_fn(model, dry_run=False):
            success += 1
        else:
            failed += 1
        print()

    print("=" * 60)
    print(f"  完成: {success} 成功, {failed} 失败, {len(targets)} 总计")
    if failed > 0:
        print(f"  提示: 失败可重试，已下载的部分不会丢失")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
