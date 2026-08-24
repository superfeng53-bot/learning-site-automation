---
name: learning-site-automation
description: >-
  Bootstrap a learning-website automation project from a URL plus test credentials
  using Goal mode: the parent only manages CreateGoal, gates, and AskQuestion;
  one sub-agent completes each of phases 1–5 (HTTP login, APIs, session, runner,
  always-on Chinese web console). Packaging is a separate host-agnostic agent.
  Use when the user provides a site URL plus a test username/password and asks
  to 做自动化 / build automation / scrape / 跑课 / 刷课 / 持续学习服务
  (双卫网 / 医博士 / 学习强国 / 继教平台).
---

# Learning Site Automation — Goal Mode (Phases 1–5)

Turns one login URL + one test account into a multi-account always-on HTTP service with a 简体中文 web console. Distilled from 双卫网; site-agnostic.

**This Cursor skill stops after Phase 5.** PyInstaller / `start.sh` / `smoke_frozen.py` run later on **each target OS**, by the host-agnostic packaging agent (`templates/agents/packaging.md`). Do not fold packaging into this Goal.

## Goal Mode — Parent Is Manager Only

The parent conversation **must stay one session**. Do **not** ask the user to open a New Chat. Context isolation = one `Task` sub-agent per phase.

### Parent loop

1. Collect inputs (below). If (1)–(4) missing, **one** `AskQuestion` (always include credential input mode).
2. Name `<pkg>` / `<svc>`, run `scripts/init_project.py`, `move_agent_to_root` into the **new project**.
3. `CreateGoal` with objective covering Phases 1–5 only. Example: `为 <平台> 做到 Phase 5：纯 HTTP 登录、业务 API、会话稳定、单账号 runner、多账号常驻服务+中文控制台。打包不在本 Goal。`
4. For `N = 1 … 5`:
   - Before Phase 2: confirm `site_profile` if not inferable (AskQuestion slot 3).
   - `Task` `generalPurpose`: paste `$SKILL_ROOT/templates/agents/phase-worker.md` + this phase’s paths. **One Task = one phase.** The worker may nest more Tasks internally.
   - Re-read `docs/verification/PHASE<N>_REPORT.md` and the DoD in `phaseN-*.md`. Chat “done” ≠ pass.
   - Phase gate: summarize + ask to continue. Bundle gap acceptance here (does not use an extra AskQuestion slot).
   - Before Phase 5: AskQuestion slot 4 (continue or stop after the runner).
5. Phase 5 pass → copy packaging files into the project (see **After Phase 5**), then `UpdateGoal` `complete`.
6. Tell the user to run `docs/packaging/AGENT.md` on each OS they need a binary for.

`UpdateGoal` `complete` only when Phase 5 DoD is pass/skipped-with-reason **or** the user accepted stopping after Phase 4. Never mark complete because “workers were launched”.

Parent **does not**: implement `login.py` / `*Service` / UI / Excel; run PyInstaller; paste browser dumps into chat.

Parent **does**: AskQuestion, naming, init, CreateGoal/UpdateGoal, launch/resume the phase Task, re-score DoD, phase gates, copy packaging handoff.

Full manager rules: `cursor-agent-playbook.md`.

## Inputs the User Must Provide

1. **Site URL** (login page)
2. **Test credentials** (one working username + password)
3. **Domain goal** in one sentence (e.g. "刷视频课 + 自动考试 + 申请学分")
4. **Project root path** (absolute)
5. **Credential input mode** — `split` or `combined`. Confirm at project create (batch ops often `combined`). Write `data/account.json` `credential_input_mode`; Phase 5 copies to `CREDENTIAL_INPUT_MODE` / Web UI. Not a runtime toggle — restart after change.
6. (Optional) A requirements doc; else baseline templates in Phase 2.

## The 5 Phases (this Goal)

| Phase | Purpose | Output | Detail file |
|-------|---------|--------|-------------|
| 1 | Login recon (MCP if it works, else curl/JS) + captcha + `login.py` | `docs/LOGIN_FLOW.md` + working login | `phase1-login-recon.md` |
| 2 | `site_profile` + wrap business APIs | `docs/API_REQUIREMENTS.md`, `<pkg>/*.py`, `API_REFERENCE.md` | `phase2-api-tools.md` |
| 3 | Session reuse, errors, retry | `session_manager.py`, `responses.py`, `captcha_limiter.py` | `phase3-stability.md` |
| 4 | Single-account runner | `course_runner.py` / year|project runner + `run_course.py` | `phase4-end-to-end.md` |
| 5 | Multi-account SQLite scheduler + FastAPI console | `<svc>/` + `web/app.py` + `index.html` | `phase5-service.md` |

Packaging spec (not in this Goal): `phase6-packaging.md` → copied to `docs/packaging/SPEC.md`. Agent prompt: `templates/agents/packaging.md`.

## Hard Workflow Rules

1. **Phase gate**: stop, summarize, user confirms before the next phase Task. DoD lives in the phase file — walk it before announcing pass.
2. **Worker reads the phase file**; parent does not preload every spec. Parent reads reports + DoD items that failed.
3. **Do not skip phases** unless the user says so (e.g. stop after Phase 4).
4. **Site-specific knowledge in the project**, not in this skill.
5. **Never commit the test account**: gitignore `data/`, `.run/`, cookies, account JSON in Phase 1.
6. **One session, five workers.** Read `cursor-agent-playbook.md` before Phase 1. **Never** suggest New Chat.
7. **Site profile gate** (Phase 2, parent if needed): `site-profiles.md` A / B / B′. A → optional-capability multi-select + `templates/api-requirements.md`. B → `api-requirements-b.md` + `requirements-year-driven.md`. B′ → `api-requirements-b-prime.md` + `requirements-project-driven.md` and **must** implement `course_plan.py`. B/B′ skip A’s full multi-select; 购卡/注册 only if triggered.
8. **Capability scope**: login/session, account info, course/progress; exam if recon finds it. A: credit if present; optional 学科/注册/购卡 by multi-select. B: skip 学科列表 + 申请学分 + planner/apply_queue/日配额. B′: same as B, skip `yearly_learning`/`target_years`, must have `course_plan`. Persist in `docs/API_REQUIREMENTS.md`.
9. **Implementation assurance**: no phase pass with unchecked DoD or unaccepted gaps.

## Implementation Assurance

| Scope | Checklist lives in |
|-------|-------------------|
| Phases 1–4 | `phaseN-*.md` → Definition of Done |
| Phase 5 Web UI | `web-ui-spec.md` §12–§13、§16 |
| Phase 5 Excel | `excel-spec.md` §6 |
| Packaging (later, other host) | `phase6-packaging.md` / `docs/packaging/SPEC.md` |

Each phase worker writes `PHASE<N>_REPORT.md` and gaps. Parent re-scores the merged tree. Enter N+1 only when every item is `pass` or `skipped` with reason, and every gap is closed or **accepted in the same gate message**.

Stable site rules after Phase 2 → optional `create-rule`. Open blockers → `docs/gaps/` only.

## After Phase 5 (parent)

Copy into the project so **any** agent on **any** OS can package without this skill:

```bash
mkdir -p "$PROJECT_ROOT/docs/packaging"
cp "$SKILL_ROOT/templates/agents/packaging.md" "$PROJECT_ROOT/docs/packaging/AGENT.md"
cp "$SKILL_ROOT/phase6-packaging.md" "$PROJECT_ROOT/docs/packaging/SPEC.md"
cp "$SKILL_ROOT/templates/packaging-handoff.md" "$PROJECT_ROOT/docs/handoffs/PACKAGING.md"
# fill PACKAGING.md placeholders: 站点, pkg, svc, 平台中文名, site_profile, captcha
```

Then stop. Do not run `build.sh` in this Goal.

## When to Call AskQuestion

At most four times in this Goal:

1. Start — missing inputs (1)–(4) + credential mode
2. End of Phase 1 — captcha kind ambiguous (`blocked: need_user` from the worker)
3. Start of Phase 2 — `site_profile` if not inferable; A optional APIs; B/B′ extra ask only for 购卡/注册/混合
4. End of Phase 4 — continue to Phase 5 or stop

Gap acceptance bundled into the phase gate does **not** count as an extra question.

## Captcha Decision Tree

| Site captcha kind | Detect by | Use |
|-------------------|-----------|-----|
| Click-word / point-touch | `wordList`, `originalImageBase64` | `ddddocr` det + OCR; AES-ECB |
| Slider | `bg`/`tile`, track | `ddddocr.slide_match` |
| Plain char OCR | single captcha `<img>` | `ddddocr.classification` |
| SMS / face / passkey | biometric / SMS gate | **stop; parent AskQuestion** |

## Canonical Tech Stack

- Python 3.9+, `requests`, `ddddocr`, `pycryptodome`, `fastapi` + `uvicorn`
- Single inlined **`index.html`** — 简体中文 per `web-ui-spec.md`
- `sqlite3` (WAL), `openpyxl` per `excel-spec.md`
- Packaging later: `pyinstaller`; optional LLM for subject mapping

## Operator-facing Chinese requirements (fixed)

| Surface | Rule |
|---------|------|
| Web 控制台 | 全部简体中文；`web-ui-spec.md` §0 |
| Excel 模板 | `{平台}账号模板.xlsx`；Sheet/表头全中文；`excel-spec.md` §2 |
| Excel 导入 | 只解析中文表头；`combined` 含「账号密码」；`excel-spec.md` §2 |
| Excel 导出 | 前 A–J 与导入模板一致；状态/日志中文列在后；`excel-spec.md` §3 |
| 复制日志 | 失败/重试账号复制 `error_log_text`；`web-ui-spec.md` §4.12 |
| 开发态启动 | 单实例、二次启动只开 WebUI、端口避让 — Phase 5 `run_service.py` |
| 打包交付 | 一键 `start.sh`、单文件 PyInstaller、`{平台}_{月}_{日}`、`console=True` — **packaging agent** |

## Initial Project Layout

```
<project_root>/
├── <pkg>/
├── <svc>/web/app.py + templates/index.html
├── docs/
│   ├── LOGIN_FLOW.md
│   ├── API_REQUIREMENTS.md
│   ├── handoffs/          # worker → next worker (not New Chat)
│   ├── verification/
│   ├── gaps/
│   ├── packaging/         # AGENT.md + SPEC.md after Phase 5
│   └── 通用需求说明.md
├── data/                  # gitignored
├── .run/                  # gitignored
├── run_course.py
└── run_service.py
```

`scripts/init_project.py` scaffolds. See `phase1-login-recon.md`.

## Anti-Patterns

- Do NOT implement phase work in the parent; Do NOT suggest New Chat
- Do NOT start packaging / PyInstaller / `smoke_frozen.py` in this Goal
- Do NOT use Selenium/Playwright at runtime or as default recon (playbook §1.1)
- Do NOT stall Phase 1–2 on MCP `Server not found` — fall through to curl/JS
- Do NOT treat workbench `open_resource` as controllable recon
- Do NOT paste large browser JSON into chat — write `docs/`
- Do NOT use English UI / Excel headers / Sheet names
- Do NOT reorder export columns relative to the import template
- Do NOT use emoji in UI text
- Do NOT skip `ui.confirm` / `ui.toast`
- Do NOT ship `index.html` with `#tableWrap` left at `opacity:0`, IIFE handlers not on `window`, or `thead { top: var(--header-h) }` + `border-collapse: collapse` (see `web-ui-spec.md` §6.7、§8.15–§8.16). `Object.assign(window, …)` must include `submitAddForm`, `dragOver`/`dragLeave`/`dropFile`
- Do NOT generate combined Excel samples in both「账号密码」and split 账号/密码 columns (`excel-spec.md` §2)
- Do NOT mark a phase complete with unchecked DoD or unaccepted gaps
- Do NOT duplicate full spec checklists in `docs/verification/`
- Do NOT merge a worker’s “done” without parent re-scoring DoD
- Do NOT assume `credential_input_mode` is missing because the UI shows two fields — default is `split` until `data/account.json` is `combined` and the service restarts
- Do NOT update B/B′ **年度学时** from local play seconds only (`progress-sync.md`)
- Do NOT write hour-level `learning_progress.percent` as drawer/list **总进度**
- Do NOT treat `extra.progress_percent === 0` as final in Web UI
- Do NOT mark B-type year task failed when courses are 100% and `auditStatus>=0` but `publicNum` is 0 — `_resolve_year_completion`
- Do NOT hardcode video `step`/`interval` without Phase 2 recon (`phase2-api-tools.md` § Video Progress)

## Auxiliary Resources

- `cursor-agent-playbook.md` — Goal manager, net ladder, worker prompts, assurance
- `templates/agents/phase-worker.md` — Phase 1–5 worker contract
- `templates/agents/packaging.md` — host-agnostic packaging agent
- `templates/packaging-handoff.md` → `docs/handoffs/PACKAGING.md`
- `site-profiles.md`, `web-ui-spec.md`, `excel-spec.md`, `progress-sync.md`
- `phase1-login-recon.md` … `phase5-service.md`; packaging spec `phase6-packaging.md`
- `templates/agents/api-recon.md` — nested recon inside Phase 1–2 workers
- `scripts/init_project.py`, `scripts/captcha_probe.py`
- `templates/code/` — copy then wire APIs (Phase 4–5 workers)

Read phase files **only when that phase’s worker starts**. Parent: do not preload Code Templates.

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
│   ├── runtime.py                  # 单实例锁、端口探测、endpoint.json ── 直接复制
│   ├── config.py                   # DEFAULT/MAX_CONCURRENCY=400、日配额常量
│   ├── states.py                   # 账号/申请状态机 + UnitState
│   ├── course_planner.py           # A 型 tier 排序、queue_rank、DP/贪心凑学分
│   ├── requirements_resolver.py
│   ├── subject_mapper.py
│   ├── course_matcher.py
│   ├── llm_subject.py
│   ├── account_pipeline.py
│   ├── session_retry.py
│   ├── scheduling.py               # A 型用，B 型可省
│   ├── store.py
│   ├── orchestrator.py
│   ├── worker_base.py
│   ├── apply_worker.py             # [OPTIONAL:申请学分]
│   └── web/
│       ├── app.py
│       └── excel_io.py
├── web/index.html
├── pkg/
│   ├── site_adapter_template.py
│   ├── progress_snapshot_template.py
│   ├── year_task_template.py
│   └── client_ssl_snippet.md
├── api/course_plan.py              # B′
├── runner/
│   ├── course_runner.py
│   └── project_runner.py
└── scripts/smoke_frozen.py         # packaging agent 复制；本 Goal 不跑
```

B 型 Phase 5 另复制：`service/worker_b_template.py` → `<svc>/worker.py`（`progress-sync.md`）。
B′ 型 Phase 5 另复制：`service/project_sync.py`。

### 每个文件的「对接点」

| 文件 | 你需要做的事 |
|------|------------|
| `config.py` | 复制到 `<svc>/config.py`，改配额与 `SITE_PROFILE` |
| `states.py` | 直接复制；`store` 已接入转移校验 |
| `course_planner.py` | A 型分配/学习闸门用；B 型可不复制 |
| `requirements_resolver.py` | 解析学科1/2+学分；`normalize_requirements()` |
| `subject_mapper.py` | `ensure_subject_mappings` 逐条映射；`merge_requirements_by_mapped_subject` |
| `course_matcher.py` | `match_two_phase` + `pick_courses_with_priority`（DP） |
| `llm_subject.py` | `build_llm_mapper()`；凭证 `templates/ai_config.json` → `.run/ai_config.json` |
| `account_pipeline.py` | 实现 `CoursePoolProvider.gather_pool`；`build_assignment_plan()` |
| `pkg/site_adapter_template.py` | 复制为 `<pkg>/site_adapter.py`，实现拉课表/学科列表 TODO |
| `pkg/progress_snapshot_template.py` | **B/B′**：复制为 `<pkg>/progress_snapshot.py`（`progress-sync.md`） |
| `pkg/year_task_template.py` | **B 型**：复制为 `<pkg>/year_task.py`；`_resolve_year_completion` |
| `pkg/client_ssl_snippet.md` | Phase 1/3：`SSL_VERIFY` + `session.verify` |
| `session_retry.py` | 直接复制；业务 Service 用 `worker.call_with_session_retry()` |
| `runtime.py` | 直接复制 |
| `scheduling.py` | **A 型**复制；**B 型**不复制 |
| `store.py` | **A 型**删 `[OPTIONAL]`；**B 型**删学科列、`apply_queue`、学科槽，保留 `target_years_json` |
| `apply_worker.py` | **B 型**不复制；A 型实现 `do_apply_credit` |
| `orchestrator.py` | 直接复制；传入 `AccountWorker` 工厂 |
| `worker_base.py` | A：`run_pipeline()`；B：`run_year_pipeline()` |
| `worker_b_template.py` | **B 型** → `<svc>/worker.py`，替换 `<PKG>` |
| `web/app.py` | 替换 `PLATFORM`/`LOGO_LETTER`；注入 store/orch/excel_io |
| `web/excel_io.py` | A 默认；B → `B_IMPORT_COLS`；B′ → `B_PRIME_IMPORT_COLS` |
| `web/index.html` | 替换 `{{ PLATFORM }}`/`{{ LOGO_LETTER }}`；B/B′ 按 spec §14/§15 |
| `api/course_plan.py` | **B′ 型**对接 `FIELD_*` 与 `CourseService` |
| `runner/course_runner.py` | A：`CourseRunner`；**B 型**：`YearTaskRunner` |
| `runner/project_runner.py` | **B′ 型** → `<pkg>/project_task.py` |
| `service/project_sync.py` | **B′ 型**：`build_project_status()` + sync-projects API |
| `run_service.py` | 替换 `<SVC>`/`<PKG>`；真实 `session_manager`；frozen `except`+`input()` 由 **packaging agent** 补齐若 Phase 5 未写 |
| `scripts/smoke_frozen.py` | **packaging agent**：复制到 `scripts/`；`build.py` 成功后 `check_call` |

### 使用规则

1. **先复制，再对接**：Phase 4/5 **工人**先复制模板再填 TODO。
2. **`[OPTIONAL:xxx]`**：不需要则整段删除（含注释行）。
3. **`index.html` 画像**：B → spec §14；B_prime → §15；A 保持学科表单。共用分页、抽屉、复制日志、§6.7 列表滚动。
4. **web-ui-spec.md 仍是权威**；冲突时改生成物，不反向改 `templates/code/` 里的对接代码。
5. **不要把站点 API 写进 skill 模板。**
