# FEISHU.md — 飞书对话机器人接入方案

> 政务多 Agent 平台（gov_AP）接入飞书开发文档
> 作者: le ｜ 日期: 2026-08-19 ｜ 状态: ⏳ 未实施（方案待确认）

---

## 1. 概述

### 1.1 目标

让用户在**飞书里直接和平台的政务多 Agent 对话**：用户发一条自然语言问题 → 平台走完整 Agent 工作流（意图识别 → 政策检索 → 材料审核 → 流程执行 → 安全审查）→ 把最终答案回发给用户，并支持多轮追问。

### 1.2 架构流程

```
用户在飞书聊天窗口发消息
   │
   ▼
飞书开放平台（触发 im.message.receive_v1 事件）
   │  HTTPS 回调（平台须 3 秒内返回 200，否则飞书重试）
   ▼
┌───────────────────────────────────────────────┐
│ 平台  /api/feishu/callback                     │
│  ① crypto.py   验证签名 + 解密事件内容          │
│  ② callback.py 立即返回 200（不能等 Agent）      │
│  ③ handler.py  后台任务编排                     │
└───────────────────────────────────────────────┘
   │ mapping.py（开发期固定 demo 身份）
   ▼
backend.api.dependencies.execute_agent(...)
   │ 复用现有业务层（不造 HTTP/JWT）
   ▼
client.py  tenant_access_token（缓存） + send_text
   │ POST /open-apis/im/v1/messages
   ▼
用户收到最终答案（含 trace_id 便于排查）
```

### 1.3 决策记录（2026-08-19 已确认）

| 决策点 | 选择 | 说明 |
|---|---|---|
| 接入形态 | **对话机器人（双向）** | 完整实现事件订阅 + 消息接收 + 消息回发 |
| 公网条件 | **暂无，先用内网穿透** | 阶段 0 用 cpolar / ngrok 映射本地 12401 |
| 身份映射 | **先跑通** | 开发期固定 `feishu_demo` 身份，`mapping.py` 预留正式化接口 |

---

## 2. 前置条件

- 本地平台能正常启动（`uvicorn backend.main:app`，端口 12401）
- 能访问 [飞书开放平台](https://open.feishu.cn/)，有企业管理员权限
- Python 依赖：`httpx` 已有（`requirements.txt` 第 59 行）；`cryptography` 需显式补声明（见 §5.5）

---

## 3. 阶段 0 — 公网可达性

> 飞书事件回调需要一个**公网可访问**的地址。尚未部署服务器，先用内网穿透解决联调。

1. 注册内网穿透服务（二选一，约 5 分钟）：
   - **cpolar**：`https://dashboard.cpolar.com` 注册 → 下载客户端 → `cpolar authtoken <你的token>`
   - **ngrok**：`https://ngrok.com` 注册 → `ngrok config add-authtoken <token>`
2. 把本地 API 端口 12401 映射到公网：

   ```powershell
   cpolar http 12401
   # 或
   ngrok http 12401
   ```

3. 拿到公网地址，形如 `https://a1b2c3d4.r2.cpolar.cn`，**记下备用**。
4. 验证：浏览器打开 `https://你的穿透域名/health`，应返回 `{"status":"healthy",...}`。

> ⚠️ 免费档域名每次重启穿透进程会变；联调期间保持穿透进程不关，正式化再上云服务器 + 域名。

---

## 4. 阶段 1 — 飞书开放平台侧配置（无代码）

1. **创建企业自建应用**：`open.feishu.cn` → 开发者后台 → 创建企业自建应用 → 名称"政务智能助手"。
2. **开启机器人能力**：应用详情 → 添加应用能力 → **机器人**。
3. **配置权限**（权限管理 → 开通）：
   - `im:message` —— 读取消息
   - `im:message:send_as_bot` —— 以机器人身份发消息
   - `im:message.p2p_msg` —— 接收单聊消息事件
   - （可选，后续做 OCR）`im:resource` —— 读取消息中的图片资源
4. **配置事件订阅**（事件与回调）：
   - 订阅事件：`im.message.receive_v1`
   - **请求地址**：`https://<你的穿透域名>/api/feishu/callback`
   - 加密策略：选择"使用 **Encrypt Key** 加密事件内容"，生成并保存 `encrypt_key` 和 `verification_token`
   - ⚠️ 点"保存"时飞书会立即发一次 **URL 验证请求**（challenge）——因此 **阶段 2 的平台代码必须先上线**，顺序不能反。
5. **发布应用**：版本管理与发布 → 创建版本 → 提交发布 → 企业管理员审批。开发期可先加"测试企业与成员"做联调。

**产出 4 个凭证**（写入 `.env`，勿提交 Git）：

| 变量 | 值示例 |
|---|---|
| `FEISHU_APP_ID` | `cli_xxxxxxxxxxxx` |
| `FEISHU_APP_SECRET` | `xxxxxxxxxxxx` |
| `FEISHU_VERIFICATION_TOKEN` | `xxxxxxxxxxxx` |
| `FEISHU_ENCRYPT_KEY` | `xxxxxxxxxxxx` |

---

## 5. 阶段 2 — 平台侧代码

### 5.1 配置项 — `backend/config.py`

在 `Settings` 类中新增飞书段（沿用现有 `alias` 风格，环境变量自动读取）：

```python
# ── 飞书集成 ──
feishu_enabled: bool = Field(default=False, alias="FEISHU_ENABLED")
feishu_app_id: str = Field(default="", alias="FEISHU_APP_ID")
feishu_app_secret: str = Field(default="", alias="FEISHU_APP_SECRET")
feishu_verification_token: str = Field(default="", alias="FEISHU_VERIFICATION_TOKEN")
feishu_encrypt_key: str = Field(default="", alias="FEISHU_ENCRYPT_KEY")
feishu_callback_path: str = Field(default="/api/feishu/callback", alias="FEISHU_CALLBACK_PATH")
```

`.env` 追加：

```
# ── 飞书集成 ──
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
FEISHU_ENCRYPT_KEY=xxx
```

> `.env` 已在 `.gitignore`，凭证不会提交。

### 5.2 新增模块 `integration/feishu/`

```
integration/feishu/
├── __init__.py
├── crypto.py        # URL challenge + X-Lark-Signature 验签 + AES 解密
├── client.py        # tenant_access_token 缓存 + send_text 发消息
├── callback.py      # FastAPI router：/api/feishu/callback 入口
├── handler.py       # 消息编排：execute_agent → 回发结果
└── mapping.py       # 身份映射（先 demo，预留接口）
```

#### `crypto.py` — 两道校验

- **URL 验证**：收到 `{"challenge": "...", "token": "..."}` → 比对 `token == verification_token` → 原样返回 `{"challenge": "..."}`。
- **事件验签**：请求头 `X-Lark-Signature`，按飞书规则用 `encrypt_key + timestamp + nonce` 拼串 SHA256 比对；若配置了 Encrypt Key，事件 body 为 AES-CBC 密文，先解密再解析。
- 验签失败一律 401 拒绝，不进入业务处理。

#### `client.py` — 飞书 API 封装

- `get_tenant_access_token()`：`POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`，body `{"app_id", "app_secret"}` → 返回 `tenant_access_token`。**2 小时过期，须做缓存 + 提前刷新**。
- `send_text(open_id, text)`：`POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id`，body：
  ```json
  {"receive_id": "<open_id>", "msg_type": "text", "content": "{\"text\":\"...\"}"}
  ```
  content 必须是 **JSON 字符串**（双层转义）。

#### `handler.py` — 核心编排（关键：异步回包）

流程（收到消息事件后）：

```text
① 校验/解密通过后 → 立即返回 200 给飞书（3 秒限制，不能等 Agent）
② 启动后台任务：
   1. mapping.resolve_user(open_id)        → user_id（开发期固定 "feishu_demo"）
   2. mapping.get_conversation_id(open_id) → 持久化映射，实现多轮上下文
   3. execute_agent(user_query, user_id, trace_id, settings,
                    conversation_id, ...)  → 直接复用业务层
   4. 先发提示消息："已收到，正在办理…"
   5. Agent 完成 → send_text 回发 final_answer（附 trace_id）
   6. 异常 → 回发友好错误文案
③ 幂等去重：按 message_id 记录已处理事件，飞书重试推送不重复回答
```

#### `mapping.py` — 身份映射

- **开发期（先跑通）**：
  - `user_id` 固定为 `feishu_demo`，角色 `user`、租户 `default`。
  - `conversation_id` 以 `open_id` 为 key 做映射（内存 dict + SQLite 持久化），实现每个飞书用户独立的多轮会话。
- **正式化预留接口**：`resolve_user(open_id) -> str` 已定义，后续改为查"飞书 open_id ↔ 平台账号"绑定表，以平台账号身份执行（对接现有 JWT/RBAC）。

### 5.3 路由挂载 — `backend/main.py`

在 `create_app()` 注册路由处追加：

```python
if settings.feishu_enabled:
    from integration.feishu.callback import router as feishu_router
    app.include_router(feishu_router)   # 挂在 /api/feishu 前缀
```

### 5.4 认证白名单 — `backend/middleware/auth.py`

飞书回调请求**不带平台 JWT**，必须把 `/api/feishu/*` 加入 AuthMiddleware 的公开白名单（与 `/health`、`/api/auth/login` 同级）。安全性由飞书验签（`crypto.py`）保证，不依赖 JWT。

### 5.5 依赖 — `requirements/requirements.txt`

- `httpx` ✅ 已存在，`client.py` 直接用。
- `cryptography` ⚠️ 目前是 `python-jose[cryptography]` 的传递依赖，用于飞书 AES 解密。建议显式补一行：

  ```
  cryptography>=42.0,<47.0
  ```

---

## 6. 阶段 3 — 验证

| # | 步骤 | 预期 |
|---|---|---|
| 1 | 平台启动，`curl -X POST https://<域名>/api/feishu/callback -d '{"challenge":"abc","token":"<verification_token>"}'` | 返回 `{"challenge":"abc"}` |
| 2 | 飞书后台保存事件订阅 | URL 验证通过（说明穿透 + crypto 都通） |
| 3 | 飞书里给机器人发："我想在成都开川菜馆需要什么手续" | 收到"正在办理…" → 稍后收到完整答案 |
| 4 | 再追问一句 | 多轮上下文生效（conversation_id 映射正确） |
| 5 | 查看平台日志 + `/api/dashboard/overview` | trace_id 链路完整、请求计数正常 |

---

## 7. 安全注意事项

- 飞书回调端点**只用验签/解密做安全**，不依赖 JWT；验签失败一律 401。
- `encrypt_key`、`app_secret` 只在 `.env`，`.env` 已 gitignore，禁止硬编码到代码。
- 事件幂等：按 `message_id` 去重，防飞书重试导致重复回答（对齐现有 A2A 幂等思路）。
- 后续接图片 OCR 时：复用 `ocr_*` 配置（超时、大小限制、降级策略），禁止静默生成模拟 OCR 数据。
- 开发期固定 `feishu_demo` 身份仅限联调，正式化前必须切身份映射 + 关掉 dev-login 类开关。

---

## 8. 改动文件汇总

| 文件 | 动作 |
|---|---|
| `backend/config.py` | 新增 6 个飞书配置字段 |
| `.env` | 新增飞书凭证 |
| `integration/feishu/`（5 个文件） | 新增模块 |
| `backend/main.py` | 条件挂载 feishu router |
| `backend/middleware/auth.py` | 白名单加 `/api/feishu/*` |
| `requirements/requirements.txt` | 显式补 `cryptography` |

---

## 9. 后续可扩展

- **群推送（单向通知）**：群自定义机器人 Webhook，签名放 `timestamp` + `sign` 字段，把 Agent 结果/告警推到群里（约 3 步，不走事件订阅）。
- **消息卡片渐进更新**：用 `interactive` 卡片 + 更新接口，把"规划中/检索中/完成"实时刷新，替代两条消息的体验。
- **图片 / 文件材料上传**：`im:resource` 权限 + `download_image()` → 接入现有 OCR pipeline。
- **正式身份映射**：`mapping.py` 切换为绑定表，飞书员工 ↔ 政务系统账号。

---

## 10. 待办 Checklist

- [ ] 阶段 0：注册 cpolar/ngrok 并映射 12401，验证 `/health`
- [ ] 阶段 1：飞书创建应用、开机器人、配权限、配事件订阅
- [ ] 阶段 2：`config.py` 加字段
- [ ] 阶段 2：新增 `integration/feishu/` 模块
- [ ] 阶段 2：`main.py` 挂载 + `auth.py` 白名单
- [ ] 阶段 2：补 `cryptography` 依赖
- [ ] 阶段 3：URL 验证通过 → 机器人对话 → 多轮验证
