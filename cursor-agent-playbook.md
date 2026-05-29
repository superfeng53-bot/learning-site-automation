# Cursor Agent Playbook（本 skill 专用）

本文件教 Cursor Agent **如何在本 skill 的各阶段管理上下文、何时开新对话、何时派子 agent、何时调用其他 skill/MCP**。  
主入口 `SKILL.md` 在 phase gate 处引用本文件；进入 phase 1/2/5 前**先读对应小节**。

---

## 1. Cursor 工具体系（按阶段选用）

### 1.1 站点解析：必须用 Cursor 内置浏览器（硬规则）

在 **Cursor IDE / Cursor Agent** 中执行本 skill 时，Phase 1–2 的**所有现场解析**（打开页面、点表单、走业务流、看 Network、读 cookie/localStorage）**一律优先且默认使用** MCP **`cursor-ide-browser`**（Cursor 内置浏览器工具），**不要**用下列替代做侦察：

- ❌ Playwright / Selenium / Puppeteer 脚本（runtime 与侦察均禁止，见 `SKILL.md` Anti-Patterns）
- ❌ 让用户手动开 Chrome DevTools 口述请求（除非内置浏览器不可用，见下）
- ❌ `WebFetch` / 纯 `curl` 猜登录页与 AJAX（仅可在 **browser 已产出 endpoint 样本之后** 做 HTTP 对照，见 §5 `shell`）

**调用前**：`Read` 项目内 `mcps/cursor-ide-browser/tools/*.json`（或当前工作区 MCP 描述目录），按 schema 调用；典型顺序见 `phase1-login-recon.md` Step 2：`browser_navigate` → `browser_lock` → `browser_snapshot` / `browser_fill` / `browser_click` → `browser_cdp`（`Network.enable`、`Runtime.evaluate` 等）→ `browser_lock` unlock。

**子 agent 侦察**：派 `Task explore` 或项目级 `api-recon` subagent 时，prompt 里**必须写明**「用 `cursor-ide-browser` MCP，禁止外部浏览器自动化」。

**仅当内置浏览器不可用**（MCP 未启用、页面需企业证书/特殊插件、用户明确指定外部环境）时：停止 improvising，向用户说明阻塞项，并改用手动抓包 + 用户提供的 HAR/请求样本写入 `docs/`；仍不得把 Playwright 写进 `<pkg>/` runtime。

### 1.2 按阶段工具表

| 阶段 | 首选工具 | 用途 |
|------|----------|------|
| Phase 1 登录侦察 | **`cursor-ide-browser` MCP**（§1.1） | 打开登录页、抓 Network、读 cookie/localStorage |
| Phase 1 登录侦察 | **`Task` + `subagent_type=explore`** 或 **`.cursor/agents/api-recon`** | 只读梳理页面结构；产出 draft md（须走内置浏览器） |
| Phase 1 实现 | **`Task` + `subagent_type=generalPurpose`** | 独立实现 `captcha.py` / `login.py`（输入：侦察摘要文件） |
| Phase 2 API 发现 | **`cursor-ide-browser` MCP**（§1.1） | 手动走一遍业务流，抓每个 domain 的请求 |
| Phase 2 API 发现 | **`Task` + `explore`**（并行） | 每个业务域一份 `docs/api-discovery/<domain>.md` 草稿 |
| Phase 2 HTTP 对照 | **`shell` skill**（可选） | browser 定稿后用 `curl`/小脚本对照 cookie 与响应 |
| Phase 2 实现 | **`Task` + `generalPurpose`**（并行） | 每个 domain 一个 `*Service` + `cli_*.py` |
| Phase 2 结束 / 多站点 | **`create-rule`** + **`memory-merger`** | 项目规则沉淀解析约定；workspace 级记忆合并 |
| 复杂登录/API 时序 | **`canvas` skill**（可选） | 交互式流程图，辅助审阅（结论仍写入 `docs/`） |
| Phase 5 Excel | **`spreadsheet` skill**（`~/.agents/skills/spreadsheet/SKILL.md`） | 生成/校验中文模板 xlsx、导出列顺序 |
| Phase 5 Web UI | **`Task` + `generalPurpose`** | 按 `web-ui-spec.md` 生成 `index.html` |
| 任意阶段边界 | **`rename_chat`** MCP | 把对话标题改成 `Phase N · <站点名> · <状态>`，方便用户找 handoff 点 |

**不要**在 runtime 代码里用 browser MCP；它只用于 phase 1–2 侦察。

---

## 2. 上下文压缩 vs 新开对话（固定策略）

Cursor **没有**「一键清空上下文」工具。等效做法是：**把知识写进项目文件 + 用短 handoff 开新对话**。

### 2.1 必须写 handoff 文件的时机

在每个 **phase 结束**、以及下列 **phase 内检查点** 结束时，写入：

```
docs/handoffs/PHASE<N>_<slug>.md
```

`<slug>` 示例：`login-recon-done` / `api-course-exam-done` / `web-ui-done`

Handoff 模板（固定 8 段，每段 1–5 行，**禁止粘贴大段代码**）：

```markdown
# Phase N Handoff — <站点中文名>

## 已完成
- …

## 关键路径（绝对路径）
- …

## 站点决策（不可丢）
- captcha 族：…
- `<pkg>` / `<svc>`：…
- 每日配额：…

## 已验证命令
- …

## 验收摘要
- 报告：`docs/verification/PHASE<N>_REPORT.md`（DoD/spec 逐项 pass/fail + 证据）
- 缺口：`docs/gaps/PHASE<N>_gaps.md`（无则写「无」）

## 未完成 / 下步第一件事
- …

## 新对话启动语（复制给 Agent）
请继续 learning-site-automation skill，从 Phase X 开始。先 Read：
- docs/handoffs/PHASE…md
- phaseX-….md
项目根：<绝对路径>
```

写完后在聊天里**明确告诉用户**：

> 建议 **New Chat（新对话）**，把上面「新对话启动语」整段粘贴进去再继续。  
> 若继续当前对话，我会只依赖 handoff 文件，不再引用本对话早期的 browser 抓包细节。

### 2.2 何时强烈建议新开对话

| 时机 | 原因 |
|------|------|
| Phase 1 → Phase 2 | browser 抓包 + 验证码试错占满上下文 |
| Phase 2 每完成 **2 个** business domain | 每个 domain 的 request/response 样本很大 |
| Phase 2 → Phase 3 | API 细节应已在 `API_REFERENCE.md`，聊天可丢弃 |
| Phase 5 的「后端 store/worker」→「Web UI」| UI spec 与调度逻辑不应混在同一上下文 |
| 任何阶段内已读 **>8 个文件** 或编辑 **>15 次** | 见 `SKILL.md` Context Budget |

### 2.3 当前对话内压缩（不新开 chat 时）

1. **停止**再读 phase 文件全文；只 `Read` handoff + 当前要改的文件  
2. 浏览器/MCP 原始输出：**不要**留在聊天里复述；写入 `docs/LOGIN_FLOW.md` 或 `docs/api-discovery/*.md`  
3. 子 agent 只回传：**结论 + 文件路径 + 一条验证命令**  
4. 用 `rename_chat` 标记：`Phase 2 · 双卫网 · course+study 完成`

---

## 3. Phase 1–2 推荐编排（子 agent + MCP）

### Phase 1 三步走

```
[父 Agent] init_project.py + 读 phase1-login-recon.md
    ↓
[子 explore 或 父+ browser MCP] Step 2 侦察
    → 产出 docs/LOGIN_FLOW.draft.md（endpoint、captcha、cookie、失败码表）
    ↓
[父 Agent] 审阅 draft → 定 captcha 族 → AskQuestion（若 ambiguous）
    ↓
[子 generalPurpose] 实现 captcha.py + login.py + cli_login.py
    → 输入：draft 路径 + data/account.json
    ↓
[父 Agent] 跑通登录 → 定稿 docs/LOGIN_FLOW.md → PHASE1_handoff
```

**Phase 1 侦察子 agent 提示词骨架**（复制改写）：

```
你是 learning-site-automation Phase 1 侦察子任务。
项目根：<abs_path>
登录 URL：<url>
测试账号：见 data/account.json（勿在回复里复述密码）

在 Cursor 中必须用 cursor-ide-browser MCP（内置浏览器）完成 phase1-login-recon.md Step 2。
禁止 Playwright/Selenium/WebFetch 替代现场解析。调用 MCP 前先 Read mcps/cursor-ide-browser 工具 schema。
把结论写入 docs/LOGIN_FLOW.draft.md，结构同 LOGIN_FLOW.md 七章。
不要写 login.py。回复只给：draft 路径 + captcha 族判断 + 阻塞项。
```

### Phase 2 按 domain 并行

对每个 relevant domain（course / study / exam / credit / …）：

1. **侦察**：browser MCP 或 `Task explore` → `docs/api-discovery/<domain>.md`  
2. **实现**：`Task generalPurpose` → `<pkg>/<domain>.py` + `cli_<domain>.py`  
3. **父 Agent 合并**：更新 `API_REFERENCE.md` 一节  

**每完成 2 个 domain** → 写 `docs/handoffs/PHASE2_<domains>_done.md`，建议用户新开会话。

Phase 2 侦察子 agent **不要**一次包「全部 6 个 domain」；一次最多 **1–2 个 domain**。

**Phase 2 侦察子 agent 提示词骨架**（复制改写）：

```
你是 learning-site-automation Phase 2 API 侦察子任务（domain: <course|study|exam|…>）。
项目根：<abs_path>
已登录 cookie：见 data/cookies.json（勿在回复里复述）

在 Cursor 中必须用 cursor-ide-browser MCP 走一遍该 domain 的业务操作并抓 Network。
禁止 Playwright/Selenium；禁止未走 browser 就用 WebFetch/curl 编造 endpoint。
调用 MCP 前先 Read mcps/cursor-ide-browser 工具 schema。
把结论写入 docs/api-discovery/<domain>.md（method、path、body、响应样本、失败码）。
不要写 *Service 代码。回复只给：md 路径 + 阻塞项 + 一条建议的 curl 对照命令（可选）。
```

### 3.1 解析增强流水线（Cursor 内推荐顺序）

Phase 1–2 在 Cursor 中执行时，按此顺序叠工具与 skill（结论始终落盘到 `docs/`）：

```
cursor-ide-browser（内置浏览器，§1.1）
    → Task explore 或 .cursor/agents/api-recon（可选，须写明用内置浏览器）
    → docs/LOGIN_FLOW.draft.md / docs/api-discovery/<domain>.md
    → shell skill：curl/小脚本对照（仅验证，不替代 browser 发现）
    → 父 agent 合并 → API_REFERENCE.md / LOGIN_FLOW.md
    → create-rule（项目内解析约定，可选）
    → memory-merger（多站点/workspace 沉淀，可选）
    → Task generalPurpose 实现 login.py / *Service
```

复杂 SSO 或多步 captcha 时，可 Read **`canvas` skill** 画时序图辅助审阅；**仍以 `docs/` 文字为权威**。

---

## 4. Phase 5 子任务拆分（与上下文）

| 顺序 | 子任务 | 建议执行方式 | handoff 后是否新 chat |
|------|--------|--------------|------------------------|
| 5a | schema + store + recovery | 父 agent 或 1 个子 agent | 可选 |
| 5b | worker + apply_worker + orchestrator | 父 agent | 建议新 chat 再做 5c |
| 5c | FastAPI `/api/*` | 子 generalPurpose | — |
| 5d | Web UI `index.html` | 子 generalPurpose + `web-ui-spec.md` | — |
| 5e | Excel 模板/导入/导出 | 读 **`spreadsheet` skill** + `excel-spec.md` | — |

5c 与 5d 可并行两个子 agent；父 agent 只做集成与 DoD 验收。

---

## 5. 与其他 skill / MCP 的协作方式

**总则（Cursor 执行环境）**

1. **站点现场解析**：MCP **`cursor-ide-browser`**（Cursor 内置浏览器）为默认且首选，见 §1.1。  
2. **调用任何外部 skill**：**先 `Read` 其 `SKILL.md`，再执行**；不要把各 skill 的全文流程写进业务仓库注释。  
3. **子 agent 与 skill 分工**：browser 侦察可派 `Task` 或项目 subagent；**实现** `login.py` / `*Service` 用 `generalPurpose`；**不要**用 `shell` / `WebFetch` 替代 browser 做「第一次」发现 endpoint。

### 5.1 Phase 1–2 解析与分析（优先组合）

| 工具 / skill | 路径提示 | 何时用 | 用途 |
|--------------|----------|--------|------|
| **`cursor-ide-browser` MCP** | 工作区 `mcps/cursor-ide-browser/tools/*.json` | Phase 1–2 全程 | 登录页、业务流、Network、cookie/localStorage（**必用**） |
| **`Task` + `explore`** | Cursor 内置 | 每轮侦察 | 产出 `LOGIN_FLOW.draft.md`、`api-discovery/<domain>.md` |
| **`create-subagent`** | `~/.cursor/skills-cursor/create-subagent/SKILL.md` | 多站点/长期项目 | 创建 `.cursor/agents/api-recon.md`，固定「只用内置浏览器、只写 docs、每轮 ≤2 domain」 |
| **`shell`** | `~/.cursor/skills-cursor/shell/SKILL.md` | browser 定稿后 | `curl`/小脚本对照 endpoint 与 `data/cookies.json`，不用于猜接口 |
| **`create-rule`** | `~/.cursor/skills-cursor/create-rule/SKILL.md` | Phase 2 结束或第二站点起 | `.cursor/rules/` 沉淀：响应字段、失败码表、禁止贴大 JSON 进聊天 |
| **`memory-merger`** | `~/.agents/skills/memory-merger/SKILL.md` | 多站点成熟后 | 把 workspace `*-memory.instructions.md` 合并进站点解析说明 |
| **`canvas`** | `~/.cursor/skills-cursor/canvas/SKILL.md` | 流程复杂时（可选） | 登录/captcha/SSO 时序可视化；结论仍写入 `docs/` |

**`api-recon` 子 agent**：复制模板到项目或用户 agents 目录：

```bash
mkdir -p <project_root>/.cursor/agents
cp ~/.cursor/skills/learning-site-automation/templates/agents/api-recon.md \
   <project_root>/.cursor/agents/api-recon.md
```

安装说明见 `templates/api-recon-agent.md`；也可用 **`create-subagent`** skill 按需微调。

### 5.2 Phase 5 及之后（非 HTTP 解析）

| 外部 skill | 何时 Read | 本 skill 中的用途 |
|------------|-----------|-------------------|
| `spreadsheet` | Phase 5 做 xlsx 模板/导出 | 中文表头、列宽、说明 sheet（`excel-spec.md`） |
| `xlsx-manipulation` | 仅需 openpyxl 细改 cell 时 | 可选，`spreadsheet` 优先 |
| `excel-automation` | 需 Office MCP 复杂宏时 | 一般不需要；HTTP 项目优先 `spreadsheet` |

### 5.3 不建议用于站点解析的 skill

| skill | 原因 |
|-------|------|
| `sdk` | Cursor Agent API/CI，非抓站 |
| `loop` | 轮询运行状态，非一次性侦察 |
| `WebFetch`（工具） | 无法执行登录交互、captcha、XHR；仅适合静态页，**不能**替代 §1.1 |

---

## 6. 父 agent vs 子 agent 分工（修订版）

| 必须父 agent | 可子 agent |
|--------------|------------|
| `AskQuestion` | browser 抓包 → draft md |
| `<pkg>`/`<svc>` 命名 | captcha.py / login.py |
| phase gate 与用户确认 | 单个 `*Service` 模块 |
| 合并 API_REFERENCE | 整页 `index.html` |
| 跑通端到端 smoke test | PyInstaller 打包脚本 |
| 写 handoff + verification report + gaps（如有） | openpyxl 模板生成（在 spreadsheet skill 指导下） |
| 对照 phase DoD / `web-ui-spec` / `excel-spec` 验收子 agent 产出后再合并 | — |

**修订**：Phase 1 Step 2 **可以**派子 agent 做 browser 侦察，但 captcha 族最终判定与 AskQuestion 仍由父 agent 负责。

---

## 7. Anti-patterns（Cursor 特有）

- ❌ 在同一对话里从 Phase 1 扫到 Phase 5  
- ❌ Phase 1–2 不用 **`cursor-ide-browser`**，改用 Playwright/Selenium/让用户手抄 DevTools（除非 §1.1 阻塞并已说明）  
- ❌ 未走内置 browser 就用 `WebFetch` / `curl` **发现**登录或业务 API（对照验证除外）  
- ❌ 子 agent 返回整页 HTML/JSON 样本到聊天（应写文件）  
- ❌ 未写 handoff 就让用户「自己记得」  
- ❌ Phase 5 未读 `web-ui-spec.md` / `excel-spec.md` 就开始写 UI 或 xlsx  
- ❌ 用英文 UI 文案「先跑通再说」  
- ❌ 导出 Excel 重排导入列顺序  
- ❌ Excel 表头用英文或拼音（如 `username`、`status`、`xingming`）  

---

## 8. 验收与缺口闭环（Implementation Assurance）

与 Cursor 内置 skill **不重复**：`babysit` 只管 PR/CI；`create-rule` 只管长期约定。本节只管 **本 workflow 的阶段交付**。

### 8.1 三类文件分工

| 文件 | 用途 | 何时写 |
|------|------|--------|
| `docs/handoffs/PHASE<N>_*.md` | 新对话上下文交接 | phase 结束或 phase 内检查点 |
| `docs/verification/PHASE<N>_REPORT.md` | DoD/spec 逐项 **pass/fail + 证据** | 每次宣布 phase 完成前 |
| `docs/gaps/PHASE<N>_gaps.md` | 做不到 / 暂缓的需求与阻塞证据 | 有 gap 时；无 gap 可不建文件 |

**禁止**在 `verification/` 里再抄一遍完整 checklist（权威清单仍在 `phaseN-*.md`、`web-ui-spec.md` §12–§13、`excel-spec.md` §6）。

### 8.2 `PHASE<N>_REPORT.md` 模板

```markdown
# Phase N Verification Report — <站点>

| # | Source | Item | Result | Evidence |
|---|--------|------|--------|----------|
| 1 | phase1-login-recon.md DoD | docs/LOGIN_FLOW.md | pass | path + section count |
| 2 | phase1-login-recon.md DoD | cli_login 成功 | pass | `python -m <pkg>.cli_login` exit 0 |
| … | … | … | pass/fail/skipped | command / file / manual step |

Open gaps: none | see docs/gaps/PHASE<N>_gaps.md
User accepted scope cuts: none | listed in phase-gate chat
```

Phase 5 额外引用：`web-ui-spec.md` §12–§13、`excel-spec.md` §6 各行填入上表，不得只写「UI 已完成」。

### 8.3 `PHASE<N>_gaps.md` 模板

```markdown
# Phase N Gaps — <站点>

| Requirement | Why blocked | Evidence | Workaround | User decision |
|-------------|-------------|----------|------------|---------------|
| … | SMS 验证码 | browser 截图 / Network | 手动输入或砍 scope | pending / accepted / rejected |
```

有 **pending** 行时：**不得**进入下一阶段，除非用户在 phase gate 里明确接受 scope cut（可与「是否进入 phase N+1」同一条消息确认）。

### 8.4 父 agent 验收子 agent（硬规则）

1. 子 agent 只回传：结论 + 文件路径 + 一条验证命令。  
2. 父 agent **Read 合并后的文件**，按 phase DoD 或 spec § 逐项打 pass/fail。  
3. 子 agent 聊天里说「完成」≠ 验收通过；未写 `PHASE<N>_REPORT.md` 不算 phase 结束。  

Phase 5 子 agent 交付 `index.html` / `excel_io.py` 后，父 agent 必须对照 `web-ui-spec.md` §13 与 `excel-spec.md` §6 填报告，再写 handoff。

### 8.5 与 `create-rule` / CI 的边界

- **Gap（临时）** → `docs/gaps/`；用户确认后的**稳定解析约定** → 可选 `create-rule`（phase 2 后）。  
- **Phase 6 CI** → lint + import smoke only；单实例、二次启动、Excel 列对齐等 **不进 CI**，写在 `PHASE5_REPORT` / `PHASE6_REPORT` 的手动证据里。  
- 用户 babysit PR 时再用 **`babysit` skill**；与本节 phase 验收互不替代。
