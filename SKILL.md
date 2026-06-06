---
name: learning-site-automation
description: Bootstrap a learning-website automation project from a URL plus test credentials. Use when the user wants to build pure-HTTP login tools, course/exam runners, and a multi-account always-on scheduler with web console for any online learning / continuing-education platform (e.g. 双卫网 / 医博士 / 学习强国 / 各类继教平台). Trigger when the user provides a site URL plus a test username/password and asks to "做自动化 / build automation / scrape / 跑课 / 刷课 / 持续学习服务".
---

# Learning Site Automation Bootstrap

A 6-phase workflow that turns "one URL + one test account" into a production-ready, multi-account, always-on automation service. The flow is distilled from the `shuangwei` (双卫网) project but the skeleton is site-agnostic.

## Inputs the User Must Provide

Before starting, confirm you have:

1. **Site URL** (login page, e.g. `https://www.example.com/?from=login`)
2. **Test credentials** (one working username + password)
3. **Domain goal** in one sentence (e.g. "刷视频课 + 自动考试 + 申请学分")
4. **Project root path** (absolute path on disk where the codebase will live)
5. (Optional) A requirements doc; if absent, use `templates/requirements.md` as the baseline.

If any of (1)-(4) is missing, ask the user **once** with `AskQuestion` before invoking phase 1.

## The 6 Phases

| Phase | Purpose | Output | Detail file |
|-------|---------|--------|-------------|
| 1 | Login reconnaissance via browser MCP + captcha probe | `docs/LOGIN_FLOW.md` + working `login.py` | `phase1-login-recon.md` |
| 2 | Confirm capability scope, then wrap business endpoints (course / video / exam / credit-if-present / optional recharge/registration/etc.) | `docs/API_REQUIREMENTS.md`, `<pkg>/course.py`, `study.py`, ... + `API_REFERENCE.md` | `phase2-api-tools.md` |
| 3 | Session reuse, error classification, retry policy | `session_manager.py`, `responses.py`, `captcha_limiter.py` | `phase3-stability.md` |
| 4 | End-to-end single-account runner | `course_runner.py` + `run_course.py` entry | `phase4-end-to-end.md` |
| 5 | Multi-account SQLite scheduler + FastAPI web console | `<svc>/orchestrator.py`, `worker.py`, `apply_worker.py`, `web/app.py` | `phase5-service.md` |
| 6 | One-click start, single-instance (+ reopen WebUI on relaunch), port fallback, single-file build (`{平台}_{MM}_{DD}`, console logs), CI | `start.sh`, `build.sh`, `scripts/build.py`, `.github/workflows/ci.yml` | `phase6-packaging.md` |

## Hard Workflow Rules

1. **Phase gate**: at the end of every phase you MUST stop, summarize what was built, and ask the user to confirm before starting the next phase. Each phase has a "Definition of Done" checklist inside its detail file — read it before announcing completion.
2. **Read the phase file before acting**: each phase has its own `phaseN-*.md` with concrete commands, code patterns, and pitfalls. Read it once at the start of that phase using the `Read` tool with the absolute path shown in the table above.
3. **Do not skip phases** unless the user explicitly says so (e.g. "我只要 API 工具，不要常驻服务" → stop after phase 4).
4. **Preserve site-specific knowledge in code, not in this skill**: every site differs in captcha kind, response shape, anti-bot tricks. The skill is a scaffold, not a copy-paste template.
5. **Never commit the test account**: add `data/`, `.run/`, cookies, and account JSONs to `.gitignore` in phase 1.
6. **Don't try to finish in one shot**: split work across phases + specs. **Read `cursor-agent-playbook.md`** before phase 1 for handoff files, New Chat boundaries, sub-agents, and other skill/MCP usage.
7. **Site profile gate** (phase 2): confirm **`site_profile`** per `site-profiles.md`. **A 型**：画像确认后 → 可选能力 **多选** `AskQuestion` → `templates/api-requirements.md` + `templates/requirements.md`. **B 型**：画像确认后 → 复制 **`templates/api-requirements-b.md`** 与 **`requirements-year-driven.md`**，套用 **§B 型快速路径** 默认跳过项；**不**跑 A 型全量多选，仅在购卡/注册/混合专题时追加窄问。用户目标已写明公需/按年时可推断 B，免画像单选。
8. **Capability scope gate**: mandatory flows are login/session, account info, course/progress, exam **if recon finds it**. **A 型**：credit application if present; optional 学科列表/注册/购卡/其他 由多选决定。**B 型**：固定 skip 学科列表 + 申请学分 + planner/apply_queue/日配额；购卡/注册仅在有触发时写入 Optional Selected。Persist in `docs/API_REQUIREMENTS.md`.
9. **Implementation assurance**: do not announce a phase complete while any DoD item is unchecked or any open gap lacks user acceptance. See **Implementation Assurance** below.

## Implementation Assurance

Close the loop without duplicating existing checklists. **Authoritative sources** stay where they are:

| Scope | Checklist lives in |
|-------|-------------------|
| Phases 1–4, 6 | `phaseN-*.md` → Definition of Done |
| Phase 5 Web UI | `web-ui-spec.md` §12–§13 |
| Phase 5 Excel | `excel-spec.md` §6 |

At **end of every phase**, the parent agent MUST:

1. Walk the authoritative checklist(s) for that phase — do not copy them into a second file.
2. Write `docs/verification/PHASE<N>_REPORT.md`: each item → `pass` / `fail` / `skipped` + one-line evidence (command run, file path, manual step).
3. If anything is **blocked or intentionally deferred**, write `docs/gaps/PHASE<N>_gaps.md` (one row per gap: requirement, evidence, workaround, user decision needed).
4. **Phase gate rule**: enter the next phase only when every DoD item is `pass` or `skipped` with documented reason, **and** every gap is either closed or **explicitly accepted** by the user in the same phase-gate message (does **not** consume an extra `AskQuestion` slot — bundle with the normal “OK to enter phase N+1?”).

**Sub-agent rule**: parent agent integrates output only after re-running DoD against the merged tree; never trust “done” from chat alone.

**Stable conventions vs transient gaps**: confirmed, long-lived site rules → optional **`create-rule`** after phase 2; open blockers → `docs/gaps/` only, not `.cursor/rules/`.

## Cursor Agent Playbook (read before phase 1)

**Full detail:** `cursor-agent-playbook.md`

| When | Action |
|------|--------|
| End of each phase | Write `docs/verification/PHASE<N>_REPORT.md` + `docs/handoffs/PHASE<N>_*.md`; gaps → `docs/gaps/` if any; offer **New Chat** |
| Phase 1 → 2 | Strongly suggest New Chat (browser capture bloat) |
| Phase 2, every 2 domains | Mid-phase handoff + optional New Chat |
| Phase 5 backend → UI | New Chat before generating `index.html` |
| Mid-phase pressure | Read >8 files OR >15 edits OR one file >600 LOC → stop & handoff |

**Phase 1–2 analysis (Cursor 内):** **必须**用 MCP **`cursor-ide-browser`**（Cursor 内置浏览器）做现场解析；可叠 **`Task` explore** 或项目 **`api-recon` subagent**（见 playbook §1.1、§3、§5）。browser 定稿后可 Read **`shell` skill** 做 HTTP 对照。父 agent 合并进 `docs/LOGIN_FLOW.md` / `API_REFERENCE.md`。多站点可选 **`create-rule`** / **`memory-merger`**。

**Phase 4–5 代码生成策略**：优先**复制 `templates/code/` 模板**，对接 API，不从零写。具体对接点见 SKILL.md §Code Templates。Web UI per **`web-ui-spec.md`**（模板为 `templates/code/web/index.html`，替换占位符即可）; Excel per **`excel-spec.md`** + **`spreadsheet` skill**。

Use **`rename_chat`** MCP at phase boundaries: `Phase N · <站点> · <状态>`.

## Context Budget & Sub-agent Strategy

The whole flow is too big for one conversation. Follow `cursor-agent-playbook.md` for handoff file format and New Chat triggers. Summary:

### When to compress / handoff (mandatory checkpoints)

Stop and write `docs/handoffs/PHASE<N>_*.md` at the **end of every phase**. Also stop if you have read >8 files, made >15 edits, one file >600 LOC, or are switching to a new sub-task with its own DoD.

### When to delegate to a sub-agent (recommended split points)

Use `Task` with `subagent_type=generalPurpose` or `explore`. Copy DoD from the phase file into the prompt.

| Boundary | Why delegate | Sub-agent scope |
|---|---|---|
| Phase 1 browser recon | Heavy MCP output | Write `docs/LOGIN_FLOW.draft.md` via `cursor-ide-browser`; no login.py |
| Phase 1 captcha + login | Finicky iteration | Implement `captcha.py` + `login.py` from draft path |
| Phase 2 API discovery | Per-domain network dumps | One explore agent → `docs/api-discovery/<domain>.md` (max 2 domains each) |
| Phase 2 service module | Parallel-friendly | One generalPurpose agent per `*Service` + `cli_*.py` |
| Phase 5 web UI | Pure presentation | 复制 `templates/code/web/index.html` → 替换占位符 → 按 B 型/可选能力删减块；验收 `web-ui-spec.md` §12–§13 |
| Phase 5 service layer | After API confirmed | 复制 `templates/code/service/{store,orchestrator,worker_base,apply_worker,web/app,excel_io}.py` → 实现 `run_pipeline()` → 注入 session_manager |
| Phase 5 Excel | Formatting rules | `excel_io.py` 模板已含导入/导出；仅在有非标列时借 `spreadsheet` skill 调整 |
| Phase 6 packaging | Platform quirks | `start.sh`, `build.sh`, PyInstaller spec |

### What stays in the parent agent

- `AskQuestion`, naming (`<pkg>`/`<svc>`), phase gates, smoke tests, handoff files
- Integrating sub-agent outputs and re-running DoD
- Final captcha-family decision after reviewing recon draft

### Detail preservation under compression

Never drop: endpoint paths, failure codes, captcha family, `<pkg>`/`<svc>` names, daily quotas, user's domain goal. Persist in `docs/LOGIN_FLOW.md`, `<pkg>/API_REFERENCE.md`, `<svc>/config.py`.

## Initial Project Layout (used from phase 1 onward)

```
<project_root>/
├── <pkg>/                     # HTTP toolkit (login, captcha, services, CLIs)
├── <svc>/                     # Always-on service (phase 5+)
│   └── web/app.py + templates/index.html
├── docs/
│   ├── LOGIN_FLOW.md          # produced in phase 1
│   ├── API_REQUIREMENTS.md     # produced at phase 2 start; confirmed capability scope
│   ├── handoffs/              # PHASE<N>_*.md — Cursor context handoffs
│   ├── verification/          # PHASE<N>_REPORT.md — DoD pass/fail evidence (no duplicate checklists)
│   ├── gaps/                  # PHASE<N>_gaps.md — blocked/deferred requirements (if any)
│   ├── api-discovery/         # phase 2 per-domain drafts (optional)
│   └── 通用需求说明.md
├── data/                      # gitignored
├── .run/                      # gitignored
├── run_course.py              # phase 4
├── run_service.py             # phase 5
└── ...
```

Use `scripts/init_project.py` to scaffold. See `phase1-login-recon.md`.

## Canonical Tech Stack (battle-tested, do not deviate without reason)

- Python 3.9+, `requests`, `ddddocr`, `pycryptodome`, `fastapi` + `uvicorn`
- Single inlined **`index.html`** — **简体中文** UI per `web-ui-spec.md`
- `sqlite3` (WAL), `openpyxl` — import/export per **`excel-spec.md`**（中文文件名、Sheet 名与表头字段名）
- `pyinstaller`; optional LLM for subject mapping

## Operator-facing Chinese requirements (fixed)

These apply to every generated project unless the user explicitly opts out:

| Surface | Rule |
|---------|------|
| Web 控制台 | 全部简体中文；见 `web-ui-spec.md` §0 |
| Excel 模板 | 文件名 `{平台}账号模板.xlsx`；Sheet 名与表头字段名**全部中文**；见 `excel-spec.md` §2 |
| Excel 导入 | 只解析中文表头（姓名/账号/密码/学科1…）；错误提示中文；见 `excel-spec.md` §2 |
| Excel 导出 | 前 A–J 列与导入模板完全一致；状态/日志等中文列追加在后；见 `excel-spec.md` §3 |
| 复制日志 | 失败/重试账号一键复制 `error_log_text`；见 `web-ui-spec.md` §4.12 + `excel-spec.md` §4 |
| 启动与打包 | 一键启动、单实例、二次启动只开 WebUI、端口避让、单文件 PyInstaller、`{平台}_{月}_{日}` 命名、`console=True`；见 `phase5-service.md` + `phase6-packaging.md` |

## Captcha Decision Tree (site-specific tweak point)

| Site captcha kind | Detect by | Use |
|-------------------|-----------|-----|
| Click-word / point-touch | `wordList`, `originalImageBase64` | `ddddocr` det + OCR; AES-ECB |
| Slider | `bg`/`tile`, track | `ddddocr.slide_match` |
| Plain char OCR | single captcha `<img>` | `ddddocr.classification` |
| SMS / face / passkey | biometric / SMS gate | **stop and ask the user** |

## When to Call AskQuestion

At most four times across the whole run:

1. Start — missing inputs (1)–(4)
2. End of phase 1 — captcha kind ambiguous
3. Start of phase 2 — confirm `site_profile` (A/B) if not inferable; **A 型** optional API multi-select; **B 型** apply `api-requirements-b.md` defaults (extra ask only for 购卡/注册/混合). Writes `docs/API_REQUIREMENTS.md`.
4. End of phase 4 — continue to phase 5 or stop

Bundling **gap acceptance** or **scope cut** into the normal phase-gate confirmation does **not** count as an extra question.

## Anti-Patterns to Avoid

- Do NOT use Selenium/Playwright at runtime or for recon (in Cursor, use **`cursor-ide-browser` MCP** only for phase 1–2 site parsing; see playbook §1.1)
- Do NOT use WebFetch/curl to *discover* login or API endpoints before built-in browser recon is documented in `docs/`
- Do NOT finish phases 1–5 in one chat without handoff files
- Do NOT paste large browser JSON into chat — write `docs/` files
- Do NOT use English UI labels or English Excel headers / Sheet names / field names
- Do NOT reorder export columns relative to import template
- Do NOT use emoji in UI text; use plain Chinese labels
- Do NOT skip `ui.confirm` / `ui.toast` patterns in web UI
- Do NOT mark a phase complete with unchecked DoD or unaccepted gaps in `docs/gaps/`
- Do NOT duplicate full spec checklists in `docs/verification/` — only pass/fail + evidence
- Do NOT merge sub-agent output without parent re-running DoD on the integrated tree

## Auxiliary Resources In This Skill

- `site-profiles.md` — **A 学科规划型 vs B 公需年度型**（双轨架构、选型、与 liangshangongxu 对照）
- `cursor-agent-playbook.md` — **Cursor orchestration**: built-in browser first (§1.1), handoff, sub-agents, parsing skill combos (§5)
- `web-ui-spec.md` — phase-5 web console 完整规范（中文 UI, 复制日志）
- `excel-spec.md` — 中文模板/导出列对齐, `error_log_text`
- `phase1-login-recon.md` … `phase6-packaging.md` — per-phase detail (read only when entering that phase)
- `templates/requirements.md`, `templates/requirements-year-driven.md`（B 型）, `templates/api-requirements.md`（A 型）, `templates/api-requirements-b.md`（B 型预填，少问）, `templates/account.json`, `templates/project-skeleton.md`
- `templates/agents/api-recon.md` + `templates/api-recon-agent.md`（安装说明；复制前者到 `.cursor/agents/api-recon.md`）
- `scripts/init_project.py`, `scripts/captcha_probe.py`
- **`templates/code/`** — 预写通用代码模板（见下方 §Code Templates）

Read phase files and specs **only when entering that phase/sub-task**. Do not preload everything.

---

## Code Templates — 通用代码直接复制，只对接 API

所有通用层已预写完毕，放在 `templates/code/`。每个网站只需：
1. 复制对应文件到项目包目录
2. 将注释中的 `TODO` / `[OPTIONAL:xxx]` 按站点实际情况填入或删除
3. 实现标注 `@abstractmethod` 的方法（site-specific API 对接）

### 文件清单

```
templates/code/
├── run_service.py                  # 服务启动入口（复制到项目根）
├── service/
│   ├── runtime.py                  # 单实例锁、端口探测、endpoint.json ── 完整通用，直接复制
│   ├── config.py                   # DEFAULT/MAX_CONCURRENCY=400、日配额常量
│   ├── states.py                   # 账号/申请状态机 + UnitState
│   ├── course_planner.py           # A 型 tier 排序、queue_rank、DP/贪心凑学分、学习闸门
│   ├── requirements_resolver.py    # 学科1/2 多形态解析（requirements_text / Excel…）
│   ├── subject_mapper.py           # 逐条 category 映射 → ai_subject_map → 同学科合并
│   ├── course_matcher.py           # 优先级分桶 + 两阶段凑课 + 精确学分 DP
│   ├── llm_subject.py              # qwen3.5-flash 单条学科 LLM 映射（DashScope 兼容）
│   ├── account_pipeline.py         # 完整链路：映射→预匹配→course_results→学习队首
│   ├── session_retry.py            # is_session_expired + relogin 一次重试
│   ├── scheduling.py               # 8:00 错峰 daily_eligible_at ── A 型用，B 型可省
│   ├── store.py                    # SQLite WAL 持久层 + 状态转移校验
│   ├── orchestrator.py             # 调度器 tick ── 完整通用，直接复制
│   ├── worker_base.py              # AccountWorkerBase ── 继承并实现 run_pipeline()
│   ├── apply_worker.py             # ApplyWorkerBase ── [OPTIONAL:申请学分]
│   └── web/
│       ├── app.py                  # FastAPI 路由 ── 替换 <PLATFORM>，注入 store/orch
│       └── excel_io.py             # 导入/导出 ── 按 A/B 型选列
├── web/
│   └── index.html                  # 完整 Web UI（vanilla JS，≤1600 行）── 替换占位符
├── pkg/
│   └── site_adapter_template.py    # SiteAdapter 参考实现（build_plan 已接 account_pipeline）
└── runner/
    ├── course_runner.py            # CourseRunner（A 型）+ YearTaskRunner（B 型）
    └── ...
```

### 每个文件的「对接点」

| 文件 | 你需要做的事 |
|------|------------|
| `config.py` | 复制到 `<svc>/config.py`，改配额与 `SITE_PROFILE` |
| `states.py` | 直接复制；`store` 已接入转移校验 |
| `course_planner.py` | A 型分配/学習闸门用；B 型可不复制 |
| `requirements_resolver.py` | 解析学科1/2+学分；`normalize_requirements()` |
| `subject_mapper.py` | `ensure_subject_mappings` 逐条映射；`merge_requirements_by_mapped_subject` |
| `course_matcher.py` | `match_two_phase` + `pick_courses_with_priority`（DP） |
| `llm_subject.py` | `build_llm_mapper()`；凭证 `templates/ai_config.json` → `.run/ai_config.json` |
| `account_pipeline.py` | 实现 `CoursePoolProvider.gather_pool`；`build_assignment_plan()` |
| `pkg/site_adapter_template.py` | 复制为 `<pkg>/site_adapter.py`，实现拉课表/学科列表 TODO |
| `session_retry.py` | 直接复制；业务 Service 用 `worker.call_with_session_retry()` |
| `runtime.py` | 直接复制，无需修改 |
| `scheduling.py` | **A 型**：复制并在 `config.py` 设日窗；**B 型**：不复制 |
| `store.py` | **A 型**：按可选能力删 `[OPTIONAL]`；**B 型**：删学科列、`apply_queue`、`requirements_json` 学科槽，保留 `target_years_json` |
| `apply_worker.py` | **B 型**：不复制 |
| `orchestrator.py` | 直接复制；`worker_factory` 参数传你的 `AccountWorker` 构造函数 |
| `worker_base.py` | A 型实现 `run_pipeline()`；B 型实现 `run_year_pipeline()`（`run_once` 已内置按年循环） |
| `apply_worker.py` | 继承 `ApplyWorkerBase`，实现 `do_apply_credit(client, project_id, task)` |
| `web/app.py` | 替换 `PLATFORM`/`LOGO_LETTER`；`run_service.py` 中注入 `app.state.store/orch/excel_io` |
| `web/excel_io.py` | A 型保持默认；B 型将 `IMPORT_COLS` 替换为 `B_IMPORT_COLS` |
| `web/index.html` | 替换 `{{ PLATFORM }}`/`{{ LOGO_LETTER }}`；B 型替换添加面板（§14）；删除 `[OPTIONAL]` 块 |
| `runner/course_runner.py` | 调整 `WATCH_THRESHOLD`、`PROBE_STEP`/`PROBE_INTERVAL`、字段名、`_watch_lesson` 参数名；实现 `probe_progress`；B 型用 `YearTaskRunner` |
| `run_service.py` | 替换 `<SVC>`/`<PKG>`；传入真实 `session_manager` |

### 使用规则

1. **先复制，再对接**：在 phase 4/5 开始时，先把对应模板复制到项目，再填 TODO，不要从头写。
2. **`[OPTIONAL:xxx]` 注释**：站点不需要某功能时，整段删除（含开始/结束注释行）；保留的功能只需取消注释或保持原样。
3. **`index.html` 的 B 型改造**：如果 `site_profile=B`，把添加表单替换为 `web-ui-spec.md §14` 的年度 pill 版本；其余组件（stats、table、drawer、toast 等）保持不变。
4. **web-ui-spec.md 仍是权威**：模板是规范的实现。如果两者冲突，以规范为准，修模板。
5. **不要把对接代码写进模板文件**：site-specific 代码（API 端点、字段名、错误码）只在子类/caller 中，不要反向修改 `templates/code/` 里的文件。
