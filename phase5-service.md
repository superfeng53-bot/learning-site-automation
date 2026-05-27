# Phase 5 — Multi-Account Always-On Service

Goal: turn the single-account runner into a long-running scheduler that drives many accounts in parallel, persists state across crashes, and exposes a web console for operators. This phase is **highly generic** — most of the design carries over from site to site. Only the worker-internal pipeline (phase 4 runner integration) is site-specific.

## Definition of Done

- [ ] `<svc>/persistence/store.py` with SQLite (WAL) schema for `accounts / runs / apply_queue / credit_applications / kv`
- [ ] `<svc>/worker.py` `AccountWorker.run_once(account)` runs the full single-account pipeline
- [ ] `<svc>/apply_worker.py` `ApplyWorker.process_one(now)` consumes the apply queue independently
- [ ] `<svc>/orchestrator.py` ticks every N seconds, claims queued accounts under a concurrency limit
- [ ] `<svc>/web/app.py` FastAPI serves the console + `/api/*` endpoints
- [ ] `<svc>/web/templates/index.html` single-page console with inlined CSS/JS, no third-party UI libs
- [ ] `run_service.py` at project root: single-instance lock + port avoidance + auto-open browser
- [ ] Crash recovery: restarting the service requeues `running` accounts and `in_flight` apply tasks

## Read First

If the user has provided their own requirements doc, read it now. Otherwise, copy `templates/requirements.md` to `docs/通用需求说明.md` and **adapt** the placeholders (`<PLATFORM>`, `<DOMAIN>`, captcha kind, quotas) to the actual site. The skeleton is the same; numbers and labels differ.

## Schema (SQLite WAL)

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
```

State machine recap:

```
Account.status: queued | running | waiting_apply | retrying | completed | failed | paused
apply_queue.status: pending | in_flight | succeeded | dead | skipped
```

## Account State Machine Rules

| Transition | Trigger |
|------------|---------|
| `queued / retrying → running` | `claim_next_queued()` atomic UPDATE within tx |
| `running → completed` | worker finishes, all courses have `state == applied` |
| `running → waiting_apply` | learning side done but apply queue has pending |
| `running → retrying` | transient failure, `retry_count++`, `queued_at = now+60` |
| `running → failed` | hard failure (auth, business code) or `retry_count` exceeded |
| `* → queued` (recovery) | service restart, status was `running` |
| `* → paused` | manual pause via API |

`waiting_apply` does NOT count against the learning concurrency limit. This is critical — otherwise the apply queue starves the learning side.

## Orchestrator Tick

```python
def tick(self):
    now = time.time()
    # 1) apply side runs always, even when paused (drains backlog)
    try: self.apply_worker.process_one(now)
    except Exception: pass
    # 2) learning side: paused short-circuits
    if self.store.is_paused(): return
    limit = self.store.get_concurrency_limit()
    if self._active >= limit: return
    if now - self._last_start < self._stagger_seconds: return  # 2s stagger
    account = self.store.claim_next_queued(now)
    if not account: return
    self._last_start = now
    self._active += 1
    threading.Thread(target=self._run_account, args=(account,), daemon=True).start()
```

Stagger (e.g. 2s) avoids login thundering-herd; concurrency limit (typically 1-5) controls memory + per-IP rate.

## Worker Pipeline (per account, single call to `run_once`)

The worker re-uses phase 4's `CourseRunner` for the actual learning, plus higher-level orchestration:

```
run_once(account):
    1. ensure_session(account.username, account.password, account.extra.cookies, probe=list_subjects)
       - If reuse failed and login is rate-limited -> requeue with delay
       - If reuse failed and credentials are wrong -> failed (do not retry)
    2. If no course_results in extra OR forced reassign:
       a. Build Requirement list from account.requirements
       b. Optional: AI subject mapping (e.g. zhipuai GLM)
       c. Plan courses (DP knapsack to hit credit target)
       d. Write course_results to extra, status -> queued, return (next tick will learn)
    3. Daily gate: before 08:00 Asia/Shanghai -> push queued_at to today 08:00, return
    4. Learning gate:
       - any course state == "learned" -> waiting_apply (apply worker handles it), return
       - any course daily_learn_date == today -> already learned 1 today, push to tomorrow 08:00
       - pick course with smallest queue_rank that is not done today
    5. Run phase-4 runner on the chosen course
    6. Persist results:
       - success -> course.state = learned, push apply_queue with next_attempt_at = tomorrow 08:00, status -> waiting_apply
       - retryable failure -> status retrying, retry_count++, queued_at = now+60
       - hard failure -> status failed, failed_phase = learning
       - all courses done -> completed
```

Use `extra["phase"]` (e.g. `"login" / "assigning" / "learning" / "waiting_apply" / "idle"`) so the UI can show what the worker is currently doing.

## ApplyWorker

```
process_one(now):
    1. claim next pending apply task with next_attempt_at <= now
    2. If credit_applications today success count >= daily_apply_limit: push the whole account's pending tasks to tomorrow 08:00, return
    3. ensure_session from account.extra.cookies (fallback to full login)
    4. credit.apply_credit(project_id, auto_survey=True)
    5. On success: status = succeeded, course.state = applied, write credit_applications, check if account fully completed
    6. On rate-limit: next_attempt_at += 300s, status back to pending
    7. On business fail: attempts++, if >= max -> status = dead, course.state = failed
```

Apply worker runs even when the scheduler is paused (the user's pause means "don't start new learning" — finishing already-earned credits is fine).

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
| `MAX_LEARN_PER_DAY` | `1` per account | matches most CME / 继教 rules |
| `MAX_APPLY_PER_DAY` | `1` per account | same |
| `APPLY_AFTER_HOURS` | next-day 08:00 | many sites refuse same-day apply |

Change per site as needed but keep them as constants in `<svc>/config.py`. Do not expose to UI unless the user asks for it.

## Web Console — minimum-viable layout

Use the template at `templates/web-ui-template.html` (single file, inlined CSS + vanilla JS, polls `/api/stats` and `/api/accounts` every 5s). Required pieces:

- Top bar: title, status badge, concurrency input, pause/resume, template download, export, AI config
- Stat tiles: total / queued / running / waiting_apply / completed / failed / active workers
- Add-account form: name / username / password / requirement-1 / credits-1 / requirement-2 / credits-2 / optional card-no / card-pw
- Excel upload
- Account list (search, status pill filter, date range, paging)
- Expandable detail row: course table, apply queue, credit applications, run history, AI mapping results
- Per-row actions: requeue / top / edit / clear-token / reset / delete

## FastAPI Endpoints (canonical surface)

```
GET    /                                       index.html
GET    /api/health
GET    /api/stats                              counts + active_workers + paused + captcha state
GET    /api/accounts?status=&search=&limit=&offset=&date_from=&date_to=
POST   /api/accounts                           create one
POST   /api/accounts/batch                     create many
POST   /api/accounts/upload                    Excel
GET    /api/accounts/{id}                      detail + runs + apply_tasks + credit_applications
PATCH  /api/accounts/{id}                      partial update
DELETE /api/accounts/{id}
POST   /api/accounts/{id}/requeue
POST   /api/accounts/{id}/top
POST   /api/accounts/{id}/force_relogin        clear cookies, next tick = fresh login
POST   /api/accounts/{id}/reset                clear course state + cookies, keep credentials
POST   /api/accounts/{id}/recharge             optional, if site has recharge cards
POST   /api/scheduler/limit                    {limit: int}
POST   /api/scheduler/pause
POST   /api/scheduler/resume
GET    /api/template                           Excel template download
GET    /api/export                             full export Excel
GET    /api/ai/config                          read .run/ai_config.json (if AI mapping used)
POST   /api/ai/config
POST   /api/ai/test
```

Sensitive fields (`password`, `cookies`, `card_password`) MUST be stripped from any GET response. Use a `_safe_account(d)` helper.

## Service Entry — `run_service.py`

```python
from sww_service.runtime import SingleInstanceLock, find_available_port, project_root
import uvicorn, webbrowser, argparse, threading, time
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=17865)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    lock_path = project_root() / ".run" / "service" / "service.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with SingleInstanceLock(lock_path):
        port = find_available_port(args.host, args.port)
        if not args.no_browser:
            def _open():
                time.sleep(1.5)
                webbrowser.open(f"http://{args.host}:{port}")
            threading.Thread(target=_open, daemon=True).start()
        uvicorn.run("<svc>.web.app:app", host=args.host, port=port, log_level="info")

if __name__ == "__main__":
    main()
```

`SingleInstanceLock` uses fcntl on POSIX, msvcrt on Windows. Reference impl in shuangwei `sww_service/runtime.py`.

## Excel Import / Export

- File name: `<site>账号模板.xlsx` (e.g. `医博士账号模板.xlsx`)
- Sheet 1: `账号列表` with Chinese headers `姓名 / 账号 / 密码 / 学科1 / 学分1 / 学科2 / 学分2 / 卡号 / 卡号密码 / 备注`
- Sheet 2: `填写说明` — short guide
- Export adds columns: `状态 / 说明 / 重试次数 / 创建时间`

Only recognize Chinese headers in import — defensive against column reorder.

## End-of-phase Report

1. SQLite tables created, row counts.
2. Web UI URL (e.g. `http://127.0.0.1:17865`).
3. One end-to-end test: add the test account via UI, watch it move queued → running → waiting_apply → completed.
4. Files added/changed.
5. Ask: "OK to enter phase 6 (one-click start + single-file build)?"

## Pitfalls

- **Threading + SQLite**: open new connections per call (`sqlite3.connect(check_same_thread=False)` + WAL). Do not share a connection across worker threads.
- **`apply_queue` UNIQUE conflicts**: use `INSERT ... ON CONFLICT(account_id,project_id) DO UPDATE SET ...` for idempotent enqueue.
- **Active worker counter leak**: wrap the worker call in `try/finally self._active -= 1`. A leak here causes the scheduler to think it's at capacity forever.
- **Polling every 1s**: don't. 5s is fine for the UI; the scheduler tick can be 2-3s.
- **`force_relogin` should NOT wipe `course_results`**: only `reset` does that. Two different operations.
- **Pause semantics confusion**: pause = stop starting NEW learning. Running workers finish their course, apply worker keeps running.
