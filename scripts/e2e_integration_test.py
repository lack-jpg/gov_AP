"""
scripts.e2e_integration_test - 端到端集成测试（需 Docker compose 全栈运行）

PLAN #10「端到端集成测试（docker compose 起服务后全链路）」

覆盖:
    1. /health                     后端健康
    2. POST /api/conversations     创建会话
    3. POST /api/chat              单轮对话（回答 + 意图）
    4. POST /api/chat              多轮对话（conversation_id 关联）
    5. GET  /api/conversations     会话列表
    6. GET  /api/conversations/{id}/messages  历史消息持久化
    7. GET  /api/dashboard/overview   看板（agent_stats/total_tokens）
    8. POST /api/chat/stream       SSE 流式（node 事件 + final 回答）
    9. GET  /api/evaluation/report/v1  评测报告

用法:
    docker compose up -d                      # 先起全栈
    python scripts/e2e_integration_test.py     # 跑全链路
    退出码: 0=全部通过, 1=有失败
"""
from __future__ import annotations

import json
import sys

import httpx

API = "http://127.0.0.1:8002"
HEADERS = {
    "X-User-Id": "demo_user",
    "X-User-Role": "admin",
    "Content-Type": "application/json",
}

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


async def main() -> int:
    async with httpx.AsyncClient(timeout=180) as client:
        # 1. 健康检查
        section("1. 后端健康")
        try:
            r = await client.get(f"{API}/health", timeout=10)
            check("GET /health 200", r.status_code == 200)
        except Exception as e:
            check("GET /health 200", False, str(e))
            return 1  # 后端不可达 → 直接失败

        # 2. 创建会话
        section("2. 创建会话")
        r = await client.post(f"{API}/api/conversations", headers=HEADERS)
        conv = r.json()
        cid = conv.get("conversation_id", "")
        check("POST /api/conversations 200", r.status_code == 200)
        check("返回 conversation_id", cid.startswith("conv_"), cid)

        # 3. 单轮对话
        section("3. 单轮对话")
        r = await client.post(
            f"{API}/api/chat",
            json={"user_query": "我想开一家川菜馆需要什么手续", "user_id": "demo_user"},
            headers=HEADERS,
        )
        d = r.json()
        check("POST /api/chat 200", r.status_code == 200)
        check("intent 识别", d.get("intent") in ("restaurant_license", "business_license"), d.get("intent"))
        check("有回答", len(d.get("answer", "")) > 20)

        # 4. 多轮对话（同一 conversation_id 两轮）
        section("4. 多轮对话")
        r1 = await client.post(
            f"{API}/api/chat",
            json={"user_query": "我想开一家川菜馆需要什么手续", "user_id": "demo_user", "conversation_id": cid},
            headers=HEADERS,
        )
        r2 = await client.post(
            f"{API}/api/chat",
            json={"user_query": "那需要哪些材料？", "user_id": "demo_user", "conversation_id": cid},
            headers=HEADERS,
        )
        check("第一轮 200", r1.status_code == 200)
        check("第二轮 200", r2.status_code == 200)
        check("第二轮 conversation_id 回显", r2.json().get("conversation_id") == cid)

        # 5. 会话列表
        section("5. 会话列表")
        r = await client.get(f"{API}/api/conversations", headers=HEADERS)
        items = r.json().get("items", [])
        check("GET /api/conversations 200", r.status_code == 200)
        check("列表含刚建的会话", any(c.get("conversation_id") == cid for c in items))

        # 6. 历史消息持久化
        section("6. 历史消息")
        r = await client.get(f"{API}/api/conversations/{cid}/messages", headers=HEADERS)
        msgs = r.json().get("messages", [])
        check("GET messages 200", r.status_code == 200)
        check("≥4 条消息（2轮×2）", len(msgs) >= 4, f"got {len(msgs)}")

        # 7. 看板
        section("7. 看板")
        r = await client.get(f"{API}/api/dashboard/overview", headers=HEADERS)
        ov = r.json()
        check("GET overview 200", r.status_code == 200)
        check("含 agent_stats", "agent_stats" in ov)
        check("含 total_tokens", "total_tokens" in ov)
        check("有请求数据", ov.get("total_requests", 0) > 0)

        # 8. SSE 流式
        section("8. SSE 流式")
        events: list[dict] = []
        async with client.stream(
            "POST", f"{API}/api/chat/stream",
            json={"user_query": "社保卡怎么办理", "user_id": "demo_user"},
            headers=HEADERS,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            events.append(json.loads(data))
                        except json.JSONDecodeError:
                            pass
        nodes = [e.get("node") for e in events if e.get("event") == "node"]
        final = [e for e in events if e.get("event") == "final"]
        check("SSE 200", resp.status_code == 200)
        check("有 node 事件", len(nodes) >= 3, str(nodes))
        check("有 final 事件", len(final) == 1)
        if final:
            check("final 有回答", len(final[0].get("answer", "")) > 20)

        # 9. 评测报告
        section("9. 评测报告")
        r = await client.get(f"{API}/api/evaluation/report/v1", headers=HEADERS)
        rep = r.json()
        check("GET report 200", r.status_code == 200)
        check("含 task_success_rate", "task_success_rate" in rep)

    print(f"\n{'═' * 60}\n  端到端集成测试: {passed} 通过, {failed} 失败\n{'═' * 60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(__import__("asyncio").run(main()))
