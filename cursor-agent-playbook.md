# Cursor Agent Playbook — Goal Mode

本文件教 **父 agent（Goal 管理器）** 如何在 **同一会话** 里跑完 Phase 1–5：只管理、不实现。工人契约见 `templates/agents/phase-worker.md`。打包见 `templates/agents/packaging.md`（**不是**本 Goal）。

**禁止**要求用户 New Chat。抓包体积大 → 工人隔离 + `docs/` 落盘，不是新对话。

`$SKILL_ROOT` = 本 skill 目录（通常 `~/.cursor/skills/learning-site-automation`）。

---

## 1. 父 agent vs 阶段工人

| 必须父 agent | 必须阶段工人（`Task` generalPurpose） |
|--------------|--------------------------------------|
| 缺输入时 `AskQuestion` | Phase 1–5 的侦察、编码、自测 |
| `<pkg>` / `<svc>` 命名 + `init_project.py` | 写 `LOGIN_FLOW.md` / `*Service` / runner / Web UI |
| `CreateGoal` / `UpdateGoal` | 写 `PHASE<N>_REPORT.md` 与 `docs/handoffs/PHASE<N>_*.md` |
| 每个 Phase **一个** `Task`；失败则 **resume 同一阶段** | 阶段内可再嵌套 `Task`（domain 侦察、`index.html`） |
| 对照 DoD **重跑验收**（不信聊天里的「完成」） | 回复只给：结论 + 路径 + 一条验证命令 |
| Phase gate / 缺口接受 | `blocked: need_user` 时停，把问题交回父 agent |
| Phase 5 后复制 `docs/packaging/` | **禁止** PyInstaller / `build.sh` / `smoke_frozen.py` |

父 agent **禁止**：打开 `login.py` 大改、手写 `index.html`、在聊天里复述 HAR。

---

## 2. Goal 工具

输入齐、项目已 `init` 并 `move_agent_to_root` 到业务仓库之后：

1. `CreateGoal` — objective 只写到 Phase 5，点名「打包不在本 Goal」。
2. 每个阶段工人跑完且报告 `pass`、用户 gate 通过 → 继续下一 `Task`。Goal 保持 `active`。
3. Phase 5 验收通过并写好 `docs/packaging/` + `docs/handoffs/PACKAGING.md` → `UpdateGoal` `complete`。
4. 用户在 Phase 4 gate 选择停 → 也可 `complete`（范围已收缩）。

不要为「正在想」创建 Goal；本 skill 明确要求创建。

---

## 3. 派一个阶段工人（复制改写）

```
你是 learning-site-automation 的 Phase <N> 工人。
严格遵守：<SKILL_ROOT>/templates/agents/phase-worker.md

SKILL_ROOT: <abs>
PROJECT_ROOT: <abs>
PHASE: <N>
上一阶段 handoff: <path or 无>
<pkg> / <svc>: …
登录 URL: …
凭证: data/account.json（勿复述密码）
用户刚确认的决定（若有）: …

先 Read 该 PHASE 的 phase 文件 DoD，做完全部工作，写 REPORT + handoff。
禁止 New Chat、禁止开始下一阶段、禁止打包。
回复只按 phase-worker.md 五项。
```

`subagent_type=generalPurpose`。Phase 1–2 侦察若 MCP 可用，工人自己走 §4；MCP 不通则 curl/JS，**禁止**为 MCP 空转。

同一阶段未 `pass`：把 `PHASE<N>_gaps.md` 和失败证据贴进 **resume** prompt，不要新开 Phase N+1。

---

## 4. 站点解析梯子（工人用；即原 §1.1。MCP 不是硬前提）

用户口径：不一定要用 MCP，用内置上网做完侦察即可。

1. **`cursor-ide-browser` MCP** — 仅当 `browser_navigate` / `snapshot` **实际成功**。
2. **HTTP**：`WebFetch`、`curl`、`python requests` 拉登录页/SSO/JS，对照真实 XHR。
3. 用户 HAR — 仅当 1 和 2 都拿不到登录页。

立刻改走第 2 档：`Server not found: cursor-ide-browser`、auth 后仍不可调用、WebFetch 超时但 curl 能拉到、workbench `open_resource`（只能给用户看，不能当侦察）。

仍禁止：Playwright/Selenium 进 `<pkg>/` runtime；未打真实站点就写 endpoint。

嵌套侦察可 `@` 或 `Task` 遵守 `templates/agents/api-recon.md`（只写 `docs/`，不写 `login.py`）。安装：

```bash
mkdir -p <project_root>/.cursor/agents
cp "$SKILL_ROOT/templates/agents/api-recon.md" \
   <project_root>/.cursor/agents/api-recon.md
```

---

## 5. Handoff（工人 → 下一工人，不是新对话）

每个 **phase 结束**写入 `docs/handoffs/PHASE<N>_<slug>.md`。八段，每段 1–5 行，禁止大段代码：

```markdown
# Phase N Handoff — <站点中文名>

## 已完成
## 关键路径（绝对路径）
## 站点决策（不可丢）
- captcha 族 / site_profile / <pkg> / <svc> / 配额 / credential_input_mode
## 已验证命令
## 验收摘要
- 报告：`docs/verification/PHASE<N>_REPORT.md`
- 缺口：`docs/gaps/PHASE<N>_gaps.md` 或「无」
## 未完成 / 下阶段工人第一件事
## 给下一阶段工人的输入要点
（路径、cookie 文件、API_REQUIREMENTS 里已确认 domain）
## 不要做
- 不要 New Chat；不要开始 Phase N+1 以外的工作；不要打包
```

父 agent 把该文件路径放进 **下一个** `Task` prompt。聊天里只说「已写入 handoff，接着派 Phase N+1」，**不要**让用户复制启动语去新对话。

Phase 2 每完成 2 个 domain：可写 mid-handoff 供 **同一 Phase 2 工人**（或其对内嵌套 Task）接着用，仍不新开 chat。

---

## 6. 阶段内嵌套（仍算同一个 Phase Task）

**Phase 1**：工人可先写 `LOGIN_FLOW.draft.md` 再实现 `captcha.py`/`login.py`；captcha 族最终若 ambiguous → `blocked: need_user`，父 AskQuestion 后 resume Phase 1。

**Phase 2**：父 agent 若已写好 `docs/API_REQUIREMENTS.md` 再派工人。工人对每个 confirmed domain：侦察 `docs/api-discovery/<domain>.md` → `*Service` + `cli_*.py`。一次嵌套侦察最多 1–2 个 domain。未确认的 optional 不要做。

**Phase 5**：可并行嵌套 store/worker 与 `index.html`；Excel 按 `excel-spec.md`（需要时工人 Read `spreadsheet` skill）。父 agent 只验收合并树（spec §12–§13、§16 与 Excel §6）。

外部 skill：先 Read 其 `SKILL.md`。`create-rule` / `memory-merger` 仍由 **父 agent** 在 Phase 2 后可选调用。

---

## 7. 验收文件

| 文件 | 用途 |
|------|------|
| `docs/handoffs/PHASE<N>_*.md` | 下一阶段工人输入 |
| `docs/verification/PHASE<N>_REPORT.md` | DoD 逐项 pass/fail + 证据 |
| `docs/gaps/PHASE<N>_gaps.md` | 阻塞；无 gap 可不建 |

禁止在 `verification/` 抄完整 checklist。权威清单：`phaseN-*.md`、`web-ui-spec.md`、`excel-spec.md`。

### REPORT 模板

```markdown
# Phase N Verification Report — <站点>

| # | Source | Item | Result | Evidence |
|---|--------|------|--------|----------|
| 1 | phaseN-….md DoD | … | pass | command / path |
```

Open gaps: none | see `docs/gaps/PHASE<N>_gaps.md`

### 父 agent 验收硬规则

1. 工人只回五项摘要。
2. 父 agent **Read** 报告和关键产物，按 DoD 打分。
3. 未写 `PHASE<N>_REPORT.md` 不算阶段结束。
4. Phase 5：必须对照 web-ui-spec §13 与 excel-spec §6。

Gap 临时 → `docs/gaps/`。用户确认的长期解析约定 → 可选 `create-rule`。CI/打包不在本 Goal。

---

## 8. After Phase 5 — 打包离开本平台

本 Cursor Goal **不做** Phase 6。父 agent：

1. 复制 `templates/agents/packaging.md` → `docs/packaging/AGENT.md`
2. 复制 `phase6-packaging.md` → `docs/packaging/SPEC.md`
3. 填 `templates/packaging-handoff.md` → `docs/handoffs/PACKAGING.md`
4. `UpdateGoal` complete
5. 告诉用户：在 Windows / macOS 等目标机上，用 **任意** 编码 Agent 打开本仓库并执行 `docs/packaging/AGENT.md`

旧 playbook 里 Cursor 专有的打包写法（New Chat 再跑 PyInstaller、父 agent 亲自 smoke、babysit PR、MCP、`rename_chat`）**不要**带进打包。产品规则已写在 packaging agent：`console=True`、onefile、`smoke_frozen.py` 硬闸、frozen `project_root()`、dev 通过 ≠ 冻结通过。

---

## 9. Anti-patterns

- ❌ 父 agent 自己写业务代码或 UI
- ❌ 建议 New Chat / 把 handoff 当「新对话启动语」
- ❌ 一个 Task 做完 Phase 1–5
- ❌ 本 Goal 内 `build.sh` / PyInstaller / `smoke_frozen.py`
- ❌ MCP 不通后反复 auth，不改 curl/JS
- ❌ Playwright 当默认侦察或写进 runtime
- ❌ 未打真实站点就编造 API
- ❌ 工人把整页 HTML/JSON 回传到聊天
- ❌ 未写 REPORT 就 gate 通过
- ❌ Phase 5 未读 web-ui-spec / excel-spec
- ❌ 英文 UI / 英文 Excel 表头
- ❌ 导出重排导入列
- ❌ 用 venv 绿代替未来的打包 smoke（那是 packaging agent 的闸，本 Goal 不要假装已出包）
