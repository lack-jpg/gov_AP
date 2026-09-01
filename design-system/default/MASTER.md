# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** 政务多智能体协同与治理平台（gov_AP）
**Generated:** 2026-08-06 20:31:26 · **Last synced:** 2026-09-02（前端视觉重构）
**Category:** Government Enterprise SaaS / Analytics Dashboard

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `#1E40AF` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Primary Hover | `#2563EB` | `--color-primary-hover` |
| Secondary | `#3B82F6` | `--color-secondary` |
| Accent/CTA | `#0369A1` | `--color-accent` |
| Navy (heading/text) | `#0F172A` | `--color-foreground` |
| Background | `#F6F8FB` | `--color-background` |
| Background Grad | `#EFF6FF` | `--color-background-grad` |
| Card / Surface | `#FFFFFF` | `--color-card` |
| Muted Surface | `#EFF6FF` | `--color-muted` |
| Border | `#E2E8F0` | `--color-border` |
| Text Muted | `#64748B` | `--color-muted-foreground` |
| Destructive | `#DC2626` | `--color-destructive` |
| Ring | `#1E40AF` | `--color-ring` |

**Color Notes:** Professional navy + service blue, light government tone, WCAG AA contrast.

### Typography

- **Heading Font:** Plus Jakarta Sans（800/700）
- **Body Font:** Plus Jakarta Sans（400/500/600）
- **CJK Fallback:** PingFang SC · Microsoft YaHei · Noto Sans SC
- **Mood:** enterprise, saas, b2b, government, professional, legible
- **Google Fonts:** [Plus Jakarta Sans](https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
```

### Spacing Variables

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(15,23,42,0.04)` | Subtle lift |
| `--shadow-md` | `0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.04)` | Cards |
| `--shadow-brand` | `0 6px 16px rgba(30,64,175,0.30)` | Icon badges / logo |
| `--shadow-hover` | `0 2px 4px rgba(15,23,42,0.06), 0 12px 32px rgba(30,64,175,0.10)` | Card hover |

---

## Component Specs

> 实现文件：`frontend/ui.py`（Streamlit 共享组件库）。以下规格与实现同步。

### Page Header（Hero）

```css
.gp-header { display: flex; align-items: center; gap: 16px; }
.gp-header-badge {
  width: 54px; height: 54px; border-radius: 15px;
  background: linear-gradient(135deg, #1E40AF, #3B82F6);
  color: #fff; box-shadow: 0 6px 16px rgba(30,64,175,.30);
}
.gp-header-title { font-size: 28px; font-weight: 800; color: #0F172A; }
.gp-header-rule {
  height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, #1E40AF, rgba(30,64,175,.05));
}
```

### Metric Card

```css
.gp-metric {
  background: #fff; border: 1px solid #E2E8F0; border-radius: 14px;
  padding: 16px 18px; border-top: 3px solid transparent;
  box-shadow: var(--shadow-md);
  transition: transform 180ms ease, box-shadow 180ms ease;
}
.gp-metric:hover { transform: translateY(-2px); box-shadow: var(--shadow-hover); }
.gp-metric-value { font-size: 26px; font-weight: 800; color: #0F172A; font-variant-numeric: tabular-nums; }
```

### Card

```css
.gp-card {
  background: #fff; border: 1px solid #E2E8F0; border-radius: 14px;
  padding: 18px 20px; box-shadow: var(--shadow-md);
  transition: all 180ms ease;
}
.gp-card:hover {
  border-color: #C7D6F2; transform: translateY(-1px); box-shadow: var(--shadow-hover);
}
```

### Button

```css
.stButton > button { border-radius: 10px; font-weight: 600; transition: all 150ms ease; }
.stButton > button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(30,64,175,.18); }
.stButton > button[kind="primary"] { background: #1E40AF; border-color: #1E40AF; }
.stButton > button[kind="primary"]:hover:not(:disabled) { background: #2563EB; border-color: #2563EB; }
```

### Input / Textarea

```css
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
  border-radius: 10px; border: 1px solid #E2E8F0;
}
/* focus */
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: #1E40AF; box-shadow: 0 0 0 3px rgba(30,64,175,.15);
}
```

### Icon

- 全部使用内联 **SVG**（Lucide 风格，stroke=currentColor，24×24 viewBox）。
- 图标字典见 `frontend/ui.py` `_ICONS`：home / chat / target / cpu / book / clipboard / share / shield / shield-check / chart / activity / network / rocket / search / send / user / log-out / plus / history / clock / zap / trending-up / database / key / check-circle / alert / info / sparkles / building / wallet / file-text / file-check / arrow-down / git-branch / gauge / layers / government 等。

---

## Style Guidelines

**Style:** Light Mode · Accessible & Ethical

**Keywords:** Government, enterprise, professional, high contrast, accessible, keyboard navigation, screen-reader friendly, focus states, semantic, trustworthy

**Best For:** Government platforms, B2B SaaS, admin dashboards, public services, compliance

**Key Effects:** Clear focus rings (3px rgba(30,64,175,.5)), soft shadows, gradient blue accents, tabular numbers for metrics, reduced-motion support

### Page Pattern

**Pattern Name:** Trust & Authority

- **Conversion Strategy:** Security badges, credibility signals, transparent metrics, low-friction demo.
- **CTA Placement:** Primary action in page header + after metrics.
- **Section Order:** 1. Hero (product + status), 2. Key metrics, 3. How it works / architecture, 4. Capabilities, 5. Clear next-step.

---

## Anti-Patterns (Do NOT Use)

- ❌ **Emojis as icons** — 必须使用内联 SVG 图标（Lucide 风格）。仅 Streamlit 原生限制处可用 emoji（`st.Page` 导航 icon）或 Material 图标名（`:material/name:`）。
- ❌ **AI purple/pink gradients** — 政务场景禁止。
- ❌ **Playful / 儿童化设计** — 保持克制与信任感。
- ❌ **Missing cursor:pointer** — 所有可点击元素必须有 cursor:pointer。
- ❌ **Layout-shifting hovers** — 避免 scale 变换导致的布局抖动。
- ❌ **Low contrast text** — 保持 4.5:1 最小对比度。
- ❌ **Instant state changes** — 始终使用 150-300ms 过渡。
- ❌ **Invisible focus states** — 焦点状态必须可见（a11y）。

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Lucide-style stroke SVG)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile
