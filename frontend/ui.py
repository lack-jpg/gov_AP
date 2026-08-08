"""
frontend.ui - Streamlit 共享 UI 组件库（浅色专业政务风）

设计系统：design-system/default/MASTER.md
配色：
    Primary 政务蓝 #1E40AF · Secondary #3B82F6 · 服务绿 #16A34A
    Warning 琥珀 #D97706 · Destructive #DC2626
    Background #F6F8FB · Surface #FFFFFF · Muted surface #EFF6FF
    Border #D6E2F0 · Text #1F2A44 · Text muted #64748B

用法：
    from frontend import ui
    ui.inject_theme_css()              # 全局 CSS（入口脚本调用一次即可）
    ui.page_header("🏛️", "标题", "副标题", tags=["v3.0"])
    ui.section_header("📊", "小节")
    ui.metric_card("总请求数", 1234, accent="blue")
    ui.status_badge("low")             # 返回 HTML 字符串，可嵌入 markdown
    ui.evidence_card("来源", 0.92, "摘要")

说明：
    - 侧边导航 st.Page 的 icon 参数必须用 emoji（Streamlit 原生限制），
      页面内装饰 emoji 收敛到 header 徽章 + 状态符号。
    - 所有自定义组件基于 Streamlit 原生 API + 内联 CSS，无新增依赖。
"""
from __future__ import annotations

from html import escape as _esc
from typing import Iterable

import streamlit as st

# ============================================================
# 设计 token
# ============================================================

C_BLUE = "#1E40AF"
C_SECONDARY = "#3B82F6"
C_GREEN = "#16A34A"
C_AMBER = "#D97706"
C_RED = "#DC2626"
C_BG = "#F6F8FB"
C_SURFACE = "#FFFFFF"
C_MUTED = "#EFF6FF"
C_BORDER = "#D6E2F0"
C_TEXT = "#1F2A44"
C_TEXT_MUTED = "#64748B"

_ACCENTS: dict[str, str] = {
    "blue": C_BLUE,
    "green": C_GREEN,
    "amber": C_AMBER,
    "red": C_RED,
    "gray": C_TEXT_MUTED,
}

_PILL_TONES: dict[str, tuple[str, str, str]] = {
    "blue": ("#EFF6FF", C_BLUE, "#BFDBFE"),
    "green": ("#F0FDF4", "#15803D", "#BBF7D0"),
    "amber": ("#FFFBEB", "#B45309", "#FDE68A"),
    "red": ("#FEF2F2", "#B91C1C", "#FECACA"),
    "gray": ("#F1F5F9", "#475569", "#E2E8F0"),
}


# ============================================================
# 全局 CSS
# ============================================================

def inject_theme_css() -> None:
    """注入全局主题 CSS（在入口脚本 st.set_page_config 后调用一次）。

    CSS 仅覆盖两类目标：
      1. 本项目自定义 class（gp-*），由下方组件生成；
      2. Streamlit 1.56 稳定 data-testid（stMetric / stVerticalBlockBorderWrapper 等）。
    即使选择器失效也不影响功能（只丢失样式）。
    """
    st.markdown(
        """
<style>
/* ── 全局字体与正文 ── */
/* 注意：不要用 [class*="st-"] 覆盖 font-family —— 会误伤 Streamlit 自带的
   Material Symbols 图标字体（ligature 图标），导致图标渲染成文字
   （如 sidebar 折叠箭头显示为 keyboard_double_arrow_left）。
   只设置基础元素，图标 span 有自身 font-family 规则，不会继承。 */
html, body, .stApp {
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC",
                 -apple-system, "Segoe UI", sans-serif;
}

/* 防御性兜底：显式保留 Streamlit 图标字体（Material Symbols ligature） */
.material-symbols-rounded,
.material-symbols-outlined,
.material-symbols-sharp {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined",
                 "Material Symbols Sharp", "Material Icons" !important;
}
.stMarkdown p { line-height: 1.6; }
h1, h2, h3 { color: #1E40AF; letter-spacing: 0.3px; }
h1 { font-weight: 700; }
code, pre, [data-testid="stCode"] {
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
}

/* ── 指标卡 ── */
.gp-metric {
    background: #FFFFFF; border: 1px solid #D6E2F0; border-radius: 10px;
    padding: 14px 16px; box-shadow: 0 1px 2px rgba(30, 64, 175, 0.05);
    margin-bottom: 12px;
}
.gp-metric-label { font-size: 13px; color: #64748B; font-weight: 500; }
.gp-metric-value {
    font-size: 26px; font-weight: 700; color: #1F2A44; margin-top: 4px; line-height: 1.2;
}

/* ── 通用卡片 ── */
.gp-card {
    background: #FFFFFF; border: 1px solid #D6E2F0; border-radius: 12px;
    padding: 18px 20px; box-shadow: 0 1px 3px rgba(30, 64, 175, 0.06);
    margin-bottom: 14px;
}

/* ── 页头 ── */
.gp-header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 6px; }
.gp-header-badge {
    width: 52px; height: 52px; border-radius: 14px; background: #EFF6FF;
    border: 1px solid #BFDBFE; display: flex; align-items: center; justify-content: center;
    font-size: 26px; flex-shrink: 0;
}
.gp-header-title { font-size: 26px; font-weight: 700; color: #1E40AF; line-height: 1.3; }
.gp-header-sub { color: #64748B; font-size: 14px; margin-top: 4px; }
.gp-header-tags { margin-top: 8px; }
.gp-header-rule { border-bottom: 2px solid #EFF6FF; margin: 12px 0 20px; }

/* ── 徽章 / 胶囊 ── */
.gp-badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; line-height: 1.6;
}

/* ── 证据卡 ── */
.gp-evidence-head {
    display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px;
}
.gp-evidence-source { font-weight: 600; color: #1E40AF; }
.gp-evidence-excerpt { color: #334155; font-size: 14px; line-height: 1.55; }

/* ── 能力卡 ── */
.gp-capability { display: flex; gap: 14px; align-items: flex-start; }
.gp-cap-icon { font-size: 26px; line-height: 1; }
.gp-cap-name { font-weight: 700; color: #1F2A44; margin-bottom: 4px; }
.gp-cap-desc { color: #475569; font-size: 14px; line-height: 1.55; margin-bottom: 6px; }
.gp-cap-page { color: #64748B; font-size: 13px; }

/* ── 架构图 ── */
.gp-arch { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 0; }
.gp-arch-node {
    text-align: center; border-radius: 10px; padding: 10px 22px; font-weight: 600;
    border: 1px solid #D6E2F0; background: #FFFFFF; min-width: 220px;
    box-shadow: 0 1px 2px rgba(30, 64, 175, 0.05);
}
.gp-arch-gateway { border-color: #3B82F6; color: #1E40AF; }
.gp-arch-super { border-color: #1E40AF; background: #EFF6FF; color: #1E40AF; }
.gp-arch-agent { background: #F8FAFF; }
.gp-arch-workflow { border-color: #16A34A; color: #0F766E; }
.gp-arch-governance { border-color: #D97706; color: #92400E; }
.gp-arch-end { background: #16A34A; color: #FFFFFF; border-color: #16A34A; }
.gp-arch-arrow { color: #93A5C4; font-size: 14px; line-height: 1; padding: 2px 0; }
.gp-arch-sub { font-weight: 400; font-size: 12px; color: #64748B; display: block; margin-top: 2px; }
.gp-arch-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.gp-arch-row .gp-arch-node { min-width: 150px; }

/* ── 空态 ── */
.gp-empty { text-align: center; padding: 32px 16px; color: #64748B; }

/* ── 按钮 ── */
.stButton > button { border-radius: 10px; }
.stButton > button[kind="primary"] { border-radius: 10px; font-weight: 600; }

/* ── 边框容器 (st.container(border=True)) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #D6E2F0 !important; border-radius: 12px !important; background: #FFFFFF;
}

/* ── 输入框 / 代码块圆角 ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea { border-radius: 10px; }
[data-testid="stCode"] { border-radius: 10px; }

/* ── caption 灰色 ── */
[data-testid="stCaptionContainer"] p { color: #64748B; }

/* ── 可访问性：可见焦点 ── */
:focus-visible { outline: 3px solid rgba(30, 64, 175, 0.5) !important; outline-offset: 2px; }

/* ── 隐藏 Streamlit 原生英文 UI（Deploy / Made with Streamlit / 汉堡菜单） ── */
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stToolbar"] { visibility: hidden; }
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* ── 动画降级 ── */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# 基础徽章
# ============================================================

def pill(text: object, tone: str = "blue") -> str:
    """返回小胶囊标签 HTML 字符串。tone: blue/green/amber/red/gray"""
    bg, fg, bd = _PILL_TONES.get(tone, _PILL_TONES["gray"])
    return (
        f'<span class="gp-badge" style="background:{bg}; color:{fg};'
        f' border:1px solid {bd};">{_esc(str(text))}</span>'
    )


def status_badge(level: object, label: str | None = None) -> str:
    """按风险/严重度返回语义徽章 HTML。level: low/medium/high/critical 等"""
    mapping = {
        "low": ("green", "低风险"),
        "info": ("green", "正常"),
        "ok": ("green", "通过"),
        "medium": ("amber", "中风险"),
        "warning": ("amber", "警告"),
        "high": ("red", "高风险"),
        "error": ("red", "错误"),
        "critical": ("red", "严重"),
        "failed": ("red", "未通过"),
    }
    key = str(level).lower()
    tone, default_label = mapping.get(key, ("gray", str(level)))
    return pill(label or default_label, tone)


# ============================================================
# 组合组件
# ============================================================

def page_header(emoji: str, title: str, subtitle: str | None = None, tags: Iterable[str] | None = None) -> None:
    """统一页头：圆角徽章 + 标题 + 副标题 + 标签胶囊"""
    tags_html = " ".join(pill(t) for t in (tags or []))
    sub_html = f'<div class="gp-header-sub">{_esc(subtitle)}</div>' if subtitle else ""
    tags_block = f'<div class="gp-header-tags">{tags_html}</div>' if tags_html else ""
    html = (
        '<div class="gp-header">'
        f'<div class="gp-header-badge">{_esc(emoji)}</div>'
        '<div class="gp-header-main">'
        f'<div class="gp-header-title">{_esc(title)}</div>'
        f"{sub_html}"
        f"{tags_block}"
        "</div>"
        "</div>"
        '<div class="gp-header-rule"></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def section_header(emoji: str, title: str, hint: str | None = None) -> None:
    """统一小节标题"""
    st.markdown(f"### {emoji} {title}")
    if hint:
        st.caption(hint)


def metric_card(label: object, value: object, accent: str = "blue") -> None:
    """语义色指标卡。accent: blue/green/amber/red/gray"""
    top = _ACCENTS.get(accent, C_BLUE)
    html = (
        f'<div class="gp-metric" style="border-top:3px solid {top};">'
        f'<div class="gp-metric-label">{_esc(str(label))}</div>'
        f'<div class="gp-metric-value">{_esc(str(value))}</div>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def evidence_card(source: object, score: object, excerpt: str) -> None:
    """证据卡：来源 + 相关度徽章 + 摘要"""
    score_val = float(score) if isinstance(score, (int, float)) else score
    score_txt = f"{score_val:.0%}" if isinstance(score_val, float) and 0 <= score_val <= 1 else str(score_val)
    html = (
        '<div class="gp-card gp-evidence">'
        '<div class="gp-evidence-head">'
        f'<span class="gp-evidence-source">{_esc(str(source))}</span>'
        f'{pill(f"{score_txt} 相关度", "blue")}'
        "</div>"
        f'<div class="gp-evidence-excerpt">{_esc(str(excerpt))}</div>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def capability_card(emoji: str, name: str, tag: str, desc: str, page: str) -> None:
    """首页能力卡：图标 + 名称 + 标签 + 描述 + 跳转提示"""
    html = (
        '<div class="gp-card gp-capability">'
        f'<div class="gp-cap-icon">{_esc(emoji)}</div>'
        '<div class="gp-cap-body">'
        f'<div class="gp-cap-name">{_esc(name)} {pill(tag, "blue")}</div>'
        f'<div class="gp-cap-desc">{_esc(desc)}</div>'
        f'<div class="gp-cap-page">→ 前往侧边栏「{_esc(page)}」体验</div>'
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def status_card(ok: bool, title: str, detail: str = "") -> None:
    """状态卡：左侧语义色边条 + 状态点。ok=True 绿色 / False 琥珀"""
    c = C_GREEN if ok else C_AMBER
    detail_html = (
        f'<div style="color:#64748B; font-size:13px; margin-top:4px;">{_esc(detail)}</div>'
        if detail
        else ""
    )
    html = (
        f'<div class="gp-card" style="border-left:4px solid {c};">'
        f'<span style="color:{c}; margin-right:8px;">●</span>'
        f"<strong>{_esc(title)}</strong>"
        f"{detail_html}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def empty_state(icon: str, title: str, hint: str | None = None) -> None:
    """居中空态提示"""
    hint_html = (
        f'<div style="font-size:13px; margin-top:4px;">{_esc(hint)}</div>' if hint else ""
    )
    html = (
        '<div class="gp-empty">'
        f'<div style="font-size:32px;">{_esc(icon)}</div>'
        f'<div style="font-weight:600; color:#475569; margin-top:8px;">{_esc(title)}</div>'
        f"{hint_html}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def architecture_diagram() -> None:
    """架构流程图（HTML/CSS 盒子 + 箭头），替换首页 ASCII 图"""
    html = """
<div class="gp-arch">
    <div class="gp-arch-node gp-arch-gateway">FastAPI Gateway</div>
    <div class="gp-arch-arrow">▼</div>
    <div class="gp-arch-node gp-arch-super">Supervisor Agent<span class="gp-arch-sub">LangGraph StateGraph · 任务拆解 / Agent 路由</span></div>
    <div class="gp-arch-arrow">▼</div>
    <div class="gp-arch-row">
        <div class="gp-arch-node gp-arch-agent">Intent Agent<span class="gp-arch-sub">意图识别</span></div>
        <div class="gp-arch-node gp-arch-agent">Policy Agent<span class="gp-arch-sub">RAG 检索</span></div>
        <div class="gp-arch-node gp-arch-agent">Material Agent<span class="gp-arch-sub">材料审核</span></div>
    </div>
    <div class="gp-arch-arrow">▼</div>
    <div class="gp-arch-node gp-arch-workflow">Workflow Agent<span class="gp-arch-sub">→ A2A 跨域协同</span></div>
    <div class="gp-arch-arrow">▼</div>
    <div class="gp-arch-node gp-arch-governance">Governance Agent<span class="gp-arch-sub">安全护栏 · PII · 风险检测</span></div>
    <div class="gp-arch-arrow">▼</div>
    <div class="gp-arch-node gp-arch-end">回答用户</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
