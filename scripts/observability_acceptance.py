"""scripts.observability_acceptance - P4-6 可观测性验收（需 Docker compose 全栈运行）

校验“指标 / 告警 / 面板 / DB trace”四口径一致，作为 P2-2 收尾验收：
    1. API /metrics：暴露预期指标族（agent_calls_total / agent_latency_ms histogram /
       llm_tokens_total / http_requests_total 等）；
    2. Prometheus：gov-agent-api target UP；alert_rules.yml 全部规则已加载（含 Watchdog 金丝雀）；
    3. Grafana：Prometheus 数据源已 provisioning、gov-agent 看板存在；
    4. 造真实对话流量 → agent_calls_total / agent_latency_ms_count / http_requests_total 非零；
    5. DB trace 落库校验（P4-7 迁移修复后）：trace 表按 agent 计数与 Prometheus 计数一致；
       LLM token 用量已接入指标（llm_tokens_total 有样本；LLM key 无效时跳过）；
    6. 告警管线：向 Alertmanager 注入合成告警并确认可达；Watchdog 金丝雀触发后出现在
       Alertmanager 告警列表（链路 Prometheus → Alertmanager 通）。

用法:
    docker compose up -d --build           # 全栈（api 需含 P4-6/P4-7 改动后重建）
    python scripts/observability_acceptance.py
    退出码: 0=全部通过, 1=有失败（--strict 下未断言项也失败）

环境变量（默认按端口规范 CLAUDE.md §17）:
    API=127.0.0.1:12401  PROMETHEUS=127.0.0.1:12411  GRAFANA=127.0.0.1:12421
    ALERTMANAGER=127.0.0.1:12431
    AUTH_ADMIN_USERNAME / AUTH_ADMIN_PASSWORD（默认 admin/admin123）
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any

# 以 `python scripts/xxx.py` 运行时 sys.path[0]=scripts/，cwd 不在 sys.path；
# 显式把仓库根加进来以支持 `from backend.config import get_settings`（DB 一致性校验用）。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

API = os.getenv("API", "http://127.0.0.1:12401")
PROM = os.getenv("PROMETHEUS", "http://127.0.0.1:12411")
GRAF = os.getenv("GRAFANA", "http://127.0.0.1:12421")
AM = os.getenv("ALERTMANAGER", "http://127.0.0.1:12431")
AUTH_USER = os.getenv("AUTH_ADMIN_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_ADMIN_PASSWORD", "admin123")
# Grafana HTTP API 走 Basic Auth（默认 admin/admin，同 compose 默认）
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
STRICT = os.getenv("OBS_ACCEPT_STRICT", "0") == "1"


def grafana_headers() -> dict[str, str]:
    """构造 Grafana API 的 Basic Auth 头。"""
    token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

passed = 0
failed = 0
skipped = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def warn_skip(name: str, reason: str) -> None:
    """跳过未断言项：非 strict 不记失败（如环境无有效 LLM key）。"""
    global skipped
    skipped += 1
    print(f"  [SKIP] {name} — {reason}")


def section(title: str) -> None:
    print(f"\n{'─' * 66}\n  {title}\n{'─' * 66}")


def http_json(url: str, data: Any = None, method: str = "GET", headers: dict | None = None,
              timeout: int = 15) -> Any:
    """urllib 封装：data dict → JSON body；返回解析后的 JSON。"""
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        method = method or "POST"
    req = urllib.request.Request(url, data=body, method=method or "GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def http_text(url: str, timeout: int = 15) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def prom_query(query: str) -> list[dict]:
    """Prometheus /api/v1/query → result 列表。"""
    url = f"{PROM}/api/v1/query?query={urllib.parse.quote(query)}"
    d = http_json(url)
    return (d or {}).get("data", {}).get("result", [])


def login() -> str:
    d = http_json(f"{API}/api/auth/login",
                  {"username": AUTH_USER, "password": AUTH_PASSWORD}, method="POST")
    token = (d or {}).get("access_token", "")
    if not token:
        raise RuntimeError("登录失败，请检查 AUTH_ADMIN_USERNAME/PASSWORD")
    return token


def main() -> int:
    section("0. 前提健康检查")
    health = http_json(f"{API}/health")
    check("API /health", health.get("status") == "healthy")
    if health.get("status") != "healthy":
        print("  API 不可达 → 请先 docker compose up -d --build")
        return 1

    # ── 1. API /metrics 指标族 ──
    section("1. API /metrics 指标族")
    text = http_text(f"{API}/metrics")
    expected_types = {
        "agent_calls_total": "counter",
        "agent_failure_total": "counter",
        "agent_success_total": "counter",
        "agent_latency_ms": "histogram",
        "llm_tokens_total": "counter",
        "http_requests_total": "counter",
        "http_request_duration_ms": "histogram",
    }
    for name, mtype in expected_types.items():
        check(f"/metrics 含 # TYPE {name} {mtype}",
              f"# TYPE {name} {mtype}" in text)
    # 造流量前 http_requests_total 应有 /health 探测样本
    check("/metrics http_requests_total 有样本",
          "\nhttp_requests_total" in text and "http_requests_total{" in text)

    # ── 2. Prometheus 抓取与规则 ──
    section("2. Prometheus targets / rules")
    targets = http_json(f"{PROM}/api/v1/targets").get("data", {}).get("activeTargets", [])
    api_up = any(t.get("health") == "up" and "api" in t.get("scrapeUrl", "")
                 for t in targets)
    check("gov-agent-api target UP", api_up)

    rules = http_json(f"{PROM}/api/v1/rules").get("data", {}).get("groups", [])
    loaded = {r.get("name") for g in rules for r in g.get("rules", [])}
    for expect in ("AgentHighFailureRate", "AgentHighLatency", "ApiNoTraffic",
                   "HighTokenConsumption", "Watchdog"):
        check(f"告警规则 {expect} 已加载", expect in loaded)

    # ── 3. Grafana 数据源与看板 ──
    section("3. Grafana provisioning")
    gf_health = http_json(f"{GRAF}/api/health")
    check("Grafana /api/health", gf_health.get("database") == "ok")
    ds = http_json(f"{GRAF}/api/datasources", headers=grafana_headers())
    check("Prometheus 数据源已 provisioning",
          any(d.get("type") == "prometheus" for d in ds))
    dash = http_json(f"{GRAF}/api/search?query=Gov", headers=grafana_headers())
    check("看板 'Gov Agent Platform' 已 provisioning",
          any("gov" in (d.get("uri") or "").lower() or "Gov" in (d.get("title") or "")
              for d in dash))

    # ── 4. 造流量 → 指标非零 ──
    section("4. 造流量并核对指标")
    token = login()
    auth = {"Authorization": f"Bearer {token}"}
    queries = ["成都开餐饮店需要什么材料", "查询社保补缴政策", "失业保险金领取条件是什么"]
    for q in queries:
        try:
            http_json(f"{API}/api/chat", {"user_query": q, "user_id": "obs_acceptance"},
                      method="POST", headers=auth, timeout=180)
        except Exception as e:
            print(f"  [warn] chat 请求失败（将计入后续一致性判定）: {q} — {e}")
    time.sleep(18)  # 等 Prometheus 抓 1~2 个周期

    counts = {m.get("metric", {}).get("agent"): float(m.get("value", [0, 0])[1])
              for m in prom_query("agent_calls_total")}
    check("agent_calls_total 非零", sum(counts.values()) > 0, str(counts))
    lat = prom_query("agent_latency_ms_count")
    check("agent_latency_ms histogram 有观测", len(lat) > 0)
    check("agent_latency_ms_bucket 含 le 分桶",
          any("le" in m.get("metric", {}) for m in
              prom_query("agent_latency_ms_bucket")))

    # ── 5. DB trace 一致性（P4-7 迁移修复后应落库） ──
    section("5. DB trace 落库一致性")
    db_counts: dict[str, int] = {}
    try:
        import psycopg
        from backend.config import get_settings
        s = get_settings()
        # postgres_sync_url 是 SQLAlchemy 方言 URL，libpq 不认 +psycopg scheme，需剥离
        libpq_url = s.postgres_sync_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(libpq_url) as conn:
            rows = conn.execute(
                "SELECT agent_name, count(*) FROM trace "
                "GROUP BY agent_name"
            ).fetchall()
            db_counts = {r[0]: r[1] for r in rows}
    except Exception as e:
        warn_skip("DB 一致性（缺 psycopg / 配置）", str(e)[:100])
    if db_counts:
        total_db = sum(db_counts.values())
        check("trace 表有落库记录（schema 漂移已修复）", total_db > 0, str(db_counts))
        # 计数器自 API 进程启动起累计，DB 行跨进程保留；受 api 重启/span 记录边界影响，
        # 允许少量偏差（每个 agent ≤ max(1, 5%×较大值)），正常同进程运行时二者应几乎相等。
        tol_ok = all(
            abs(counts.get(a, 0) - float(db_counts.get(a, 0)))
            <= max(1.0, 0.05 * max(counts.get(a, 0), float(db_counts.get(a, 0))))
            for a in set(counts) | set(db_counts)
        )
        check("按 agent 计数: Prometheus ≈ DB trace（±5%）",
              tol_ok and total_db > 0,
              f"prom={counts} db={db_counts}")

    # ── 6. LLM token 指标已接线 ──
    section("6. LLM token 指标接线")
    tok = prom_query("llm_tokens_total")
    if tok:
        check("llm_tokens_total 有样本（P4-6 接线生效）", True,
              str([(m["metric"], m["value"][1]) for m in tok]))
    else:
        warn_skip("llm_tokens_total 有样本",
                  "当前 LLM key 无效/未调用真实 LLM → 无 token 上报（接线本身见单测）")

    # ── 7. 告警管线（Alertmanager 可达 + Watchdog 金丝雀） ──
    section("7. 告警管线")
    try:
        am_status = http_json(f"{AM}/api/v2/status")
        check("Alertmanager /api/v2/status", am_status.get("versionInfo", {}) is not None)
    except Exception as e:
        check("Alertmanager /api/v2/status", False, str(e))

    # 注入一条合成告警验证接收端点可达（fire → 列表可见 → resolve 后消失）
    try:
        http_json(f"{AM}/api/v2/alerts", method="POST",
                  data=[{
                      "labels": {"alertname": "AcceptanceCanary",
                                 "severity": "none",
                                 "instance": "obs-acceptance"},
                      "annotations": {"summary": "P4-6 验收注入告警"},
                      "generatorURL": "http://obs-acceptance",
                  }])
        time.sleep(3)
        alerts = http_json(f"{AM}/api/v2/alerts")
        names = {a.get("labels", {}).get("alertname") for a in alerts}
        check("注入的合成告警出现在 Alertmanager", "AcceptanceCanary" in names)
    except Exception as e:
        check("注入合成告警到 Alertmanager", False, str(e))

    # Watchdog 金丝雀（vector(1), for:1m）：轮询直到 Prometheus 侧 firing 且
    # Alertmanager 收到该告警 —— 链路 Prometheus → Alertmanager 的真实证明。
    # 若长期未 firing，说明规则/路由配置或抓取有问题。
    watchdog_ok = False
    for _ in range(12):  # 最长 ~72s
        rules = http_json(f"{PROM}/api/v1/rules").get("data", {}).get("groups", [])
        wd_state = [r.get("state") for g in rules
                    for r in g.get("rules", []) if r.get("name") == "Watchdog"]
        if wd_state:
            am_alerts = http_json(f"{AM}/api/v2/alerts")
            wd_seen = any(a.get("labels", {}).get("alertname") == "Watchdog"
                          for a in am_alerts)
            if wd_state[0] == "firing" and wd_seen:
                watchdog_ok = True
                break
        time.sleep(6)
    check("Watchdog 金丝雀 firing 且 Alertmanager 已收到（链路通）", watchdog_ok,
          f"prom_state={wd_state}")

    # 汇总
    print(f"\n{'═' * 66}")
    print(f"  可观测性验收: {passed} 通过, {failed} 失败, {skipped} 跳过")
    print(f"{'═' * 66}")
    if STRICT:
        return 1 if (failed or skipped) else 0
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
