# Web Console UI Spec（固定，不要跑偏）

本规格描述 phase 5 的 Web 控制台必须长什么样、用什么、怎么交互。  
**通用模板已预写于 `templates/code/web/index.html`（A 型完整实现）。执行 agent 直接复制该文件，替换 `{{ PLATFORM }}`/`{{ LOGO_LETTER }}`，B 型替换添加面板（§14），删除 `[OPTIONAL]` 块即可。本规格是权威来源；模板与规格冲突时以规格为准，修模板而非改规格。**  
所有"可以这么写也可以那么写"的位置都已固定下来。除非用户明确要求，**不要**临时引入新依赖、新组件库、新色板。

---

## 0. 硬约束（不可破坏）

1. **界面语言必须为中文**：`<html lang="zh-CN">`；所有可见文案（标题、按钮、表头、placeholder、toast、confirm、空态、徽章、快捷键帮助）使用**简体中文**。禁止英文 UI（API 路径 `/api/...` 除外）。状态枚举显示中文：排队 / 进行中 / 等待申请 / 重试 / 已完成 / 失败 / 已暂停。
2. **零运行时外链依赖**：不允许 `<script src="https://...">` / `<link href="https://...">`。所有 CSS、JS、字体、图标全部内联在一个 HTML 文件里。理由：PyInstaller 单文件 + 离线场景必须能直接用。
3. **单文件**：整套控制台只有一个 HTML（含 `<style>` + `<script>`）。FastAPI 用 Jinja `TemplateResponse` 直接返回。
4. **原生 vanilla JS**：不引入 React / Vue / Alpine / jQuery / lit / htmx 等任何前端框架，不引入任何 UI 库（element-plus / antd / bootstrap / tailwind 等都不允许）。
5. **图标用 inline SVG**：单色线性图标，`stroke-width 1.6`，`viewBox="0 0 16 16"`，`fill="none" stroke="currentColor"`。不准用 emoji。图标与文字之间间距 `6px`。
6. **总代码量预算**：HTML + CSS + JS 合计 ≤ 1600 行。在此范围内优先保证视觉质量；不要用注释水行数。
7. **可访问性**：所有可点击元素必须有可见 `:focus-visible`（`outline: 2px solid var(--c-primary); outline-offset: 2px`）；模态/抽屉必须能 ESC 关闭；色彩对比度 ≥ 4.5:1（WCAG AA）。

---

## 1. 技术栈（固定）

| 项 | 选定值 | 备注 |
|---|---|---|
| 模板引擎 | Jinja2（FastAPI 自带） | 仅用占位符替换 `{{PLATFORM}}` / `{{LOGO_LETTER}}` |
| 样式 | 内联 `<style>`，CSS 变量驱动 | 见 §3 design tokens |
| 脚本 | 内联 `<script>`，IIFE，`"use strict"` | 不污染全局，只在 `window.ui` 暴露 toast/confirm/drawer |
| 图标 | inline SVG | 单色 currentColor，stroke-linecap round，stroke-linejoin round |
| 字体 | 系统字体栈（见 §3） | 不下载外部字体 |
| 通信 | `fetch` + JSON | 统一封装在 `api()` 里 |
| 数据 | `/api/*` REST，5s 轮询 | 见 §8 |

---

## 2. 页面骨架（顶到底）

```
┌─ <header class="app-header">  sticky, 60px, backdrop-blur(12px) + 底部 1px border
│   [Logo方块(36px圆角8px渐变背景)] · [站点名 bold] · [调度状态徽章] · [更新时间 + spinner]
│   ── flex spacer ──
│   [并发 input] · [暂停|恢复 btn] · [模板 btn] · [导出 btn] · [主题切换 icon btn]
│
├─ <main class="container">  max-width 1320px, padding 24px, display flex flex-col gap 20px
│   ① <section class="stats-grid">     7 张 stat 卡，带图标 + hover 动效
│   ② <section class="panel" id="addPanel">  折叠式添加面板（默认展开）
│   └ ③ <section class="panel">        账号列表（toolbar + 表格 / 移动端卡片）
│
├─ <div id="toastStack">    fixed right:20 bottom:20，纵向 stack，gap 10px
├─ <div id="modalMount">    全局模态/确认弹窗
└─ <div id="drawerMount">   右侧抽屉
```

---

## 3. Design Tokens（CSS 变量，固定）

写入 `:root`；暗色覆盖写入 `[data-theme="dark"]` 和 `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }`。

### 浅色（默认）

```css
/* 背景层次 */
--c-bg:           #f0f2f7;   /* 最外层页面底色 */
--c-surface:      #ffffff;   /* 卡片/表格/面板 */
--c-surface-2:    #f4f6fb;   /* 输入框、segmented 凹槽、hover 行 */
--c-surface-3:    #eaecf4;   /* 嵌套区域、skeleton */

/* 描边 */
--c-border:       #e2e5ef;
--c-border-strong:#c8cedf;

/* 文字 */
--c-text:         #1a2033;
--c-text-soft:    #55617c;
--c-text-muted:   #8891a6;

/* 主色蓝 */
--c-primary:      #3659f0;
--c-primary-hover:#2546e0;
--c-primary-soft: #eaedff;
--c-primary-dim:  rgba(54,89,240,.12);

/* 成功绿 */
--c-success:      #15a348;
--c-success-soft: #d9f7e6;

/* 警告橙 */
--c-warning:      #d97706;
--c-warning-soft: #fef3c7;

/* 危险红 */
--c-danger:       #dc2626;
--c-danger-soft:  #fee2e2;

/* 信息青 */
--c-info:         #0891b2;
--c-info-soft:    #ddf4fb;

/* 中性 */
--c-neutral:      #6b7280;
--c-neutral-soft: #f1f2f5;

/* Logo 渐变（方块背景） */
--c-logo-grad: linear-gradient(135deg, #3659f0 0%, #7c3aed 100%);

/* 圆角 */
--r-xs:   4px;
--r-sm:   6px;
--r:      10px;
--r-md:   12px;
--r-lg:   16px;
--r-pill: 999px;

/* 阴影（精确值） */
--shadow-xs: 0 1px 2px rgba(0,0,0,.06);
--shadow-sm: 0 1px 4px rgba(0,0,0,.07), 0 2px 8px rgba(0,0,0,.04);
--shadow:    0 2px 8px rgba(0,0,0,.08), 0 4px 20px rgba(0,0,0,.05);
--shadow-lg: 0 8px 24px rgba(0,0,0,.10), 0 16px 48px rgba(0,0,0,.06);
--shadow-primary: 0 4px 14px rgba(54,89,240,.28);

/* 动效 */
--dur-fast: 110ms;
--dur:      170ms;
--dur-slow: 260ms;
--ease:     cubic-bezier(.2,.8,.2,1);
--ease-out: cubic-bezier(0,.7,.3,1);

/* 字体 */
--font: -apple-system, BlinkMacSystemFont, "Segoe UI",
        "PingFang SC", "Microsoft YaHei", "Helvetica Neue",
        Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono",
             "Cascadia Code", Consolas, "Liberation Mono", Menlo, monospace;

/* 布局 */
--header-h:  60px;
--container: 1320px;
```

### 暗色覆盖（仅列差异）

```css
--c-bg:           #0d0f16;
--c-surface:      #161921;
--c-surface-2:    #1c1f2c;
--c-surface-3:    #21263a;
--c-border:       #252b3d;
--c-border-strong:#333a52;
--c-text:         #e8eaf2;
--c-text-soft:    #a0a9be;
--c-text-muted:   #6a7290;
--c-primary:      #6f8fff;
--c-primary-hover:#849aff;
--c-primary-soft: #1a2150;
--c-primary-dim:  rgba(111,143,255,.15);
--c-success-soft: #0e2a1a;
--c-warning-soft: #2e1f05;
--c-danger-soft:  #2e0d0d;
--c-info-soft:    #052433;
--c-neutral-soft: #1e222e;
--c-logo-grad: linear-gradient(135deg, #5578ff 0%, #9d5cf7 100%);
--shadow-sm: 0 1px 4px rgba(0,0,0,.3), 0 2px 8px rgba(0,0,0,.2);
--shadow:    0 2px 8px rgba(0,0,0,.35), 0 4px 20px rgba(0,0,0,.22);
--shadow-lg: 0 8px 24px rgba(0,0,0,.45), 0 16px 48px rgba(0,0,0,.28);
--shadow-primary: 0 4px 14px rgba(111,143,255,.30);
```

主题状态在 `<html data-theme="light|dark">` 上（无属性 = 跟随系统）；存 `localStorage["theme"]`；切换顺序 `system → light → dark → system`。

---

## 4. 全局排版与基线

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font); font-size: 14px; line-height: 1.55;
       color: var(--c-text); background: var(--c-bg);
       -webkit-font-smoothing: antialiased; }
h2 { font-size: 15px; font-weight: 600; }
h3 { font-size: 13px; font-weight: 600; letter-spacing: .3px; }
small { font-size: 12px; color: var(--c-text-muted); }
code { font-family: var(--font-mono); font-size: 12px;
       background: var(--c-surface-2); border-radius: var(--r-xs);
       padding: 1px 4px; }
```

---

## 5. App Header

```
高度 60px；position sticky top 0；z-index 100
背景：rgba(var(--c-surface-rgb), .88) + backdrop-filter blur(12px) saturate(180%)
底部：border-bottom 1px solid var(--c-border)
```

**Logo 方块**：`width/height 36px`，`border-radius 9px`，背景 `var(--c-logo-grad)`，白色居中 `{{LOGO_LETTER}}`（font-size 16px，font-weight 700）。

**调度状态徽章**：见 §6.2 Pill，`data-tone="running|paused"`。

**并发 input**：`<input type="number" min=1 max=50>`，宽 56px，前置文案「并发」（13px muted），两者用 `display:flex align-items:center gap:6px` 包在一个 `.ctrl-group` 里，group 右侧有 1px border-right 分隔线。

**图标按钮**（主题切换）：32px 圆形，`var(--c-surface-2)` 背景，hover 时 `var(--c-border-strong)` 背景。主题图标：日/夜/系统三状切换，SVG 路径固定。

所有 header 按钮之间 `gap: 8px`。

---

## 6. 组件清单（固定，必须实现）

### 6.1 Button `.btn`

- **变体**：
  - `.btn-primary`：背景 `var(--c-primary)`，白色文字，hover 时 `var(--c-primary-hover)`，active 时 `translateY(1px)`，`:not(:disabled)` box-shadow `var(--shadow-primary)` on hover
  - `.btn-outline`：`1px border var(--c-border-strong)`，文字 `var(--c-text-soft)`，hover 时背景 `var(--c-surface-2)`、border 变 primary
  - `.btn-ghost`：无边框无背景，hover 时 `var(--c-surface-2)` 背景
  - `.btn-danger`：背景 `var(--c-danger)`，白色文字
- **尺寸**：默认 `padding: 7px 14px / font-size: 13.5px / font-weight: 500`；`.btn-sm` `5px 10px / 12.5px`；`.btn-icon` `8px`（正方形）
- **圆角**：`var(--r-sm)`
- **Busy 态**：`[aria-busy="true"]` 时禁止点击，按钮内替换文字为 spinner + 文案，`cursor: progress`
- **图标前置**：`<svg class="icon" width="14" height="14">`，与文字间距 `5px`

### 6.2 Pill `.pill`

```
display inline-flex align-items center gap 5px
padding 3px 9px; border-radius var(--r-pill)
font-size 12px; font-weight 500; white-space nowrap
左侧 6×6 圆点 .dot（border-radius 999px）
```

| `data-tone` | 文案 | 背景 | 文字 | 圆点 |
|---|---|---|---|---|
| `queued` | 排队 | `var(--c-neutral-soft)` | `var(--c-neutral)` | `#9ca3af` |
| `running` | 进行中 | `var(--c-primary-soft)` | `var(--c-primary)` | `var(--c-primary)` — 圆点加 pulse 动画 |
| `waiting_apply` | 等待申请 | `var(--c-warning-soft)` | `var(--c-warning)` | `var(--c-warning)` |
| `retrying` | 重试 | `var(--c-warning-soft)` | `var(--c-warning)` | `var(--c-warning)` |
| `completed` | 已完成 | `var(--c-success-soft)` | `var(--c-success)` | `var(--c-success)` |
| `failed` | 失败 | `var(--c-danger-soft)` | `var(--c-danger)` | `var(--c-danger)` |
| `paused` | 已暂停 | `var(--c-neutral-soft)` | `var(--c-text-muted)` | `var(--c-text-muted)` |

`running` 圆点 pulse：`@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(1.4)} } animation: pulse 1.8s ease infinite`

`waiting_apply` 仅在 `docs/API_REQUIREMENTS.md` 确认站点存在申请学分流程时出现；站点无该流程时不要在筛选、统计或状态转换中展示该状态。

### 6.3 Stat Tile `.stat-tile`

```
background var(--c-surface)
border 1px solid var(--c-border)
border-radius var(--r-md)
padding 18px 20px
box-shadow var(--shadow-sm)
cursor pointer（活跃 Worker 除外：pointer-events none）
transition box-shadow var(--dur) var(--ease),
           border-color var(--dur) var(--ease),
           transform var(--dur) var(--ease)

:hover  →  box-shadow var(--shadow), translateY(-2px), border-color var(--c-border-strong)
[data-active="true"]  →  border-color var(--c-primary), box-shadow 0 0 0 3px var(--c-primary-dim)
```

**内部布局（纵向）**：

```
┌─ 顶行：flex space-between align-start
│   左：.tile-label（12px, font-weight 500, letter-spacing .4px, var(--c-text-muted)）
│   右：.tile-icon（18×18 SVG，var(--c-text-muted)）
└─ 数字行（margin-top 10px）
    .tile-value（font-size 28px，font-weight 700，letter-spacing -.5px，
                 font-variant-numeric tabular-nums，var(--c-text)）
    可选 .tile-sub（12px，var(--c-text-muted)，如 "+2 今日"）
```

**7 张图标对应**（写 inline SVG，16×16，stroke currentColor）：

| 瓦片 | 图标语义 |
|---|---|
| 总数 | 人物 / 用户组 |
| 排队 | 时钟 / 等待 |
| 进行中 | 播放圆圈 |
| 等待申请 | 文件发送 |
| 已完成 | 勾选圆圈 |
| 失败 | 叉圆圈 |
| 活跃 Worker | 闪电 / CPU |

**数字动效**：首次渲染及数值变化时用 `countUp`（100ms，`requestAnimationFrame`，整数）。

### 6.4 Panel `.panel`（替换原 `.card`）

```
background var(--c-surface)
border 1px solid var(--c-border)
border-radius var(--r-lg)
box-shadow var(--shadow-sm)
overflow hidden
```

**Panel 头 `.panel-header`**（可折叠）：

```
padding 16px 20px
display flex align-items center gap 10px
border-bottom 1px solid var(--c-border)（展开时显示）
cursor pointer（折叠时）
```

- 左侧标题行：`h2`（15px，600）+ 小 badge 显示当前行数
- 右侧：折叠箭头 SVG（展开时 rotate 180deg，transition 170ms）
- `[aria-expanded="false"]` 时 panel body `display none`

**Panel 体 `.panel-body`**：`padding 20px`

### 6.5 表单设计（添加账号）

```
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 14px;
}
```

**字段组 `.field`**：

```html
<div class="field">
  <label class="field-label" for="…">姓名 <span class="req">*</span></label>
  <input class="input" type="text" id="…" placeholder="真实姓名">
</div>
```

```css
.field-label {
  display: block; margin-bottom: 5px;
  font-size: 12.5px; font-weight: 500;
  color: var(--c-text-soft); letter-spacing: .2px;
}
.req { color: var(--c-danger); }
.input {
  width: 100%; padding: 8px 11px;
  border: 1.5px solid var(--c-border);
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  font-size: 13.5px; color: var(--c-text);
  transition: border-color var(--dur-fast) var(--ease),
              box-shadow var(--dur-fast) var(--ease);
  outline: none;
}
.input:focus {
  border-color: var(--c-primary);
  background: var(--c-surface);
  box-shadow: 0 0 0 3px var(--c-primary-dim);
}
.input::placeholder { color: var(--c-text-muted); }
```

**Excel 上传区 `.upload-zone`**：虚线 border `2px dashed var(--c-border-strong)`，圆角 `var(--r-md)`，`padding 20px`，居中；拖拽悬停时 border 变 primary，背景 `var(--c-primary-soft)`，有 `dragover / dragleave` 事件。上传文件须符合 **`excel-spec.md`**：Sheet 名与表头字段名**全部中文**（姓名、账号、密码…），禁止英文列名。

**表单字段标签**（与 Excel 导入列对齐，全部中文）：

- **Site profile A（默认）**：姓名、账号、密码、学科1、学分1、学科2、学分2、卡号、卡号密码、备注。
- **Site profile B（公需年度型）**：见 §14；**不展示**学科/学分/卡号业务字段（除非 gap 明确混合站点）。

字段显示必须跟 `docs/API_REQUIREMENTS.md` 中的 **`site_profile`** 对齐：A 型下学科/学分仅在需要按学科选课时出现；卡号仅在 `购卡 / 充值` 被选择时出现。B 型下以 **目标年度** 为必填业务字段（至少选当前年）。为了兼容 Excel round-trip，后端可继续接受空列，但 UI 不应把未选择能力展示成必填需求。

**表单底部操作行**：右对齐，`display flex justify-content flex-end gap 10px`；包含「导入 Excel」（outline 按钮）和「添加」（primary 按钮 + `<kbd>N</kbd>` 提示）。

### 6.6 Toolbar

```
display flex align-items center gap 10px; flex-wrap wrap
padding 14px 20px; border-bottom 1px solid var(--c-border)
```

**搜索框 `.search-wrap`**：relative 包装，左侧 10px 放 14×14 放大镜 SVG（color muted，pointer-events none），input `padding-left 34px`。

**分段控件 `.segmented`**：

```css
.segmented {
  display: inline-flex;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  padding: 3px;
  gap: 2px;
}
.segmented button {
  padding: 4px 11px; border-radius: calc(var(--r-sm) - 2px);
  font-size: 12.5px; border: none; cursor: pointer;
  background: transparent; color: var(--c-text-soft);
  transition: background var(--dur-fast), color var(--dur-fast);
}
.segmented button[aria-pressed="true"] {
  background: var(--c-surface);
  color: var(--c-text);
  box-shadow: var(--shadow-xs);
}
```

**右侧计数**：`已显示 N / 总 M`，12px，muted，margin-left auto。

### 6.7 表格

```css
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
thead th {
  padding: 10px 14px;
  font-size: 11.5px; font-weight: 600;
  letter-spacing: .5px; text-transform: uppercase;
  color: var(--c-text-muted);
  background: var(--c-surface-2);
  border-bottom: 1px solid var(--c-border);
  white-space: nowrap;
  position: sticky; top: var(--header-h); z-index: 10;
}
tbody tr {
  border-bottom: 1px solid var(--c-border);
  transition: background var(--dur-fast);
}
tbody tr:hover { background: var(--c-surface-2); }
tbody tr.is-failed { background: rgba(220,38,38,.03); }
tbody tr.is-failed:hover { background: rgba(220,38,38,.06); }
tbody td {
  padding: 12px 14px; font-size: 13.5px; vertical-align: middle;
}
```

**列宽分配**（`table-layout: fixed`）：

| 列 | 宽度 | 说明 |
|---|---|---|
| 姓名 | 100px | 加粗，不截断 |
| 账号 | 140px | `font-family: var(--font-mono)` |
| 学科·学分 | auto | 小 pill 标签列表，`gap 4px flex-wrap wrap` |
| 状态 | 120px | Pill 组件 |
| 说明 | auto | `max-width` + `title` 全文；`overflow hidden text-overflow ellipsis white-space nowrap` |
| 操作 | 220px | 按钮组（固定 3 个，见下） |

**操作列按钮组（固定 3 个，任意账号状态均显示，不得增减或按状态隐藏）**：`display flex gap 6px align-items center flex-wrap wrap`

| 按钮 | 样式 | 行为 |
|---|---|---|
| 重学 | `.btn-ghost .btn-sm` | `POST /api/accounts/{id}/requeue`；语义见 §10.1 |
| 编辑重学 | `.btn-outline .btn-sm` | 打开编辑模态（字段同 §6.5 添加表单）；确认后 `PATCH /api/accounts/{id}` 且 body 含 `"requeue": true` |
| 删除 | `.btn-icon .btn-ghost` 垃圾桶 SVG，hover 时 color `var(--c-danger)` | `DELETE /api/accounts/{id}`；删除该账号全部数据 |

**禁止**在操作列放置「详情」「复制日志」「强制重登」「重置课程」等第四按钮；上述能力通过其他入口提供（见 §6.13、§6.17）。

**姓名列**：`font-weight 600`，**点击姓名**打开详情抽屉（只读）；可配合账号列合并显示（姓名在上 14px，账号在下 11px muted mono）—— 如此可去掉独立账号列，节省宽度；选一种固定。

### 6.8 移动端卡片 `.mobile-card`（≤ 640px）

```css
.mobile-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
  box-shadow: var(--shadow-xs);
}
.mobile-card + .mobile-card { margin-top: 10px; }
```

内部结构：
1. 顶行 `flex space-between`：姓名（600 weight）+ 状态 Pill
2. 账号（mono 12px muted）
3. 学科·学分标签行
4. 说明（如有，muted 12px 两行省略）
5. 操作行（flex gap 8px flex-wrap）：重学 / 编辑重学 / 删除（与桌面表格 §6.7 三按钮一致）

### 6.9 空态 `.empty-state`

```html
<div class="empty-state">
  <!-- 内联 SVG 插图（约 60×60，由简单几何图形构成，双色调） -->
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
    <!-- 外圆 -->
    <circle cx="32" cy="32" r="28" stroke="var(--c-border-strong)" stroke-width="1.5"/>
    <!-- 内部简笔画：空托盘 or 用户图标 -->
    <path d="M22 36 C22 28 42 28 42 36" stroke="var(--c-border-strong)" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="32" cy="26" r="5" stroke="var(--c-border-strong)" stroke-width="1.5"/>
  </svg>
  <p class="empty-title">暂无账号</p>
  <p class="empty-sub">点击上方表单添加，或导入 Excel</p>
</div>
```

```css
.empty-state { display: flex; flex-direction: column; align-items: center;
               gap: 10px; padding: 48px 24px; color: var(--c-text-muted); }
.empty-title { font-size: 14px; font-weight: 500; color: var(--c-text-soft); }
.empty-sub   { font-size: 12.5px; }
```

搜索无结果时 `empty-sub` 改为 `"没有匹配 "xxx" 的账号"`。

### 6.10 Skeleton

```css
.skeleton { border-radius: var(--r-sm); background: var(--c-surface-3);
            position: relative; overflow: hidden; }
.skeleton::after {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(90deg,
    transparent 0%, var(--c-border) 40%,
    transparent 80%);
  animation: shimmer 1.5s linear infinite;
}
@keyframes shimmer {
  from { transform: translateX(-100%); }
  to   { transform: translateX(100%); }
}
```

使用 3 行假数据行，每行含 4 个宽度不等的 skeleton block（模拟列宽）。

### 6.11 Toast

- 挂在 `#toastStack`（`position fixed; right 20px; bottom 20px; display flex; flex-direction column-reverse; gap 10px; z-index 200`）
- 宽 320px；`background var(--c-surface)`；`border 1px solid var(--c-border)`；`border-radius var(--r-md)`；`box-shadow var(--shadow)`；`padding 12px 14px`；左侧 `3px solid` 按 tone 取色的 accent 条
- 内部：SVG 图标（16×16，按 tone）+ 文案（flex 1，13.5px）+ × 关闭按钮（`.btn-icon .btn-ghost`）
- 入场：`opacity 0 + translateY(6px) → 1 + 0`，`120ms ease`；消失：`opacity 0 + translateY(-4px)`，`120ms`
- 4 种 tone：`success / warning / danger / info`
- API：`window.ui.toast(msg, tone="info", ms=3500)`，`ms=0` 不自动关

### 6.12 Modal / Confirm

```css
.modal-backdrop { position fixed; inset 0;
                  background rgba(10,12,20,.48); backdrop-filter blur(3px);
                  z-index 150; display flex align-items center justify-content center;
                  animation fadeIn 160ms ease; }
.modal {
  background var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  width: min(460px, calc(100vw - 32px));
  max-height: 85vh; overflow-y: auto;
  animation: slideUp 220ms var(--ease-out);
}
@keyframes slideUp { from { opacity:0; transform:translateY(12px) scale(.97) } to { opacity:1; transform:none } }
```

结构：`.modal-head`（padding 18px 20px，border-bottom）/ `.modal-body`（padding 20px，14px line-height 1.6）/ `.modal-foot`（padding 14px 20px，flex justify-end gap 10px，border-top）

API：`await window.ui.confirm({ title, body, okText, okTone:"danger|primary", cancelText })` → `Promise<boolean>`

默认焦点落主按钮（`autofocus`），ESC 关闭，点遮罩关闭。

### 6.13 Drawer

```css
.drawer-backdrop { position fixed; inset 0; background rgba(10,12,20,.36);
                   backdrop-filter blur(2px); z-index 140; }
.drawer { position fixed; top 0; right 0; bottom 0;
          width min(580px, 100vw);
          background var(--c-surface);
          border-left 1px solid var(--c-border);
          box-shadow var(--shadow-lg);
          display flex; flex-direction column;
          animation slideInRight var(--dur-slow) var(--ease-out); }
@keyframes slideInRight { from { transform translateX(100%) } to { transform translateX(0) } }
```

- **头 `.drawer-head`**：`padding 18px 20px`，`border-bottom`；左标题（600 weight）+ 右 × 关闭按钮
- **体 `.drawer-body`**：`flex 1; overflow-y auto; padding 20px`
- **尾 `.drawer-foot`**：详情抽屉为**只读**，**不得**放置重学 / 编辑重学 / 删除 / 强制重登 / 重置课程等操作按钮（账户操作仅在列表 §6.7 三按钮）。若需底部栏，仅放「关闭」或省略 `.drawer-foot`。

**Tabs 在 drawer-body 内**（见 §6.14）

### 6.14 Tabs

```css
.tabs-nav { display flex; border-bottom 1px solid var(--c-border); gap 0; margin-bottom 18px; }
.tabs-nav button {
  padding 9px 16px; font-size 13px; font-weight 500;
  border none; background transparent; cursor pointer;
  color var(--c-text-muted);
  border-bottom 2px solid transparent;
  transition color var(--dur-fast), border-color var(--dur-fast);
  margin-bottom -1px;
}
.tabs-nav button[aria-selected="true"] {
  color var(--c-primary); border-bottom-color var(--c-primary);
}
```

Tabs 根据 `docs/API_REQUIREMENTS.md` 生成：基础为 `基本信息 / 课程进度 / 运行历史`；仅当站点存在申请学分流程时增加 `申请队列`。

**课程进度 Tab** 内每条课程显示：课程名 + 学科标签 + 学分 + 状态 Pill + 简短时间戳；用 `.kv` 或列表 flex 行展示。**列表按 `queue_rank` 升序**（与 `templates/requirements.md` §3.2.1 选课优先级一致）。

**运行历史 Tab** 内按时间倒序显示 runs，每条含开始时间、结果（成功/失败 Pill）、摘要文本；折叠/展开详细日志（`<details><summary>`）。

### 6.15 KV 键值表 `.kv`

```css
.kv { display grid; grid-template-columns 110px 1fr; gap 8px 14px;
      font-size 13px; }
.kv dt { color var(--c-text-muted); font-weight 500; padding-top 1px; }
.kv dd { color var(--c-text); word-break break-word; }
```

### 6.16 Spinner `.spinner`

```css
.spinner { width 14px; height 14px; border-radius 999px;
           border 2px solid var(--c-border);
           border-top-color var(--c-primary);
           animation spin .8s linear infinite; flex-shrink 0; }
@keyframes spin { to { transform rotate(360deg) } }
```

### 6.17 复制日志按钮（必须）

- 显示条件：`status === 'failed' || status === 'retrying'` 或 `error_log_text` 非空
- 位置：**仅**详情抽屉「基本信息」Tab 末尾（**不在**表格操作列，操作列固定三按钮 §6.7）
- 样式：`.btn-sm .btn-outline`，前置复制 SVG 图标
- 点击行为：`navigator.clipboard.writeText(error_log_text)` → `ui.toast('已复制到剪贴板', 'success', 2000)`
- 降级：`clipboard` 不可用时选中隐藏 `<textarea>` + `execCommand('copy')`
- **禁止**复制密码/cookie；日志内容由后端脱敏

---

## 7. 布局与响应式

| 断点 | 行为 |
|------|------|
| ≥ 1024px | stats 7 列（auto-fit minmax 140px 1fr），表格全展开，抽屉宽 580px |
| 641–1023px | stats auto-fit，表格保留所有列，抽屉 min(580px, 100vw) |
| ≤ 640px | header 隐藏文字 label（仅 logo + 暂停 + 主题），stats 2 列（minmax 130px），表格切卡片，抽屉 100vw，container padding 14px |
| ≤ 480px | 添加表单单列，upload-zone 简化 |

容器：`.container { max-width var(--container); margin 0 auto; padding 24px; display flex; flex-direction column; gap 20px; }`

---

## 8. 交互细节

1. **轮询自适应**：可见时 5s；`document.hidden` 时 30s；`visibilitychange` 触发立即刷一次。同一时刻只允许一个 in-flight 请求（`inflight` flag）。
2. **header spinner**：`#loadingDot` 刷新中显示，完成后隐藏；不要常亮。
3. **`#lastSync`**：`更新于 HH:MM:SS`；字体 mono 12px muted。
4. **Stat tile 数字动效**：数值更新时 countUp 动画（100ms，整数）。
5. **打开详情抽屉**：点击**姓名列**触发；整行与其他列不触发（避免与三操作按钮冲突）。
6. **搜索防抖**：250ms。
7. **添加成功**：清空表单 → 焦点回「姓名」→ toast 成功 → 立即 refresh。
8. **Excel 上传**：`j.failed > 0` 用 warning toast，否则 success；消息格式 `导入：新增 X，跳过 Y，失败 Z`。
9. **暂停/恢复**：根据 `data.paused` 切换两个按钮的 `[hidden]`。
10. **删除**：必须经 `ui.confirm`，`okTone:"danger"`，body 写明将永久删除该账号及全部运行数据（含 cookies、课表、运行记录）。
11. **重学 / 编辑重学**：须 `ui.confirm`（`okTone:"primary"`），body 说明将清除登录后产生的运行数据但**保留 cookies 等登录指纹**（重学）或**先保存表单再同等清除**（编辑重学）。若账号 `status === 'running'`，confirm 额外提示「将中断当前任务」。
12. **编辑重学模态**：字段与 §6.5 添加表单一致（含密码；空密码表示不修改）；主按钮文案「保存并重学」；取消不发请求。
13. **数字输入**：并发 `min=1 max=50 step=1`；学分 `min=0 step=0.5`。
14. **空态切换**：初次加载 → skeleton；数据到达 → 渐变 opacity `0→1`（200ms）；无数据 → empty-state。

---

## 9. 键盘快捷键（固定）

| 键 | 行为 |
|----|------|
| `/` | 聚焦搜索框 |
| `N` | 跳到添加表单「姓名」字段 |
| `Space` | 暂停 / 恢复调度 |
| `T` | 切换主题 |
| `Esc` | 关闭弹窗 / 抽屉 / blur 当前输入 |
| `?` | 弹出快捷键帮助 modal |

监听 `keydown`；若 `target` 是 `INPUT / TEXTAREA / SELECT` 则忽略（Esc 例外）。

快捷键帮助 modal 用表格展示，`<kbd>` 样式：`border 1px solid var(--c-border-strong); border-radius 4px; padding 1px 6px; font-family mono; font-size 11px; background var(--c-surface-2)`。

---

## 10. API 约定（前后端必须对齐）

| Method | Path | 入参 | 出参关键字段 |
|---|---|---|---|
| GET | `/api/accounts?status=&search=&limit=&offset=&date_from=&date_to=` | query | `{ items[{…, error_log_text?}], total, counts{…}, active_workers, paused, concurrency_limit }` |
| POST | `/api/accounts` | `{ display_name, username, password, requirements?:[{category, credits}], extra?:{...} }`，字段按 `docs/API_REQUIREMENTS.md` 启用 | `{ id }` |
| POST | `/api/accounts/upload` | multipart `file` | `{ added, skipped, failed, errors? }` |
| GET | `/api/accounts/{id}` | — | `{ ...account, error_log_text, extra{…}, apply_tasks[], runs[] }` |
| PATCH | `/api/accounts/{id}` | 部分字段；可选 `"requeue": true`（编辑重学，语义同 §10.1） | `{ ok: true }` |
| DELETE | `/api/accounts/{id}` | — | `{ ok: true }`；删除账号行及 runs / apply_queue / 业务流水等全部关联数据 |
| POST | `/api/accounts/{id}/requeue` | — | `{ ok: true }`；语义见 §10.1 |
| POST | `/api/scheduler/limit` | `{ limit:int }` | `{ ok: true, limit }` |
| POST | `/api/scheduler/pause` | — | `{ ok: true, paused: true }` |
| POST | `/api/scheduler/resume` | — | `{ ok: true, paused: false }` |
| GET | `/api/template` | — | xlsx 二进制 |
| GET | `/api/export` | — | xlsx 二进制 |

错误：`{ detail: "<可读中文消息>" }`，HTTP 4xx/5xx。`api()` 包装在非 2xx 时 `throw new Error(detail)`，调用处 catch 后 `ui.toast(err.message, 'danger')`。

**敏感字段**（`password`, `cookies`, `card_password`）必须从所有 GET 响应剥掉，用 `_safe_account()` 集中处理。

### 10.1 账户操作语义（后端必须实现，与 UI 三按钮一一对应）

#### 重学（`POST …/requeue` 或 `PATCH …` + `"requeue": true`）

**保留**（登录指纹，供下次 `ensure_session` 探活复用）：

- `extra.cookies`
- `extra.user_profile` 及站点定义的其它**纯会话/身份快照**字段（若有）
- 账号凭据列：`display_name`、`username`、`password`、`requirements_json`
- `extra` 中**账号配置型**字段（卡号、地区等导入/表单填写项，非运行期产出）

**清除**（登录之后产生的运行数据）：

- `extra.<DOMAIN>_results`、`extra.phase`、`extra.failed_phase`
- `status` → `queued`；`status_msg`、`retry_count`、`failed_phase` 归零/清空；`queued_at` → 当前时间
- 该账号的 `runs`、`apply_queue`、按日配额用的业务流水（如 `credit_applications`）
- 列表/详情中的 `error_log_text` 来源字段

**下次调度行为**：Worker 第一步 `ensure_session(cookies, probe=…)`；探活成功则**跳过登录**，从**分配/计划**起重新走登录后全流程（分配 → 日闸门 → 学习 → 申请等）。探活失败则走 `templates/requirements.md` §5.1 的常规登录流程。

若账号当前为 `running`：先标记中断/释放 worker，再执行上述清除并入队。

#### 编辑重学（`PATCH …` + `"requeue": true`）

1. 合并 PATCH body 中的可编辑字段（密码为空则不改密码）。
2. 执行与「重学」相同的保留/清除规则并入队。

#### 删除（`DELETE …/{id}`）

删除 `accounts` 行及所有关联数据（含 cookies、课表、runs、apply_queue、流水）；不可恢复。

**已废弃的 UI/API 面**：不再提供 `force_relogin`、`reset` 端点或按钮；「清 cookies 强制重登」与「只清课表」由「重学」（保留 cookies、清运行数据）与「删除」覆盖。

---

## 11. 占位符（生成 index.html 时替换）

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{PLATFORM}}` | 站点中文名 | "双卫网" |
| `{{LOGO_LETTER}}` | logo 方块 1-2 字符 | "双" / "MD" |

不再增加其余占位符——差异通过 `/api/*` 数据驱动。

---

## 12. 视觉质量基线（代码写完后必须对照）

生成的 UI 应当达到以下视觉标准，以下列出具体检查项：

- [ ] 卡片有轻微阴影（`shadow-sm`），鼠标悬停 stat tile 时 shadow 升级且微微上移 2px
- [ ] 每张 stat tile 右上角有对应语义的 SVG 图标（muted 色）
- [ ] `running` 状态 Pill 的圆点有 pulse 动画
- [ ] 表格 `thead` 吸顶，列名为全大写小号字（`text-transform uppercase; font-size 11.5px`）
- [ ] 暗色模式下卡片不显"纯黑"（`--c-surface #161921`，有明显层次）
- [ ] 输入框 focus 有蓝色光晕（`box-shadow 0 0 0 3px var(--c-primary-dim)`）
- [ ] 空态有 SVG 插图，不仅是一行文字
- [ ] Skeleton 有 shimmer 动画，非静态灰块
- [ ] Header Logo 方块用渐变色背景（蓝→紫），不是纯色
- [ ] Toast 有左侧 3px accent 色条 + 对应 tone 图标
- [ ] Modal/Drawer 有 backdrop-blur 遮罩，而非纯色遮罩
- [ ] 详情抽屉为只读，账户操作仅在列表三按钮（重学 / 编辑重学 / 删除）
- [ ] 移动端（375px 宽）表格切换为卡片视图，无横向滚动
- [ ] 所有按钮有 `:focus-visible` ring，且仅在键盘导航时显示
- [ ] 运行历史条目可展开查看原始日志，使用 `<details>` 原生折叠

---

## 13. 验收清单（写完 UI 必须自检）

- [ ] 离线断网打开 `http://127.0.0.1:<port>/`，所有样式、图标、交互正常
- [ ] Chrome DevTools Lighthouse Accessibility ≥ 90
- [ ] 切到 iPhone SE（375×667），表格变卡片，无横向滚动
- [ ] 切暗色主题，对比度无问题（标题、说明、徽章都清楚可读）
- [ ] 按 `/` `N` `Space` `T` `Esc` `?` 都生效
- [ ] 删除 / 重学 / 编辑重学先弹 confirm，取消后不发请求（DevTools Network 验证）
- [ ] 操作列始终仅三按钮；复制日志仅在详情抽屉内
- [ ] 假装 `/api/accounts` 返回 500：toast 报红，不卡死，下次轮询继续
- [ ] 标签页切到后台 ≥ 30s，切回后立即触发刷新且 `#lastSync` 更新
- [ ] 抽屉 ESC 关闭；modal ESC 关闭；点遮罩关闭
- [ ] 表头 sticky，长列表滚动时不消失
- [ ] 单 HTML 文件总行数 ≤ 1600
- [ ] 全页可见文案为简体中文（header、表头、toast、confirm、空态）；Web 列表表头与 Excel 导入列名一致（中文）
- [ ] 失败账号行有「复制日志」；点击后剪贴板与 `error_log_text` 完全一致
- [ ] Stat tile 数值变化时有 countUp 动画
- [ ] `running` 状态圆点有 pulse 动画
- [ ] 鼠标 hover stat tile 时卡片轻微上移

任何一条不过，必须修，不能推到后续阶段。

---

## 14. Site profile B — 公需年度型 Web UI（固定）

当 `docs/API_REQUIREMENTS.md` 为 **B — 公需年度型** 时，§6.5 添加面板按本节实现，**替代**学科/学分表单。参考 `liangshangongxu/webui/templates/index.html` + `app.py` `recent_five_years()`。

### 14.1 近 5 年年度选择

```javascript
// 服务端注入或内联计算（Asia/Shanghai 当前年）
function recentFiveYears() {
  const y = new Date().getFullYear();
  return [0,1,2,3,4].map(i => String(y - i));
}
```

- 容器 class：**`.year-pills`**，`display flex flex-wrap gap 8px`。
- 每个年度：**`<label class="year-pill">`** 内含 `type="checkbox"`，`name="target_years"`，`value="<年份>"`。
- **默认勾选当前自然年**；至少保留 1 个选中（提交前校验，否则 toast「请至少选择一个目标年度」）。
- 文案：`2026年` 格式（年份 + 「年」），不用英文缩写。

### 14.2 添加面板字段（B 型）

| 字段 | 控件 | 说明 |
|------|------|------|
| 账号 | `input` | 必填 |
| 密码 | `input type=password` | 必填 |
| 备注 | `input` | 可选 |
| 目标年度 | `.year-pills` 多选 | 见 §14.1 |
| 任务模式 | `radio` 或 segmented | `标准`（normal）/ `快速`（fast），默认标准 |

**不展示**：姓名（登录后回填展示）、学科1/2、学分、卡号。

底部操作行仍为「导入 Excel」+「添加」（`N` 快捷键）。

### 14.3 列表与详情

- 列表列：账号、备注、**目标年度摘要**（如 `2026、2025`）、状态、进度（可用细条 `progress_percent` 或按年最小完成率）。
- 展开/抽屉：**按年分组**展示 `year_status`（已购、要求学时、已获得、是否完成、当前课程名）；**无**「学科·学分」pill 行。
- 课程 Tab（若有）：按 **年度 → 课程列表** 嵌套，排序与 `queue_rank` 无关（B 型无 planner）。

### 14.4 API 形状（B 型）

| 方法 | 路径 | Body 要点 |
|------|------|-----------|
| POST | `/api/accounts` | `{ username, password, remark?, target_years: string[], report_mode?: "normal"\|"fast" }` |
| PATCH | `/api/accounts/{id}` | 同上；`requeue` 行为同 A 型 |

`GET /api/accounts/{id}` 的 `extra` 含 `year_status`、`current_year`、`phase`（中文 phase 标签映射见项目 `view_format`）。

### 14.5 B 型验收追加项

- [ ] 添加面板显示近 5 年 pill，当前年默认选中
- [ ] 未选年度提交被拦截（中文 toast）
- [ ] 列表/抽屉无学科1/学分必填提示
- [ ] Excel 导入列与 §14.2 一致（见 `excel-spec.md` §2B）
