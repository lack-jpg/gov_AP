"""
frontend.ui - Streamlit 共享 UI 组件库（政务企业级 · Light Navy）

设计系统：design-system/default/MASTER.md（2026-09-02 重设计）
方向：Trust & Authority（政府信任感）+ Accessible & Ethical（可访问优先）
    Primary 政务蓝 #1E40AF · Hover #2563EB · CTA 深蓝青 #0369A1
    Navy 主文字 #0F172A · 背景 #F6F8FB→#EFF6FF 微渐变 · 卡片 #FFFFFF
    Border #E2E8F0 · Muted #64748B
字体：Plus Jakarta Sans（企业级）+ 中文回退（PingFang SC / Microsoft YaHei / Noto Sans SC）
图标：内联 SVG（Lucide 风格 stroke 图标），禁止 emoji 作图标。

用法：
    from frontend import ui
    ui.inject_theme_css()              # 全局 CSS（入口脚本调用一次）
    ui.page_header("home", "标题", "副标题", tags=["v3.0"])
    ui.section_header("activity", "小节")
    ui.metric_card("总请求数", 1234, accent="blue", icon="activity")
    ui.status_badge("low")             # 返回 HTML 字符串，可嵌入 markdown
    ui.evidence_card("来源", 0.92, "摘要")

图标参数约定：
    所有接收 `icon`/`emoji` 的组件都接受三类值：
      1. 内置图标名（见 _ICONS，如 "home"/"chat"/"shield"）→ 渲染 SVG
      2. 完整 SVG HTML（含 "<svg"）→ 原样嵌入
      3. 其它文本（含 emoji 字符）→ 兼容降级为文字/emoji

说明：
    - 侧边导航 st.Page 的 icon 参数必须用 emoji 或 ":material/name:"（Streamlit 原生限制），
      页面内装饰性图标统一收敛到 SVG。
    - 所有自定义组件基于 Streamlit 原生 API + 内联 CSS，无新增依赖。
"""
from __future__ import annotations

from html import escape as _esc
from typing import Iterable

import streamlit as st

# ============================================================
# 设计 token
# ============================================================

C_NAVY = "#0F172A"          # 主文字 / 标题
C_BLUE = "#1E40AF"          # 政务蓝 Primary
C_BLUE_HOVER = "#2563EB"
C_SECONDARY = "#3B82F6"
C_ACCENT = "#0369A1"        # CTA 深蓝青
C_GREEN = "#16A34A"
C_GREEN_DEEP = "#15803D"
C_AMBER = "#D97706"
C_AMBER_DEEP = "#B45309"
C_RED = "#DC2626"
C_RED_DEEP = "#B91C1C"
C_BG = "#F6F8FB"
C_BG_GRAD = "#EFF6FF"
C_SURFACE = "#FFFFFF"
C_MUTED = "#EFF6FF"
C_BORDER = "#E2E8F0"
C_TEXT = "#0F172A"
C_TEXT_MUTED = "#64748B"
C_TEXT_SUB = "#475569"

_ACCENTS: dict[str, str] = {
    "blue": C_BLUE,
    "green": C_GREEN_DEEP,
    "amber": C_AMBER_DEEP,
    "red": C_RED_DEEP,
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
# SVG 图标库（Lucide 风格，24×24，stroke=currentColor）
# ============================================================

_ICONS: dict[str, str] = {
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<path d="M9 1v2"/><path d="M15 1v2"/><path d="M9 21v2"/><path d="M15 21v2"/>'
           '<path d="M1 9h2"/><path d="M1 15h2"/><path d="M21 9h2"/><path d="M21 15h2"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "file-check": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                  '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
    "clipboard": '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
                 '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                 '<path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>'
             '<line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1'
              'c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1'
                    'c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
                    '<path d="m9 12 2 2 4-4"/>',
    "chart": '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/>',
    "activity": '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18'
                'a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    "network": '<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/>'
               '<rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>'
               '<path d="M12 12V8"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>'
              '<path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>'
              '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/>'
               '<line x1="21" x2="9" y1="12" y2="12"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'
               '<path d="M12 7v5l4 2"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "zap": '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7'
           'a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/>'
                '<path d="M3 12A9 3 0 0 0 21 12"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "sparkles": '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21'
                'l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    "building": '<rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/>'
                '<path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/>'
                '<path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/>'
                '<path d="M8 14h.01"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2'
              'a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                 '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "git-branch": '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/>'
                  '<circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "layers": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0'
              'l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
              '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "government": '<path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/>'
                  '<path d="M9 9h.01"/><path d="M9 12h.01"/><path d="M9 15h.01"/><path d="M15 9h.01"/>'
                  '<path d="M15 12h.01"/><path d="M15 15h.01"/>',
}


def _svg(name: object, size: int = 20, color: str | None = None) -> str:
    """按图标名/emoji/SVG HTML 解析出可嵌入 HTML 的图标。

    - 命中 _ICONS 的 SVG 名 → 渲染 stroke 图标
    - 含 "<svg" 的完整 SVG → 原样返回
    - 其它 → 降级为文字/emoji（保持兼容，不抛错）
    """
    if not isinstance(name, str):
        name = str(name)
    body = _ICONS.get(name.strip())
    if body is not None:
        style = f"color:{color};" if color else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" style="{style}" aria-hidden="true">{body}</svg>'
        )
    if "<svg" in name:
        return name
    return f'<span style="font-size:{size}px;line-height:1;">{_esc(name)}</span>'


def icon(name: object, size: int = 20, color: str | None = None) -> str:
    """公开图标帮助：返回可嵌入 st.markdown(unsafe_allow_html=True) 的内联 SVG HTML。"""
    return _svg(name, size=size, color=color)


# ============================================================
# 全局 CSS
# ============================================================

def inject_theme_css() -> None:
    """注入全局主题 CSS（在入口脚本 st.set_page_config 后调用一次）。

    CSS 仅覆盖两类目标：
      1. 本项目自定义 class（gp-*），由下方组件生成；
      2. Streamlit 1.56 稳定 data-testid（stMetric / stChatMessage / stSidebar 等）。
    即使选择器失效也不影响功能（只丢失样式）。
    """
    st.markdown(
        f"""
<style>
/* ── 字体：Plus Jakarta Sans（企业级）+ 中文回退 ── */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html, body, .stApp {{
    font-family: "Plus Jakarta Sans", "PingFang SC", "Microsoft YaHei", "Noto Sans SC",
                 -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
}}

/* 防御性兜底：保留 Streamlit 图标字体（Material Symbols ligature） */
.material-symbols-rounded,
.material-symbols-outlined,
.material-symbols-sharp {{
    font-family: "Material Symbols Rounded", "Material Symbols Outlined",
                 "Material Symbols Sharp", "Material Icons" !important;
}}

/* ── 全局背景：浅政务蓝渐变 ── */
.stApp {{
    background: linear-gradient(180deg, {C_BG} 0%, {C_BG_GRAD} 100%);
}}
.stMarkdown p {{ line-height: 1.65; }}
h1, h2, h3 {{ color: {C_NAVY}; letter-spacing: 0.2px; }}
h1 {{ font-weight: 800; }}

code, pre, [data-testid="stCode"] {{
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
}}

/* ── 指标卡 ── */
.gp-metric {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 14px;
    padding: 16px 18px; box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(30,64,175,0.06);
    margin-bottom: 12px; border-top: 3px solid transparent;
    transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}}
.gp-metric:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(30,64,175,0.12), 0 8px 24px rgba(30,64,175,0.08);
}}
.gp-metric-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.gp-metric-ic {{ display: inline-flex; }}
.gp-metric-label {{ font-size: 13px; color: {C_TEXT_MUTED}; font-weight: 600; }}
.gp-metric-value {{
    font-size: 26px; font-weight: 800; color: {C_NAVY}; line-height: 1.2;
    font-variant-numeric: tabular-nums;
}}

/* ── 通用卡片 ── */
.gp-card {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 14px;
    padding: 18px 20px; box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.04);
    margin-bottom: 14px;
    transition: box-shadow 180ms ease, transform 180ms ease, border-color 180ms ease;
}}
.gp-card:hover {{
    border-color: #C7D6F2;
    box-shadow: 0 2px 4px rgba(15,23,42,0.06), 0 12px 32px rgba(30,64,175,0.10);
    transform: translateY(-1px);
}}

/* ── 页头 hero ── */
.gp-header {{ display: flex; align-items: center; gap: 16px; margin: 2px 0 8px; }}
.gp-header-badge {{
    width: 54px; height: 54px; border-radius: 15px; flex-shrink: 0;
    background: linear-gradient(135deg, {C_BLUE}, {C_SECONDARY});
    color: #fff; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 16px rgba(30,64,175,0.30);
}}
.gp-header-badge svg {{ width: 27px; height: 27px; }}
.gp-header-title {{
    font-size: 28px; font-weight: 800; color: {C_NAVY};
    line-height: 1.25; letter-spacing: -0.3px;
}}
.gp-header-sub {{ color: {C_TEXT_MUTED}; font-size: 14px; margin-top: 4px; }}
.gp-header-tags {{ margin-top: 8px; }}
.gp-header-rule {{
    height: 2px; border-radius: 2px; margin: 10px 0 24px;
    background: linear-gradient(90deg, {C_BLUE}, rgba(30,64,175,0.05));
}}

/* ── 小节标题 ── */
.gp-section-head {{ display: flex; align-items: center; gap: 8px; margin: 20px 0 4px; }}
.gp-section-ic {{ color: {C_BLUE}; display: inline-flex; }}
.gp-section-title {{ font-size: 18px; font-weight: 700; color: {C_NAVY}; letter-spacing: 0.1px; }}

/* ── 徽章 / 胶囊 ── */
.gp-badge {{
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; line-height: 1.6;
}}

/* ── 证据卡 ── */
.gp-evidence-head {{
    display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px;
}}
.gp-evidence-source {{ font-weight: 700; color: {C_BLUE}; }}
.gp-evidence-excerpt {{ color: {C_TEXT_SUB}; font-size: 14px; line-height: 1.55; }}

/* ── 能力卡 ── */
.gp-capability {{ display: flex; gap: 14px; align-items: flex-start; }}
.gp-cap-ic {{
    width: 46px; height: 46px; border-radius: 13px; flex-shrink: 0;
    background: {C_MUTED}; color: {C_BLUE}; border: 1px solid #BFDBFE;
    display: flex; align-items: center; justify-content: center;
}}
.gp-cap-ic svg {{ width: 23px; height: 23px; }}
.gp-cap-name {{ font-weight: 700; color: {C_NAVY}; margin-bottom: 4px; font-size: 15px; }}
.gp-cap-desc {{ color: {C_TEXT_SUB}; font-size: 14px; line-height: 1.55; margin-bottom: 6px; }}
.gp-cap-page {{ color: {C_TEXT_MUTED}; font-size: 13px; }}

/* ── 架构图 ── */
.gp-arch {{ display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 0; }}
.gp-arch-node {{
    text-align: center; border-radius: 12px; padding: 10px 22px; font-weight: 600;
    border: 1px solid {C_BORDER}; background: {C_SURFACE}; min-width: 220px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.05), 0 4px 14px rgba(30,64,175,0.06);
    font-size: 14px; color: {C_NAVY};
}}
.gp-arch-gateway {{ border-color: {C_SECONDARY}; color: {C_BLUE}; }}
.gp-arch-super {{ border-color: {C_BLUE}; background: {C_MUTED}; color: {C_BLUE}; }}
.gp-arch-agent {{ background: #F8FAFF; }}
.gp-arch-workflow {{ border-color: {C_GREEN}; color: #0F766E; }}
.gp-arch-governance {{ border-color: {C_AMBER}; color: {C_AMBER_DEEP}; }}
.gp-arch-end {{ background: linear-gradient(135deg, {C_GREEN}, #059669); color: #fff; border-color: transparent; }}
.gp-arch-arrow {{ color: #94A8C8; display: inline-flex; padding: 2px 0; }}
.gp-arch-arrow svg {{ width: 16px; height: 16px; }}
.gp-arch-sub {{ font-weight: 400; font-size: 12px; color: {C_TEXT_MUTED}; display: block; margin-top: 2px; }}
.gp-arch-row {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }}
.gp-arch-row .gp-arch-node {{ min-width: 150px; }}

/* ── 空态 ── */
.gp-empty {{ text-align: center; padding: 32px 16px; color: {C_TEXT_MUTED}; }}
.gp-empty svg {{ opacity: 0.45; }}

/* ── 按钮 ── */
.stButton > button {{
    border-radius: 10px; font-weight: 600;
    transition: transform 150ms ease, box-shadow 150ms ease, background 150ms ease;
}}
.stButton > button:hover:not(:disabled) {{
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(30,64,175,0.18);
}}
.stButton > button[kind="primary"] {{ background: {C_BLUE}; border-color: {C_BLUE}; }}
.stButton > button[kind="primary"]:hover:not(:disabled) {{ background: {C_BLUE_HOVER}; border-color: {C_BLUE_HOVER}; }}

/* ── 边框容器 / 输入框 / 代码块 ── */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: {C_BORDER} !important; border-radius: 14px !important;
    background: {C_SURFACE};
    box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(30,64,175,0.05);
}}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {{
    border-radius: 10px; border: 1px solid {C_BORDER};
}}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {{
    border-color: {C_BLUE}; box-shadow: 0 0 0 3px rgba(30,64,175,0.15);
}}
[data-testid="stCode"] {{ border-radius: 10px; }}

/* ── 侧边栏 ── */
[data-testid="stSidebar"] {{
    background: {C_SURFACE}; border-right: 1px solid {C_BORDER};
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ line-height: 1.5; }}
/* 导航菜单高亮 */
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: {C_MUTED}; border-radius: 8px;
}}

/* ── 品牌区（侧边栏顶部） ── */
.gp-brand {{
    display: flex; align-items: center; gap: 10px;
    padding: 4px 2px 12px; margin-bottom: 8px;
    border-bottom: 1px solid {C_BORDER};
}}
.gp-brand-logo {{
    width: 38px; height: 38px; border-radius: 11px; flex-shrink: 0;
    background: linear-gradient(135deg, {C_BLUE}, {C_SECONDARY});
    color: #fff; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 10px rgba(30,64,175,0.30);
}}
.gp-brand-logo svg {{ width: 20px; height: 20px; }}
.gp-brand-name {{ font-weight: 800; font-size: 15px; color: {C_NAVY}; line-height: 1.2; }}
.gp-brand-sub {{ font-size: 11px; color: {C_TEXT_MUTED}; }}

/* ── 侧边栏用户卡片 ── */
.gp-user-card {{
    background: {C_MUTED}; border: 1px solid #BFDBFE; border-radius: 12px;
    padding: 12px 14px; margin-top: 8px;
}}
.gp-user-row {{ display: flex; align-items: center; gap: 10px; }}
.gp-user-avatar {{
    width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
    background: {C_BLUE}; color: #fff; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 14px;
}}
.gp-user-name {{ font-weight: 700; font-size: 14px; color: {C_NAVY}; }}
.gp-user-role {{ font-size: 12px; color: {C_TEXT_MUTED}; }}

/* ── chat 消息美化 ── */
[data-testid="stChatMessage"] {{
    border-radius: 14px; padding: 4px 2px;
}}

/* ── Alert（info/success/warning/error）圆角 ── */
[data-testid="stAlert"] {{ border-radius: 12px; }}

/* ── pills ── */
[data-testid="stPills"] button {{ border-radius: 999px; }}

/* ── caption 灰色 ── */
[data-testid="stCaptionContainer"] p {{ color: {C_TEXT_MUTED}; }}

/* ── 可访问性：可见焦点 ── */
:focus-visible {{ outline: 3px solid rgba(30, 64, 175, 0.5) !important; outline-offset: 2px; }}

/* ── 隐藏 Streamlit 原生英文 UI ── */
[data-testid="stAppDeployButton"] {{ display: none !important; }}
[data-testid="stToolbar"] {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
#MainMenu {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ── 动画降级 ── */
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }}
}}
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

def page_header(icon: object, title: str, subtitle: str | None = None, tags: Iterable[str] | None = None) -> None:
    """统一页头：渐变图标徽章 + 标题 + 副标题 + 标签胶囊。icon 见模块 docstring。"""
    tags_html = " ".join(pill(t) for t in (tags or []))
    sub_html = f'<div class="gp-header-sub">{_esc(subtitle)}</div>' if subtitle else ""
    tags_block = f'<div class="gp-header-tags">{tags_html}</div>' if tags_html else ""
    html = (
        '<div class="gp-header">'
        f'<div class="gp-header-badge">{_svg(icon, size=27)}</div>'
        '<div class="gp-header-main">'
        f'<div class="gp-header-title">{_esc(title)}</div>'
        f"{sub_html}"
        f"{tags_block}"
        "</div>"
        "</div>"
        '<div class="gp-header-rule"></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def section_header(icon: object, title: str, hint: str | None = None) -> None:
    """统一小节标题（SVG 图标 + 标题），可选 hint 说明。"""
    html = (
        '<div class="gp-section-head">'
        f'<span class="gp-section-ic">{_svg(icon, size=18)}</span>'
        f'<span class="gp-section-title">{_esc(title)}</span>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)
    if hint:
        st.caption(hint)


def metric_card(label: object, value: object, accent: str = "blue", icon: object | None = None) -> None:
    """语义色指标卡。accent: blue/green/amber/red/gray；icon 可选（见模块 docstring）。"""
    top = _ACCENTS.get(accent, C_BLUE)
    ic_html = (
        f'<span class="gp-metric-ic">{_svg(icon, size=16, color=top)}</span>'
        if icon is not None
        else ""
    )
    html = (
        f'<div class="gp-metric" style="border-top-color:{top};">'
        '<div class="gp-metric-top">'
        f"{ic_html}"
        f'<span class="gp-metric-label">{_esc(str(label))}</span>'
        "</div>"
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


def capability_card(icon: object, name: str, tag: str, desc: str, page: str) -> None:
    """首页能力卡：SVG 图标 + 名称 + 标签 + 描述 + 跳转提示。"""
    html = (
        '<div class="gp-card gp-capability">'
        f'<div class="gp-cap-ic">{_svg(icon, size=23)}</div>'
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
    c = C_GREEN_DEEP if ok else C_AMBER_DEEP
    ic = _svg("check-circle" if ok else "alert", size=16, color=c)
    detail_html = (
        f'<div style="color:{C_TEXT_MUTED}; font-size:13px; margin-top:4px;">{_esc(detail)}</div>'
        if detail
        else ""
    )
    html = (
        f'<div class="gp-card" style="border-left:4px solid {c};">'
        f'<span style="display:inline-flex; vertical-align:-3px; margin-right:8px;">{ic}</span>'
        f"<strong>{_esc(title)}</strong>"
        f"{detail_html}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def empty_state(icon: object, title: str, hint: str | None = None) -> None:
    """居中空态提示"""
    hint_html = (
        f'<div style="font-size:13px; margin-top:4px;">{_esc(hint)}</div>' if hint else ""
    )
    html = (
        '<div class="gp-empty">'
        f'<div style="display:flex; justify-content:center;">{_svg(icon, size=40)}</div>'
        f'<div style="font-weight:600; color:{C_TEXT_SUB}; margin-top:8px;">{_esc(title)}</div>'
        f"{hint_html}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def architecture_diagram() -> None:
    """架构流程图（HTML/CSS 盒子 + SVG 箭头）"""
    arrow = _svg("arrow-down", size=16)
    arrow_html = f'<div class="gp-arch-arrow">{arrow}</div>'
    html = f"""
<div class="gp-arch">
    <div class="gp-arch-node gp-arch-gateway">FastAPI Gateway</div>
    {arrow_html}
    <div class="gp-arch-node gp-arch-super">Supervisor Agent<span class="gp-arch-sub">LangGraph StateGraph · 任务拆解 / Agent 路由</span></div>
    {arrow_html}
    <div class="gp-arch-row">
        <div class="gp-arch-node gp-arch-agent">Intent Agent<span class="gp-arch-sub">意图识别</span></div>
        <div class="gp-arch-node gp-arch-agent">Policy Agent<span class="gp-arch-sub">RAG 检索</span></div>
        <div class="gp-arch-node gp-arch-agent">Material Agent<span class="gp-arch-sub">材料审核</span></div>
    </div>
    {arrow_html}
    <div class="gp-arch-node gp-arch-workflow">Workflow Agent<span class="gp-arch-sub">→ A2A 跨域协同</span></div>
    {arrow_html}
    <div class="gp-arch-node gp-arch-governance">Governance Agent<span class="gp-arch-sub">安全护栏 · PII · 风险检测</span></div>
    {arrow_html}
    <div class="gp-arch-node gp-arch-end">回答用户</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


# ============================================================
# 侧边栏专属组件
# ============================================================

def sidebar_brand(name: str = "政务多智能体平台", sub: str = "Government Agent Platform") -> None:
    """侧边栏顶部品牌区（logo + 名称 + 副标题）。"""
    html = (
        '<div class="gp-brand">'
        f'<div class="gp-brand-logo">{_svg("government", size=20)}</div>'
        '<div class="gp-brand-text">'
        f'<div class="gp-brand-name">{_esc(name)}</div>'
        f'<div class="gp-brand-sub">{_esc(sub)}</div>'
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def sidebar_user_card(username: str, role: str) -> None:
    """侧边栏用户卡片（头像 + 名称 + 角色）。"""
    avatar = (username[:1] or "?").upper()
    html = (
        '<div class="gp-user-card">'
        '<div class="gp-user-row">'
        f'<div class="gp-user-avatar">{_esc(avatar)}</div>'
        '<div class="gp-user-text">'
        f'<div class="gp-user-name">{_esc(username)}</div>'
        f'<div class="gp-user-role">{_esc(role) if role else "已登录"}</div>'
        "</div>"
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)
