# Web Console UI Spec (固定，不要跑偏)

本规格描述 phase 5 的 Web 控制台必须长什么样、用什么、怎么交互。  
**执行 agent 必须按本规格自行生成 `<svc>/web/templates/index.html`，本 skill 不再提供 HTML 模板。**  
所有"可以这么写也可以那么写"的位置都已固定下来。除非用户明确要求，**不要**临时引入新依赖、新组件库、新色板。

---

## 0. 硬约束（不可破坏）

1. **界面语言必须为中文**：`<html lang="zh-CN">`；所有可见文案（标题、按钮、表头、placeholder、toast、confirm、空态、徽章、快捷键帮助）使用**简体中文**。禁止英文 UI（API 路径 `/api/...` 除外）。状态枚举显示中文：排队/进行中/等待申请/重试/已完成/失败/已暂停。
2. **零运行时外链依赖**：不允许 `<script src="https://...">` / `<link href="https://...">`。所有 CSS、JS、字体、图标全部内联在一个 HTML 文件里。理由：PyInstaller 单文件 + 离线场景必须能直接用。
3. **单文件**：整套控制台只有一个 HTML（含 `<style>` + `<script>`）。FastAPI 用 Jinja `TemplateResponse` 直接返回。
4. **原生 vanilla JS**：不引入 React / Vue / Alpine / jQuery / lit / htmx 等任何前端框架，不引入任何 UI 库（element-plus / antd / bootstrap / tailwind 等都不允许）。
5. **图标用 inline SVG**：单色线性图标，stroke-width 1.6，viewBox `0 0 16 16`。不准用 emoji。
6. **总代码量预算**：HTML+CSS+JS 合计 ≤ 1200 行；超出说明设计走偏了，应当先简化。
7. **可访问性**：所有可点击元素必须有可见 `:focus-visible`；模态/抽屉必须能 ESC 关闭；色彩对比度 ≥ 4.5:1。

---

## 1. 技术栈（固定）

| 项 | 选定值 | 备注 |
|---|---|---|
| 模板引擎 | Jinja2（FastAPI 自带） | 仅用占位符替换 `{{PLATFORM}}` / `{{LOGO_LETTER}}` |
| 样式 | 内联 `<style>`，CSS 变量驱动 | 见 §3 design tokens |
| 脚本 | 内联 `<script>`，IIFE，`"use strict"` | 不污染全局，只在 `window.ui` 暴露 toast/confirm/drawer |
| 图标 | inline SVG | 单色 currentColor |
| 字体 | 系统字体栈（见 §3） | 不下载外部字体 |
| 通信 | `fetch` + JSON | 统一封装在 `api()` 里 |
| 数据 | `/api/*` REST，5s 轮询 | 见 §8 |

---

## 2. 页面骨架（顶到底）

```
┌─ <header class="app-header">  sticky, 56px, backdrop-blur
│   Logo小方块 + 站点中文名 · 调度状态徽章 · 最近刷新时间 + spinner
│   ── flex spacer ──
│   并发数 input · [暂停|恢复] · [模板] · [导出] · 主题切换图标
├─ <main class="container"> max-width 1280px, padding 20px, grid gap 16px
│   ① <section class="stats">         状态概览（7 张 stat tile）
│   ② <section class="card" id="addCard">  添加账号（表单 + 上传 Excel）
│   └ ③ <section class="card">        账号列表（toolbar + 表格/移动端卡片）
├─ <div id="toastStack">    右下角 toast 堆叠
├─ <div id="modalMount">    全局模态/确认弹窗挂载点
└─ <div id="drawerMount">   右侧抽屉挂载点（账号详情）
```

### 各 section 详细要求

**① 状态概览 stats**
- 7 张瓦片：`总数 / 排队 / 进行中 / 等待申请 / 已完成 / 失败 / 活跃 Worker`
- 每张瓦片是一个 `<button class="stat">`：点击 = 设置状态过滤器（"总数"=清空过滤，"活跃 Worker"不可点）
- 当前激活的瓦片用 `data-active="true"` 标记，外圈 3px 主色 ring
- 数字用 `font-variant-numeric: tabular-nums`，避免抖动
- 颜色调性（tone）：`progressing=primary / waiting_apply=warning / completed=success / failed=danger / active_workers=info`，其余为默认中性色

**② 添加账号 addCard**
- 表单字段（按本顺序）：姓名 / 账号 / 密码 / 学科1 / 学分1 / 学科2（可选）/ 学分2（可选）
- 上传 Excel：`<label class="btn btn-outline">` 包 `<input type="file" hidden>`，accept `.xlsx,.xls`
- 提交按钮显示 `添加 <kbd>N</kbd>`（提示快捷键）
- 提交时禁用按钮 + `aria-busy="true"` + 显示 spinner
- 成功/失败用 toast，不用内联红字

**③ 账号列表**
- toolbar：搜索框（左侧 SVG 放大镜，placeholder `搜索姓名 / 账号  ( / )`）+ 分段控件（segmented）状态过滤 + 右侧灰色 `已显示 N / 总 M`
- 桌面端（≥ 641px）：`<table>`，列 `姓名 / 账号 / 学科·学分 / 状态 / 说明 / 操作`
  - thead 浅色背景，sticky，列名小写小字 letter-spacing 0.4px
  - hover 行高亮、展开行用 `is-expanded`
  - 操作列：`详情` / `重入队` / `复制日志`（仅失败/重试时显示）/ `删除（垃圾桶 icon）`
  - 「说明」列：`status_msg` 过长时 `max-width` + `title` 全文；失败行可在说明旁放 `.btn-sm`「复制」
- 移动端（≤ 640px）：隐藏 table，显示 `<div class="mobile-cards">` 卡片列表，每张卡片含姓名、账号、状态徽章、需求、说明、操作
- 加载占位：3 行 `skeleton` 灰条带 shimmer 动画
- 空态：`<div class="empty">无数据</div>`，居中、`--c-text-muted`

---

## 3. Design Tokens（CSS 变量，固定）

写入 `:root`，暗色覆盖写入 `[data-theme="dark"]` + `@media (prefers-color-scheme: dark) [data-theme="auto"]`。

```
颜色（浅色默认）
--c-bg:           #f6f7fb     页面背景
--c-surface:      #ffffff     卡片/表格背景
--c-surface-2:    #f1f3f8     hover/分段控件凹槽
--c-border:       #e3e6ee     普通描边
--c-border-strong:#cbd0dc     hover/聚焦描边
--c-text:         #1d2433
--c-text-soft:    #5b6477
--c-text-muted:   #8b93a4
--c-primary:      #3759f0     主蓝
--c-primary-soft: #e6ebff
--c-success:      #16a34a     成功绿
--c-success-soft: #dcfce7
--c-warning:      #d97706     警告橙
--c-warning-soft: #fef3c7
--c-danger:       #dc2626     危险红
--c-danger-soft:  #fee2e2
--c-info:         #0ea5e9     信息青
--c-info-soft:    #e0f2fe

圆角
--radius-sm: 6px              按钮、输入框、pill
--radius:    10px             卡片
--radius-lg: 14px             模态
--radius-pill: 999px          徽章、分段控件

阴影
--shadow-sm: 小阴影，stat 默认
--shadow:    中阴影，hover / toast 入场
--shadow-lg: 大阴影，模态 / 抽屉

动效
--motion-fast: 120ms          input focus
--motion:      180ms          多数过渡
--motion-slow: 280ms          抽屉入场
--ease:        cubic-bezier(.2,.7,.2,1)

字体
--font:      -apple-system, BlinkMacSystemFont, "Segoe UI",
             "PingFang SC", "Microsoft YaHei", "Helvetica Neue",
             Helvetica, Arial, sans-serif
--font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono",
             "Cascadia Code", Consolas, "Liberation Mono", Menlo, monospace

布局
--header-h: 56px
--container: 1280px
```

**暗色覆盖**（仅列差异）

```
--c-bg:           #0f1117
--c-surface:      #171a23
--c-surface-2:    #1f2330
--c-border:       #262b3a
--c-border-strong:#363c50
--c-text:         #e6e9f2
--c-text-soft:    #aab1c2
--c-text-muted:   #7d8497
--c-primary:      #7491ff       亮一点的蓝，保证对比度
--c-primary-soft: #1d2747
--c-success-soft: #142e1f
--c-warning-soft: #36280a
--c-danger-soft:  #3a1414
--c-info-soft:    #0c2a3a
（阴影改为黑色透明）
```

主题状态在 `<html data-theme="auto|light|dark">` 上，存 `localStorage["theme"]`，切换顺序 `auto → light → dark → auto`。

---

## 4. 组件清单（固定，必须实现）

### 4.1 Button `.btn`
- 变体：`.btn-primary`（实心主色）/ `.btn-outline`（描边）/ `.btn-ghost`（透明，hover 出底色）/ `.btn-danger`（实心红）
- 尺寸：默认 `padding: 7px 13px / font-size: 13px`；`.btn-sm` 4×10/12px；`.btn-icon` 6px 方形
- 状态：`:hover` / `:active`（translateY +1） / `:disabled`（opacity .55 + cursor not-allowed） / `[aria-busy="true"]`（progress 光标 + 自带 spinner）
- 图标在按钮内：`<svg class="icon">`，14×14

### 4.2 Pill `.pill`
- 圆角胶囊 + 左侧 6×6 圆点 `.dot`
- 按 `data-tone` 取 `queued / running / waiting_apply / retrying / completed / failed / paused` 颜色对
- 用于状态显示。**`queued` 中性色，不要用绿色**（绿色仅留给 completed）

### 4.3 Stat tile `.stat`
- 见 §2①。点击切换过滤；激活态用 `data-active="true"` 加 3px ring

### 4.4 Toolbar 分段控件 `.segmented`
- 凹槽 `--c-surface-2`，激活项用 `--c-surface` + `--shadow-sm`，`aria-pressed="true"`
- 用于状态过滤切换

### 4.5 Toast
- 挂在 `#toastStack`（fixed right:16 bottom:16，纵向 stack，gap 8px）
- 4 种 tone：`success / warning / danger / info`，左侧 3px 边框色对应
- API：`window.ui.toast(msg, tone="info", ms=3500)`，`ms=0` = 不自动关
- 右上角 `×` 关闭按钮
- 入场 `translateY(8px) → 0`，120-180ms
- **所有 API 错误/成功提示必须走 toast，禁止 `alert()`、`console.log` 单独使用**

### 4.6 Modal / Confirm
- 背景 `rgba(15,17,23,.42)` 全屏遮罩，点击空白处关闭
- 居中 `max-width: 440px`，圆角 14px，头/体/尾三段
- API：`await window.ui.confirm({ title, body, okText, okTone, cancelText })` → `Promise<boolean>`
- 默认焦点落在主按钮（autofocus），ESC 关闭
- **所有破坏性操作（删除、重置）必须经 confirm，禁止 `confirm()` 浏览器原生弹窗**

### 4.7 Drawer
- 右侧滑入 `width: min(560px, 100vw)`，280ms ease
- 头（标题 + 关闭按钮 ×）/ 体（可滚动）/ 尾（操作按钮组，可选）
- 用于"账号详情"，必须含 Tabs：`基本信息 / 课程 / 申请队列 / 运行历史`
- API：`window.ui.drawer({ title, body, footer })` → `{ close }`

### 4.8 Tabs
- 横向 button row + 底部 2px primary 指示条
- `role="tablist"`，激活按钮 `aria-selected="true"`
- 切换时 `[hidden]` 切换面板，不用 display none 重排

### 4.9 Skeleton
- `.skeleton`：`linear-gradient(90deg, surface-2, border, surface-2)` + 1.4s linear shimmer
- 初次加载用 1-3 行 skeleton 替代真实行

### 4.10 KV 键值表 `.kv`
- `<dl class="kv">`，`grid-template-columns: 110px 1fr`，gap `6px 14px`
- 用于详情抽屉的"基本信息"

### 4.11 Spinner
- 14×14 圆环，主色 top 边，0.9s 旋转
- 用在 header 刷新指示器、按钮 busy 态

### 4.12 复制日志按钮 `.btn-copy-log`（必须）
- 文案：**复制日志**（抽屉内可缩短为 **复制**）
- 显示条件：`status === 'failed' || status === 'retrying'`，或 `error_log_text` 非空
- 位置：账号列表操作列；详情抽屉「基本信息」Tab 底部或 KV 区下方；移动端卡片 actions 区
- 行为：点击 → `navigator.clipboard.writeText(error_log_text)` → `ui.toast('已复制到剪贴板', 'success', 2000)`
- 降级：`clipboard` 不可用时选中隐藏 `<textarea>` + `document.execCommand('copy')`，仍 toast 结果
- 数据来源：列表项字段 `error_log_text`（见 `excel-spec.md` §4）；详情 API 同字段
- **禁止**复制密码/cookie；日志内容后端已脱敏

### **不需要实现的组件**
- Tooltip（用 `title` 属性即可）
- Dropdown menu（用按钮组替代）
- Date picker（需要时用 `<input type="date">`）
- Charts / sparklines（本期不做）

---

## 5. 布局与响应式

| 断点 | 行为 |
|------|------|
| ≥ 1024px | 三列 stats（auto-fit minmax 140px），表格全展开 |
| 641-1023px | stats auto-fit；表格保留所有列；侧栏抽屉宽 560 |
| ≤ 640px | header 隐藏文字 label，仅保留 logo + 关键按钮；表格切换为 `.mobile-cards`；抽屉 100vw；container padding 改 12px |
| ≤ 480px | 添加表单 form-grid 单列 |

容器规则：
- `.container max-width: 1280px; margin: 0 auto;`
- `.form-grid grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))`
- `.stats grid-template-columns: repeat(auto-fit, minmax(140px, 1fr))`

**不要**用 flex 强行三列；用 `auto-fit / auto-fill` 自适应。

---

## 6. 交互细节（容易丢的地方）

1. **轮询自适应**：可见时 5s 一次；`document.hidden` 时降到 30s；`visibilitychange` 触发立即刷新一次。同一时刻只允许一个 in-flight 请求（`inflight` 锁），覆盖时丢弃旧的。
2. **header spinner**：刷新进行中 `#loadingDot` 显示，完成后隐藏；不要让它常亮。
3. **`#lastSync`**：显示 `更新于 HH:MM:SS`。
4. **表格行点击**：仅"详情"按钮触发详情抽屉；不要让整行点击触发（避免误删/误重入队的 hit target 冲突）。
5. **搜索防抖**：input 事件 250ms 后触发 refresh。
6. **过滤态同步**：stat 瓦片激活态、分段控件激活态、URL 不用同步（保持单页内状态即可，刷新页面状态丢失可接受）。
7. **添加成功后**：清空表单 → 焦点回到"姓名" → toast 成功 → 立即 refresh。
8. **Excel 上传后**：根据 `j.failed` 选 toast tone（>0 用 warning，否则 success），消息格式 `导入：新增 X，跳过 Y，失败 Z`。
9. **暂停按钮和恢复按钮**：根据 `data.paused` 切换 `[hidden]`，状态徽章 `data-tone` 在 `running ↔ paused` 间切换。
10. **删除/重置确认**：必须经 `ui.confirm`，主按钮 `okTone="danger"`，文案 `body` 写明影响范围。
11. **抽屉操作**：底部固定 `强制重登 / 重置课程 / 重入队` 三个按钮；重置课程必须二次确认。
12. **数字输入**：并发数 `min=1 max=50`；学分 `step=0.5 min=0`。
13. **复制日志**：失败/重试账号点击「复制日志」后，剪贴板内容与 `GET /api/accounts/{id}` 的 `error_log_text` 完全一致；成功 toast「已复制到剪贴板」。

---

## 7. 键盘快捷键（固定）

| 键 | 行为 |
|----|------|
| `/` | 聚焦搜索框 |
| `N` | 跳到添加表单的"姓名"字段 |
| `Space` | 暂停 / 恢复调度 |
| `T` | 切换主题 |
| `Esc` | 关闭弹窗 / 抽屉 / 取消输入聚焦 |
| `?` | 弹出快捷键帮助（一个 modal） |

实现要点：监听 `keydown`，若 `target.tagName` 是 `INPUT/TEXTAREA/SELECT` 则忽略（Esc 例外，触发 blur）。

---

## 8. API 约定（前后端必须对齐）

| Method | Path | 入参 | 出参关键字段 |
|---|---|---|---|
| GET | `/api/accounts?status=&search=&limit=&offset=&date_from=&date_to=` | query | `{ items[{…, error_log_text?}], total, counts{…}, active_workers, paused, concurrency_limit }` — `error_log_text` 在 failed/retrying 时必填 |
| POST | `/api/accounts` | `{ display_name, username, password, requirements:[{category, credits}] }` | `{ id }` |
| POST | `/api/accounts/upload` | multipart `file` | `{ added, skipped, failed, errors? }` |
| GET | `/api/accounts/{id}` | — | `{ ...account, error_log_text, extra{…}, apply_tasks[], runs[] }` |
| PATCH | `/api/accounts/{id}` | 部分字段 | `{ ok: true }` |
| DELETE | `/api/accounts/{id}` | — | `{ ok: true }` |
| POST | `/api/accounts/{id}/requeue` | — | `{ ok: true }` |
| POST | `/api/accounts/{id}/force_relogin` | — | `{ ok: true }` |
| POST | `/api/accounts/{id}/reset` | — | `{ ok: true }` |
| POST | `/api/scheduler/limit` | `{ limit:int }` | `{ ok: true, limit }` |
| POST | `/api/scheduler/pause` | — | `{ ok: true, paused: true }` |
| POST | `/api/scheduler/resume` | — | `{ ok: true, paused: false }` |
| GET | `/api/template` | — | xlsx 二进制 |
| GET | `/api/export` | — | xlsx 二进制 |

错误统一返回 `{ detail: "<可读中文消息>" }`，HTTP 4xx/5xx。前端 `api()` 包装层在非 2xx 时 `throw new Error(detail)`。

**敏感字段（`password`, `cookies`, `card_password`）必须从所有 GET 响应里剥掉**。提供 `_safe_account()` 工具方法集中处理。

---

## 9. 占位符（生成 index.html 时替换）

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{PLATFORM}}` | 站点中文名 | "双卫网" |
| `{{LOGO_LETTER}}` | logo 方块里的 1-2 个字符 | "双" / "MD" |

不要再加更多占位符 —— 其余差异通过 `data-*`、CSS 变量、`/api/*` 数据驱动。

---

## 10. 验收清单（写完 UI 必须自检过）

- [ ] 离线环境断网打开 `http://127.0.0.1:<port>/`，所有样式、图标、交互正常
- [ ] Chrome DevTools Lighthouse Accessibility ≥ 90
- [ ] 关闭网络后刷新页面，CSS/JS 不会因外链 404 丢失
- [ ] 切到 iPhone SE 视口（375×667），表格变卡片，无横向滚动
- [ ] 切暗色主题，对比度无问题（标题、说明、徽章都清楚可读）
- [ ] 按 `/` `N` `Space` `T` `Esc` `?` 都生效
- [ ] 删除/重置必须先弹 confirm，取消后不发请求（DevTools Network 验证）
- [ ] 假装 `/api/accounts` 返回 500：toast 报红，不卡死页面，下次轮询继续
- [ ] 标签页切到后台 ≥ 30s，再切回，应立即触发一次刷新且 `#lastSync` 更新
- [ ] 抽屉 ESC 能关闭；模态 ESC 能关闭；点遮罩能关闭
- [ ] 表头 sticky，长列表滚动时表头不消失
- [ ] 所有按钮聚焦时有可见 ring（`outline: 2px solid var(--c-primary); outline-offset: 2px`）
- [ ] 单 HTML 文件总行数 ≤ 1200
- [ ] 全页可见文案为简体中文（抽查：header、表头、toast、confirm、空态）
- [ ] 失败账号行有「复制日志」；点击后剪贴板内容与 `error_log_text` 一致

任何一条不过，必须修，不能用 "下个 phase 再说" 推。
