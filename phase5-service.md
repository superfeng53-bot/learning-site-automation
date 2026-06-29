# Phase 5 — Multi-Account Always-On Service

Goal: turn the single-account runner into a long-running scheduler that drives many accounts in parallel, persists state across crashes, and exposes a web console for operators. This phase is **highly generic** — most of the design carries over from site to site. The worker-internal pipeline and optional queues/actions must follow the confirmed capability scope in `docs/API_REQUIREMENTS.md`.

## Definition of Done

- [ ] `<svc>/persistence/store.py` with SQLite (WAL) schema for `accounts / runs / kv`, plus `ai_subject_cache` when LLM subject mapping is enabled, plus optional tables from `docs/API_REQUIREMENTS.md` such as `apply_queue / credit_applications`
- [ ] `<svc>/worker.py` `AccountWorker.run_once(account)` runs the full single-account pipeline
- [ ] **B 型**：`worker.py` 实现课节进度同步（`learning_progress` + 课节完成刷 `year_status`）；见 `progress-sync.md` 与 `worker_b_template.py`
- [ ] If credit application is in scope per `docs/API_REQUIREMENTS.md`, `<svc>/apply_worker.py` `ApplyWorker.process_one(now)` consumes the apply queue independently; otherwise no apply worker is generated
- [ ] **A 型**：`<svc>/scheduling.py` implements stable per-account **8:00 daily-window spread** (`daily_eligible_at`); all day-bound deferrals use it (learning + apply). **B 型（公需无单日限制）**：可省略 `scheduling.py` 及 Worker 内「今日学满 N 门 → 明日」逻辑（见 `requirements-year-driven.md` §4.3）
- [ ] `<svc>/orchestrator.py` ticks every N seconds, claims queued accounts under a concurrency limit
- [ ] `<svc>/web/app.py` FastAPI serves the console + `/api/*` endpoints matching `web-ui-spec.md` §8 and `excel-spec.md`
- [ ] `<svc>/web/templates/index.html` generated strictly per `web-ui-spec.md` (简体中文, 复制日志, single file, ≤ 1600 LOC)
- [ ] `<svc>/web/excel_io.py` (or equivalent) implements import/export per `excel-spec.md`（中文文件名/Sheet 名/表头字段名，导出列对齐）
- [ ] All items in `web-ui-spec.md` §12–§13 and `excel-spec.md` §6 verification checklists pass
- [ ] `run_service.py` at project root: single-instance lock + **二次启动只打开已有 WebUI** + port avoidance + auto-open browser
- [ ] `<svc>/runtime.py` writes `.run/service/endpoint.json` while running; second process reads it and exits after `webbrowser.open`
- [ ] Crash recovery: restarting the service requeues `running` accounts and, when present, `in_flight` async tasks

## Read First

Read `docs/API_REQUIREMENTS.md` first (note **`site_profile`** in `site-profiles.md`). Phase 2 应已写好该文件：**B 型**来自 `templates/api-requirements-b.md`，含默认 Explicit Skips。Then read the user-provided requirements doc if any. If `docs/通用需求说明.md` is missing:

- **A — 学科规划型**：copy `templates/requirements.md` → `docs/通用需求说明.md`
- **B — 公需年度型**：copy `templates/requirements-year-driven.md` → `docs/通用需求说明.md`

Adapt placeholders (`<PLATFORM>`, `<DOMAIN>`, captcha kind, quotas, selected optional capabilities) to the actual site. **B 型**：跳过 `scheduling.py`、`apply_worker.py`、`apply_queue` 表与 `waiting_apply`（见 `site-profiles.md` §B 型快速路径）。

Capability-dependent rules:

- If credit application is in scope, include `apply_queue`, `credit_applications`, `ApplyWorker`, waiting-apply states, and credit UI/API surfaces.
- If the site has no credit-application flow, omit `apply_queue` and `credit_applications` unless another selected flow needs an async queue; `waiting_apply` should not be a reachable account state.
- If `购卡 / 充值` is selected, include card fields and `/api/accounts/{id}/recharge`; otherwise keep card columns only if the user still needs them for import compatibility.
- If `注册` is selected, add registration service/API actions separately from account import; do not assume every imported account should be auto-registered.
- If `学科列表 / 分类列表` is not selected and the site does not need subject requirements, simplify `requirements_json` and UI fields to the confirmed requirement model.

### Site profile B — 公需年度型 Worker

When `site_profile: B`:

- Store **`target_years_json`** on `accounts` (TEXT JSON array); omit or leave empty `requirements_json`.
- `AccountWorker.run_once`: session → **`for year in ordered_target_years(account): run_year_task(...)`** — no `course_planner`, no `ApplyWorker`.
- `extra_json` must track `year_status`, `learning_progress`, `progress_percent`, `current_year`, `report_mode`, `phase` (see `templates/requirements-year-driven.md` and **`progress-sync.md`**).
- **Progress sync (B)**：Worker 在课节开始/学习中写 `learning_progress`；**课节开始 + 每个课节完成**调用 `<pkg>/progress_snapshot.build_year_progress` 刷新 `year_status` + `progress_percent`（展示进度在已获得学时为 0 时回退课程学习进度，见 `progress-sync.md` §两套进度指标）。复制 `worker_b_template.py` → `<svc>/worker.py`。
- Web UI + Excel per `web-ui-spec.md` §14 and `excel-spec.md` §2B.
- **`FAST_REPORT_SUPPORTED`**（来自 Phase 2 / `<pkg>/study.py`）：`False` 时 Web 隐藏快速模式、Excel/API 的 `fast` 降级为 `normal`（见 `phase2-api-tools.md` § Video Progress）。
- Schema: **omit** `apply_queue`, `credit_applications`, `ai_subject_cache` unless documented gap.
- Account status machine: **no** `waiting_apply`.
- **No daily learn/apply quota**（公需无单日限制）：Worker **不**调用「今日已学 N 门 → `daily_eligible_at(明日)`」；`config.py` **不设** `MAX_LEARN_PER_DAY` / `MAX_APPLY_PER_DAY`；课程单元 **无** `daily_learn_date`。`scheduling.py` 的 8:00 spread **可省略**（仅 A 型或用户明确要求日切错峰时再实现）。

### Site profile B′ — 项目驱动型 Worker

When `site_profile: B_prime`:

- Store **no** `target_years_json`; `requirements_json` stays `[]`.
- Copy `templates/code/service/project_sync.py` → `<svc>/project_sync.py`.
- `AccountWorker.run_once`: session → **`ProjectTaskRunner.run_account()`** — no `course_planner`, no `YearTaskRunner`.
- `extra_json` must track `project_status` (per `build_project_status()`), `current_project_id`, `current_course_title`, `report_mode`, `phase`.
- Web UI per `web-ui-spec.md` §15; Excel per `excel-spec.md` §2B′.
- **`FAST_REPORT_SUPPORTED`**：同 B 型；站点有限制则不做快速模式。
- Expose **`POST /api/accounts/{id}/sync-projects`** in `web/app.py` (login + `build_project_status` + merge into `extra_json`).
- `GET /api/accounts` returns **`filtered_total`** for pagination (`store.count_accounts` with same filters).
- Schema: omit `apply_queue`, `ai_subject_cache`, `scheduling.py` (same as B).

## Schema (SQLite WAL)

The schema below is the full learning + credit-application shape. Remove or adapt optional tables/columns when the confirmed scope does not include the corresponding capability.

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    requirements_json TEXT NOT NULL DEFAULT '[]',
    extra_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    status_msg TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    queued_at REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    result TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    logs_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id, id DESC);

CREATE TABLE IF NOT EXISTS apply_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    subject_label TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    credits REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    UNIQUE(account_id, project_id)
);

CREATE TABLE IF NOT EXISTS credit_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    success INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    applied_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Global AI subject-mapping cache (all accounts share; NOT in accounts.extra_json)
CREATE TABLE IF NOT EXISTS ai_subject_cache (
    cache_key TEXT PRIMARY KEY,
    requirement_texts_json TEXT NOT NULL,
    catalog_snapshot_json TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);
```

State machine recap:

```
Account.status: queued | running | waiting_apply | retrying | completed | failed | paused
apply_queue.status: pending | in_flight | succeeded | dead | skipped
```

If credit application is not in scope, omit `waiting_apply` and all `apply_queue` status handling from the state machine.

## Account State Machine Rules

| Transition | Trigger |
|------------|---------|
| `queued / retrying → running` | `claim_next_queued()` atomic UPDATE within tx |
| `running → completed` | worker finishes, all in-scope work is done (`applied` when credit is in scope, otherwise learned/exam-complete) |
| `running → waiting_apply` | credit application in scope and learning side done but apply queue has pending |
| `running → retrying` | transient failure, `retry_count++`, `queued_at = now+60` |
| `running → failed` | hard failure (auth, business code) or `retry_count` exceeded |
| `* → queued` (recovery) | service restart, status was `running` |
| `* → paused` | manual pause via API |

When credit application is in scope, `waiting_apply` does NOT count against the learning concurrency limit. This is critical — otherwise the apply queue starves the learning side.

## Orchestrator Tick

```python
# config.py
TICK_STARTS_PER_SECOND = 10  # tick 错峰：滚动 1 秒内最多新拉起 10 个 worker

def tick(self):
    now = time.time()
    # 1) optional apply side runs always, even when paused (drains backlog)
    try: self.apply_worker.process_one(now)
    except Exception: pass
    # 2) learning side: paused short-circuits
    if self.store.is_paused(): return
    limit = self.store.get_concurrency_limit()
    self._prune_start_timestamps(now, window=1.0)  # drop starts older than 1s
    budget = min(
        TICK_STARTS_PER_SECOND - len(self._start_timestamps),
        max(0, limit - self._active),
    )
    for _ in range(budget):
        account = self.store.claim_next_queued(now)
        if not account:
            break
        self._start_timestamps.append(now)
        self._active += 1
        threading.Thread(target=self._run_account, args=(account,), daemon=True).start()
```

**Tick stagger:** rolling **1 second** window, at most **`TICK_STARTS_PER_SECOND` (default 10)** new worker threads — i.e. up to **10 accounts per second**, not one every 2s. Still bounded by `concurrency_limit`. Orthogonal to the 8:00 daily-window spread below; enable both.

## Daily window spread (8:00 per-account stagger)

Many accounts defer to the same calendar **08:00** (Asia/Shanghai). Without spread, `queued_at` / `next_attempt_at` align to one second and the orchestrator can still launch hundreds of workers once the clock passes 8:00 (especially when `concurrency_limit` is high).

**Rule:** every “today/tomorrow at 8:00” deferral MUST use `daily_eligible_at(account_id, local_day=…)` from `<svc>/scheduling.py`, **not** bare `08:00:00`.

```python
# <svc>/scheduling.py  (constants from config.py)
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Shanghai")

def spread_offset_seconds(account_id: int) -> int:
    """Stable offset in [0, DAILY_SPREAD_SECONDS). Same account_id => same offset every day."""
    return int(account_id) % DAILY_SPREAD_SECONDS

def daily_eligible_at(account_id: int, *, local_day: date) -> float:
    """Unix ts: local_day at DAILY_START_HOUR:00 Shanghai + spread_offset_seconds(account_id)."""
    base = datetime(
        local_day.year, local_day.month, local_day.day,
        DAILY_START_HOUR, 0, 0, tzinfo=_TZ,
    )
    return (base + timedelta(seconds=spread_offset_seconds(account_id))).timestamp()

def today_shanghai() -> date:
    return datetime.now(tz=_TZ).date()

def tomorrow_shanghai() -> date:
    return today_shanghai() + timedelta(days=1)
```

| Constant | Default | Why |
|----------|---------|-----|
| `DAILY_SPREAD_SECONDS` | `1800` (30 min) | spreads N accounts across 8:00–8:30; raise to `3600` if fleet > ~2k |
| `DAILY_START_HOUR` | `8` | nominal daily window |

**Properties:**

- **Stable:** use `account_id % DAILY_SPREAD_SECONDS` (or `zlib.crc32(str(account_id).encode()) % …`); never `random()` per deferral.
- **Claim order:** `claim_next_queued` already orders by `queued_at ASC` — accounts naturally wake in spread order after 8:00.
- **Bypass (operator intent):** `POST …/requeue`, `PATCH` with `"requeue": true`, and `POST …/top` may set `queued_at = now` (or `0`) to run immediately; do not re-apply spread on those paths.

**Replace every bare “08:00” timestamp** in worker + apply worker with:

| Old pattern | New |
|-------------|-----|
| today 08:00 | `daily_eligible_at(account.id, local_day=today_shanghai())` |
| tomorrow 08:00 | `daily_eligible_at(account.id, local_day=tomorrow_shanghai())` |

## Worker Pipeline (per account, single call to `run_once`)

The worker re-uses phase 4's `CourseRunner` for the actual learning, plus higher-level orchestration:

```
run_once(account):
    1. ensure_session(account.username, account.password, account.extra.cookies, probe=<cheapest confirmed authenticated API>)
       - If reuse failed and login is rate-limited -> requeue with delay
       - If reuse failed and credentials are wrong -> failed (do not retry)
    2. If no course_results in extra OR forced reassign:
       a. Build Requirement list from account.requirements when the confirmed scope needs requirements
       b. Fetch platform catalog + merge existing progress (applied / learned-not-applied / in-progress)
       c. Label each candidate progress_tier + subject_tier when subject requirements are enabled (see "Course selection priority" below)
       d. Optional: AI subject mapping only when needed (rule match first); lookup/store in global `ai_subject_cache` keyed by (normalized requirement subject texts + platform catalog snapshot) — shared across all accounts; persist per-course `matched_requirement_key` only in account extra, never the cache blob
       e. Sort by (progress_tier, subject_tier, project_id), then DP/greedy to hit credit target when credit/requirement targets exist
       f. Assign queue_rank 0..n in that sorted order; preserve platform state (applied/learned/running), do not wipe
       g. Write course_results to extra, status -> queued, return (next tick will learn)
    3. Daily gate: if now < daily_eligible_at(account.id, local_day=today_shanghai())
       -> push queued_at to that timestamp, return
    4. Learning gate:
       - if credit application is in scope: any course state == "learned" -> waiting_apply (apply worker handles it), return
       - any course daily_learn_date == today -> already learned 1 today
         -> push queued_at to daily_eligible_at(account.id, local_day=tomorrow_shanghai())
       - among courses with state in ("", "running"), pick smallest queue_rank (skip applied/failed/skipped)
    5. Run phase-4 runner on the chosen course
    6. Persist results:
       - success + credit in scope -> course.state = learned,
         push apply_queue with next_attempt_at = daily_eligible_at(account.id, local_day=tomorrow_shanghai()),
         status -> waiting_apply
       - success + no credit in scope -> course.state = learned/completed per site, continue or complete account
       - retryable failure -> status retrying, retry_count++, queued_at = now+60
       - hard failure -> status failed, failed_phase = learning
       - all courses done -> completed
```

Use `extra["phase"]` (e.g. `"login"` / `"assigning"` / `"learning"` / `"waiting_apply"` when credit is in scope / `"idle"`) so the UI can show what the worker is currently doing.

## Course selection priority (fixed)

Same ordering for **building the plan** (`course_planner`) and **picking the next unit to learn** (`queue_rank`). Authoritative Chinese text: `templates/requirements.md` §3.2.1.

### Primary key — `progress_tier` (lower = sooner)

| Value | Tier | Meaning |
|-------|------|---------|
| `0` | Applied / completed | Credit already applied on platform (`state=applied` or equivalent), or completed learning when credit application is not in scope |
| `1` | Learned, not applied | Study/exam done, credit pending (`state=learned` or equivalent); only relevant when credit application is in scope |
| `2` | In progress | Joined or partial progress (`state=running` or equivalent) |
| `3` | Not started | New candidate (`state=""`) |

### Secondary key — `subject_tier` (lower = sooner)

| Value | Tier | Meaning |
|-------|------|---------|
| `0` | Required | Matches a slot in `requirements_json` (学科1 / 学科2) |
| `1` | Public | Platform "公共" category (site-specific IDs/labels in `config.py`) |
| `2` | Other | Neither of the above |

### Tertiary key — stable tie-break

Same tier → sort by `project_id` (or platform course id) lexicographically.

### `queue_rank`

After sorting all units in the plan by `(progress_tier, subject_tier, project_id)`, assign `queue_rank = 0, 1, 2, …`. DP/greedy walks candidates in that order so applied and learned units stay in the plan and are preferred when filling the schedule.

Implement in `<svc>/course_planner.py` (sort + knapsack) and `<svc>/account_pipeline.py` (platform merge). Each result row should store `progress_tier`, `subject_tier`, and optional `matched_requirement_key` for the Web UI.

### AI subject cache (`subject_mapper.py`)

When LLM mapping is enabled (`templates/requirements.md` §11):

1. **Rule match first** — static/synonym/config maps; no LLM, no cache write.
2. **Global cache lookup** — canonicalize non-empty requirement subject strings (sorted) + platform subject list (sorted by id, id+label JSON); `cache_key = sha256(canonical_req + "|" + canonical_catalog)`.
3. **On hit** — apply `mapping_json` (keyed by requirement **text**, not slot name like 学科1).
4. **On miss** — one LLM call for the whole batch, insert into `ai_subject_cache`, then apply.
5. **Never** store mapping cache in `accounts.extra_json`; requeue/delete account must not touch `ai_subject_cache`.

Optional: `DELETE FROM ai_subject_cache WHERE cache_key=?` or truncate via maintenance API if operators need to invalidate stale mappings after a platform catalog change.

## ApplyWorker (only when credit application is in scope)

```
process_one(now):
    1. claim next pending apply task with next_attempt_at <= now
    2. If credit_applications today success count >= daily_apply_limit:
       push pending tasks' next_attempt_at to daily_eligible_at(account.id, local_day=tomorrow_shanghai()), return
    3. ensure_session from account.extra.cookies (fallback to full login)
    4. credit.apply_credit(project_id, auto_survey=True)
    5. On success: status = succeeded, course.state = applied, write credit_applications, check if account fully completed
    6. On rate-limit: next_attempt_at += 300s, status back to pending
    7. On business fail: attempts++, if >= max -> status = dead, course.state = failed
```

Apply worker runs even when the scheduler is paused (the user's pause means "don't start new learning" — finishing already-earned credits is fine). If credit application is not in scope, do not create this worker; completion means learning/exam completion.

## Crash Recovery (run at start)

```sql
UPDATE accounts SET status='queued', status_msg='startup recovery: re-queued', updated_at=?
WHERE status='running';

UPDATE apply_queue SET status='pending' WHERE status='in_flight';
```

## Daily Quotas (encode as constants, not parameters)

| Constant | Value | Why |
|----------|-------|-----|
| `DAILY_START_HOUR` | `8` (Asia/Shanghai) | sites usually open daily window at 8am |
| `DAILY_SPREAD_SECONDS` | `1800` | per-account stable offset after 8:00; avoids 8:00 login/apply burst |
| `MAX_LEARN_PER_DAY` | `1` per account | matches most CME / 继教 rules |
| `MAX_APPLY_PER_DAY` | `1` per account | same |
| `APPLY_AFTER_HOURS` | next-day `daily_eligible_at(...)` | many sites refuse same-day apply; use spread, not bare 08:00 |

Change per site as needed but keep them as constants in `<svc>/config.py`. Do not expose to UI unless the user asks for it.

## Web Console — copy template, adapt to site

The console has a **pre-built template**: copy `templates/code/web/index.html` to `<svc>/web/templates/index.html`, then:

1. Replace `{{ PLATFORM }}` and `{{ LOGO_LETTER }}` with actual values.
2. If `site_profile=B`: use built-in `#addFormB`（模板已含年度 pill + `credential_input_mode` 一栏/分两栏切换）；**勿**删掉 `#fCredentialWrapB` / `applyCredentialInputLayout`；仅删 `[OPTIONAL]` 块并对照 `web-ui-spec.md §14` 验收。
3. If `site_profile=B_prime`: use built-in `#addFormBp`（无年度 pill，含 `credential_input_mode` 一栏/分两栏切换）；**勿**删掉 `#fCredentialWrapBp`；对照 `web-ui-spec.md §15` 验收。
4. Delete `[OPTIONAL:xxx]` blocks for features not in `docs/API_REQUIREMENTS.md` scope.
5. Verify all items in `web-ui-spec.md §12–§13`. Fix any that fail.

**常见模板陷阱**（A/B/B′ 共用，见 `web-ui-spec.md` §6.7、§8.15–§8.16、§15.5–§15.6）：

- `#tableWrap` 初始 `opacity:0` 时，`applyListLayout()` 显示表格必须设 `opacity:1`，否则统计/分页正常但桌面表格不可见。
- **列表首行被遮**：勿用 `thead { top: var(--header-h) }` + `border-collapse: collapse`；须按 `web-ui-spec.md` §6.7 让 `#listPanel .table-wrap` 内部滚动、`thead { top: 0 }`、`border-collapse: separate`。
- 脚本在 IIFE 内时，须 `Object.assign(window, { openDrawer, closeDrawer, requeueAccount, … })`，否则姓名点击与操作列 `onclick` 报 `ReferenceError`。
- B 型列表须 **7 列**（姓名、账号、备注、目标年度、状态、进度、操作），表头与 `rowHtml()` 列数一致；姓名列点击打开抽屉。

Read **`web-ui-spec.md`** as authoritative spec — the template is an implementation of it. If template and spec diverge, fix the template copy.

**固定要求（不可省略）**：

- **界面语言：简体中文**（`lang="zh-CN"`，所有按钮/表头/toast/confirm）
- **复制日志**：失败/重试账号提供「复制日志」按钮，内容 = API 字段 `error_log_text`（格式见 `excel-spec.md` §4）
- 零外链、vanilla JS、inline SVG、≤1600 LOC
- 完整组件/交互/验收见 `web-ui-spec.md`

**Recommended split** (see `cursor-agent-playbook.md` §4): dedicated sub-agent for `index.html`; parent integrates into FastAPI route.

## Excel 导入/导出

面向运营的 Excel：**文件名、Sheet 名、表头字段名全部中文**。实现前 Read **`excel-spec.md`**；生成 xlsx 时同时 Read **`spreadsheet` skill**（`~/.agents/skills/spreadsheet/SKILL.md`）。

摘要（列规则以 `excel-spec.md` 为准，此处不重复）：

- 模板：`{平台中文名}账号模板.xlsx`，Sheet `账号列表` + `填写说明`，表头 `姓名/账号/密码/学科1/学分1/…`（全部中文）
- 导入：只认中文表头；英文表头行报错并中文提示；导出文件可再次导入（忽略 K 列及以后）
- 导出：前 A–J 列与导入模板完全一致，后追加 `状态/说明/重试次数/创建时间/更新时间/最近运行结果/错误日志`
- 后端为列表（failed/retrying）与详情 API 提供 `error_log_text`，供 Web UI「复制日志」使用

## FastAPI Endpoints (canonical surface)

```
GET    /                                       index.html
GET    /api/health
GET    /api/stats                              counts + active_workers + paused + captcha state
GET    /api/accounts?status=&search=&limit=&offset=&date_from=&date_to=
POST   /api/accounts                           create one
POST   /api/accounts/batch                     create many
POST   /api/accounts/upload                    Excel
GET    /api/accounts/{id}                      detail + runs + optional apply_tasks / credit_applications
PATCH  /api/accounts/{id}                      partial update; `"requeue": true` = 编辑重学
DELETE /api/accounts/{id}
POST   /api/accounts/{id}/requeue              重学（语义见 Account operations）
POST   /api/accounts/{id}/top
POST   /api/accounts/{id}/recharge             optional, only if site has confirmed recharge/card flow
POST   /api/scheduler/limit                    {limit: int}
POST   /api/scheduler/pause
POST   /api/scheduler/resume
GET    /api/template                           下载中文 Excel 模板
GET    /api/export                             导出中文 Excel（表头与模板对齐）
GET    /api/ai/config                          read .run/ai_config.json (if AI mapping used)
POST   /api/ai/config
POST   /api/ai/test
```

Sensitive fields (`password`, `cookies`, `card_password`) MUST be stripped from any GET response. Use a `_safe_account(d)` helper.

### Account operations (fixed — must match `web-ui-spec.md` §6.7 + §10.1)

Web UI exposes **exactly three** account actions. Implement backend helpers `requeue_account(id)` and `delete_account(id)`.

| UI label | API | Semantics |
|----------|-----|-----------|
| 重学 | `POST /api/accounts/{id}/requeue` | **Keep** `extra.cookies`, `extra.user_profile`, credentials, config-style `extra` fields; **keep** global `ai_subject_cache` (not account-scoped). **Clear** all post-login runtime data: `<DOMAIN>_results`, `phase`, `failed_phase`, `runs`, `apply_queue`, quota ledgers, error logs; set `status=queued`, reset `retry_count`, refresh `queued_at`. Next tick: `ensure_session` → on probe success skip login and run full post-login pipeline (assign → gates → learn → apply). If account is `running`, abort worker first. |
| 编辑重学 | `PATCH /api/accounts/{id}` with `"requeue": true` | Merge editable fields (empty password = no change), then same as requeue. |
| 删除 | `DELETE /api/accounts/{id}` | Delete account row and **all** related rows (including cookies, course state, runs, apply_queue). |

Do **not** expose `force_relogin` or `reset` endpoints to the UI; requeue + delete supersede them.

### Session expiry during execution (mandatory)

While a worker is running (learning, apply, assignment fetch, etc.), session expiry MUST trigger **automatic relogin**, not manual UI action:

1. Detect via `is_session_expired()` (`phase3-stability.md`).
2. `SessionManager.relogin_user()` at most **once** per failed step; persist new `cookies` / `user_profile`.
3. Retry the current business call **once**; then apply the retry matrix (transient vs hard failure).
4. Each tick still starts with `ensure_session(..., probe=...)`; probe failure → fresh login (`templates/requirements.md` §5.1, §5.1.1). See `phase3-stability.md` Retry Decision Matrix.

## Service Entry — `run_service.py`

### Hard requirements (non-negotiable)

| 行为 | 要求 |
|------|------|
| 单实例 | 同一 `project_root()` 下只允许一个服务进程持有 `service.lock` |
| 二次启动 | 若锁已被占用：**不得**再起第二个 uvicorn；读取 `.run/service/endpoint.json` 中的 `url`，调用 `webbrowser.open(url)`（除非 `--no-browser`），然后 **立即退出 0** |
| 端口避让 | 默认 `17865`；若被占用，`find_available_port` 递增尝试直到可用 |
| 元数据 | 主进程 bind 成功后写入 `endpoint.json`：`{"host","port","url","pid"}`；正常退出时删除 |
| 首次启动 | bind 成功后延迟 ~1.5s 再 `webbrowser.open(url)`（与二次启动共用同一 `url` 字段） |

`endpoint.json` 与 `service.lock` 同目录：`.run/service/`。

### `runtime.py` API (minimum)

Implement in `<svc>/runtime.py` (reference: shuangwei `sww_service/runtime.py`):

- `project_root()` — dev 用仓库根；`sys.frozen` 时用 `Path(sys.executable).parent`
- `SingleInstanceLock(lock_path).try_acquire() -> bool` — 非阻塞；失败表示已有实例
- `find_available_port(host, start_port, max_tries=50) -> int`
- `open_existing_ui(endpoint_path, *, no_browser: bool) -> None` — 读 `url` 并 `webbrowser.open`
- `write_endpoint_meta(path, host, port) -> None` / `clear_endpoint_meta(path) -> None`

锁实现：POSIX `fcntl.flock`，Windows `msvcrt.locking`。

### Skeleton

```python
import argparse, json, os, threading, time, uvicorn, webbrowser
from pathlib import Path
from <svc>.runtime import (
    SingleInstanceLock, find_available_port, project_root,
    open_existing_ui, write_endpoint_meta, clear_endpoint_meta,
)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=17865)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    root = project_root()
    svc_dir = root / ".run" / "service"
    svc_dir.mkdir(parents=True, exist_ok=True)
    lock_path = svc_dir / "service.lock"
    endpoint_path = svc_dir / "endpoint.json"

    lock = SingleInstanceLock(lock_path)
    if not lock.try_acquire():
        open_existing_ui(endpoint_path, no_browser=args.no_browser)
        return 0

    port = find_available_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    write_endpoint_meta(endpoint_path, args.host, port)

    try:
        if not args.no_browser:
            def _open():
                time.sleep(1.5)
                webbrowser.open(url)
            threading.Thread(target=_open, daemon=True).start()
        uvicorn.run("<svc>.web.app:app", host=args.host, port=port, log_level="info")
    finally:
        clear_endpoint_meta(endpoint_path)
        lock.release()

if __name__ == "__main__":
    main()
```

### Acceptance (manual)

1. `./start.sh` → 浏览器打开控制台，终端有 uvicorn 日志。
2. **不关闭第一次**，再双击 `start.sh` 或再运行打包 exe → **只打开浏览器**，不新增进程、不报错弹窗。
3. 把默认端口占满后启动 → 服务监听 `17866` 等，`endpoint.json` 的 `url` 与实际一致。

## End-of-phase Report

1. SQLite tables created, row counts.
2. Web UI URL (e.g. `http://127.0.0.1:17865`).
3. One end-to-end test: add the test account via UI, watch it move through the in-scope states (`queued → running → waiting_apply → completed` when credit is in scope, otherwise `queued → running → completed`); on a failed account, verify **复制日志** copies `error_log_text`.
4. 导出 xlsx → 确认 A–J 列中文表头与模板完全一致；K 列及以后为追加的系统列（状态、说明…）。
5. **二次启动**：服务运行中再执行 `python run_service.py` → 仅打开浏览器，进程数不增加。
6. Ask: "OK to enter phase 6 (one-click start + single-file build)?"

## Pitfalls

- **Threading + SQLite**: open new connections per call (`sqlite3.connect(check_same_thread=False)` + WAL). Do not share a connection across worker threads.
- **`apply_queue` UNIQUE conflicts**: when credit application is in scope, use `INSERT ... ON CONFLICT(account_id,project_id) DO UPDATE SET ...` for idempotent enqueue.
- **Active worker counter leak**: wrap the worker call in `try/finally self._active -= 1`. A leak here causes the scheduler to think it's at capacity forever.
- **Polling every 1s**: don't. 5s is fine for the UI; the scheduler tick can be 2-3s.
- **Requeue vs delete**: requeue preserves cookies for session reuse; delete wipes everything. Do not reintroduce separate `force_relogin` / `reset` UI actions.
- **Pause semantics confusion**: pause = stop starting NEW learning. Running workers finish their course, apply worker keeps running.
- **Bare 08:00 timestamps**: writing the same unix time for every account at day boundary recreates a thundering herd at 8:00 even with tick stagger — always `daily_eligible_at(account_id, local_day)`.
- **Unstable spread**: `random()` per deferral shifts an account's slot daily and confuses operators; use `account_id`-derived offset only.
