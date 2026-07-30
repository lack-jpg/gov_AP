# models/ — 模型文件存储目录

> 本目录存放项目所需的所有本地模型文件。
> 模型文件体积较大（GB 级），已被 `.gitignore` 排除，不纳入版本管理。
> 请按照下方说明在目标环境中自行下载。

---

## 1. 模型清单

| 模型 | 用途 | 源 | 大小 | 存放路径 |
|------|------|-----|------|---------|
| bge-large-zh-v1.5 | Embedding 向量化 | BAAI | ~1.3 GB | `embedding/bge-large-zh-v1.5/` |
| bge-reranker-v2-m3 | 检索结果精排 | BAAI | ~2.3 GB | `reranker/bge-reranker-v2-m3/` |
| bert-intent | 意图分类 | 自训练 | ~400 MB | `intent/bert-intent/` |
| intent-v1 | 意图分类 v1（微调） | 自训练 | ~400 MB | `fine_tuned/intent-v1/` |
| ner | 命名实体识别（微调） | 自训练 | ~400 MB | `fine_tuned/ner/` |

---

## 2. 下载方式

### 方式一：HuggingFace CLI（推荐）

```bash
# 安装 huggingface_hub
pip install huggingface_hub

# Embedding 模型
huggingface-cli download BAAI/bge-large-zh-v1.5 --local-dir models/embedding/bge-large-zh-v1.5

# Reranker 模型
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir models/reranker/bge-reranker-v2-m3
```

### 方式二：ModelScope（国内加速）

```bash
pip install modelscope

# Embedding 模型
modelscope download --model BAAI/bge-large-zh-v1.5 --local_dir models/embedding/bge-large-zh-v1.5

# Reranker 模型
modelscope download --model BAAI/bge-reranker-v2-m3 --local_dir models/reranker/bge-reranker-v2-m3
```

### 方式三：Python 脚本

```python
from huggingface_hub import snapshot_download

# 下载全部预训练模型
snapshot_download("BAAI/bge-large-zh-v1.5", local_dir="models/embedding/bge-large-zh-v1.5")
snapshot_download("BAAI/bge-reranker-v2-m3", local_dir="models/reranker/bge-reranker-v2-m3")
```

---

## 3. 微调模型

`fine_tuned/` 下的模型为项目自行训练/微调的产物：

- **intent-v1/v2**：基于 `bert-base-chinese` 在政务语料上 fine-tune 的意图分类模型
- **ner**：命名实体识别模型，用于 Material Agent 的实体抽取（Phase 2）

微调脚本位于（待实现）：
```
scripts/
├── train_intent.py       # 意图分类微调
└── train_ner.py          # NER 微调
```

---

## 4. 环境变量

模型路径通过 `.env` 或环境变量配置，见 `backend/config.py`：

```bash
# .env
MODELS_DIR=models                              # 模型根目录（相对于项目根）
EMBEDDING_MODEL_PATH=models/embedding/bge-large-zh-v1.5
RERANKER_MODEL_PATH=models/reranker/bge-reranker-v2-m3
INTENT_MODEL_PATH=models/intent/bert-intent
```

默认值即可使用，无需修改（除非模型放在项目外）。

---

## 5. 注意事项

- **首次部署**：需要先下载模型再启动服务，否则 Embedding/Reranker/Intent 模块会使用 stub 模式
- **离线环境**：将模型文件拷贝到目标服务器对应路径即可，无需联网
- **GPU 服务器**：模型路径通过 `deploy/k8s/model.yaml` 挂载 PVC，与代码分离部署
- **版本管理**：微调模型命名带版本号（如 `intent-v1`、`intent-v2`），支持 A/B 测试和回滚
