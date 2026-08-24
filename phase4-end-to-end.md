# Phase 4 — End-to-End Single-Account Runner

Goal: stitch the confirmed phase-2 services into one `CourseRunner` that, given (cookies OR credentials, project_id), drives a single course through the site's required learning stages: join/enroll if needed, watch/report progress, exam if the course has one, and credit application when the site exposes that flow. Plus a top-level `run_course.py` CLI that takes the smallest possible set of inputs.

**Goal 编排**：由 **Phase 4 工人**一次做完（含 60s 进度探针）。禁止 New Chat。是否进入 Phase 5 由**父 agent** AskQuestion，工人不要自己问。

## Definition of Done

- [ ] `<pkg>/course_runner.py` exposes `CourseRunner(course, study, exam=None, credit=None).run(project_id) -> RunResult`
- [ ] `RunResult` reports stage outcomes: `joined`, `watched`, `exam_passed` when applicable, `credit_applied` when credit application is in scope, plus a per-chapter log
- [ ] `run_course.py` at project root: `python run_course.py --cookies data/cookies.json --project-id <uuid>` works end-to-end
- [ ] **Progress gate**: `CourseRunner.probe_progress(project_id, probe_seconds=60)` (or `run_course.py --probe-progress`) passes on the smoke-test course **before** any full-course run is attempted
- [ ] Resumable: if the run crashes mid-watch, re-running picks up where it left off (uses progress API, not local state)
- [ ] All transient failures auto-recover via phase-3 plumbing; only business failures stop the run
- [ ] Optional `--account data/account.json --auto-login` mode that combines `ensure_session` with the runner

## Site profile B — Year task runner (alternative to CourseRunner)

When `docs/API_REQUIREMENTS.md` specifies **B — 公需年度型** (`site-profiles.md`):

- [ ] `<pkg>/task_api.py` (or `year_runner.py`) exposes `run_year_task(client, year, ...) -> YearTaskResult`
- [ ] `run_year.py` CLI: `--cookies` + `--years 2026,2025` runs years **in list order**
- [ ] Inside each year: `get_year_courses` → filter pending → serial `study_course` → `take_exam` per course when required
- [ ] **`study_course` callbacks**：`on_hour_start` / `on_progress_tick` / `on_hour_complete`（Phase 5 Worker 写进度用；见 `progress-sync.md`）
- [ ] **`run_year_task` 透传**上述回调至 `study_course`
- [ ] **年度完成判定**：复制 `templates/code/pkg/year_task_template.py` → `<pkg>/year_task.py`；用 `_resolve_year_completion` 结合证书 `auditStatus`，**勿仅**依赖 `publicNum`（见 `progress-sync.md` §年度完成判定）
- [ ] Completion probe: certificate `earned_hours >= required_hours` **或** `auditStatus==1` **或** 课程全完成 + 证书已提交
- [ ] **Progress gate** (before full `run_year.py`): on the year's first pending course, run the same ~60s progress-increment probe (via `probe_progress` on that course's `project_id`, or a B-type equivalent on `study_course` heartbeat) and record pass/fail in `PHASE4_REPORT.md`
- [ ] **Do not** generate `course_planner.py` or subject-mapping for B-only projects

Phase 5 worker calls this module in a `for year in account.target_years` loop instead of `CourseRunner.run(project_id)`.

## Site profile B′ — Project task runner (alternative to CourseRunner / YearTaskRunner)

When `docs/API_REQUIREMENTS.md` specifies **B_prime — 项目驱动型** (`site-profiles.md` §B′):

- [ ] `<pkg>/course_plan.py` from `templates/code/api/course_plan.py` — credit-cap planning per project `N_ZXF`
- [ ] `<pkg>/project_task.py` from `templates/code/runner/project_runner.py` — `ProjectTaskRunner.run_account()`
- [ ] `CourseService.list_actionable_courses(project_id)` delegates to `plan_actionable_courses()`
- [ ] `run_course.py` CLI: `--dry-run` lists planned courses only; `--max-study-rounds 1` for single-lesson smoke
- [ ] **`report_mode=normal`** uses site-native `step`/`interval` from Phase 2 recon (`step >= interval`, typically 1× real time)
- [ ] **`report_mode=fast`** only when `FAST_REPORT_SUPPORTED=True`；**步长不变**，仅 `REPORT_INTERVAL_FAST < REPORT_INTERVAL_NORMAL`；探针无 `study_time_more`
- [ ] When `FAST_REPORT_SUPPORTED=False`, Web/Excel omit fast mode and coerce `fast` → `normal`
- [ ] **Do not** generate `YearTaskRunner`, `run_year.py`, or `target_years` handling

Phase 5 worker calls `ProjectTaskRunner.run_account()` instead of year loop or `CourseRunner`.

## Read First

Read `docs/API_REQUIREMENTS.md` and `<pkg>/API_REFERENCE.md` before writing the runner:

- Always include the mandatory learning path: account/session, course detail/status, join/enroll when required by the site, and progress reporting.
- Treat exam as mandatory-if-present. If the site has no exam flow, record `exam_required=False` / `exam_passed=True` with a clear log message such as `site has no exam flow`.
- Treat credit application as mandatory-if-present. If `docs/API_REQUIREMENTS.md` documents a site credit-application flow, wire `CreditService` and apply-queue assumptions; if the site has no such flow, do not import `CreditService`, leave `credit_applied=False` or `None` based on the project's chosen result schema, and record `skipped: site has no credit application flow`. **B 型**默认在 `API_REQUIREMENTS` 的 Explicit Skips 中已排除申请学分，直接走 **Site profile B** 小节，勿实现 `CreditService`。

## Module: `course_runner.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class LessonPhase(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    STUCK = "stuck"           # progress saved but below threshold; needs full replay
    EXAM_PENDING = "exam_pending"
    DONE = "done"


@dataclass
class StageLog:
    stage: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    project_id: str
    joined: bool = False
    watched: bool = False
    exam_passed: bool = False
    credit_applied: bool = False
    final_state: str = "running"  # learned / applied / failed
    logs: list[StageLog] = field(default_factory=list)
    error: str | None = None


class CourseRunner:
    def __init__(self, course_svc, study_svc, exam_svc=None, credit_svc=None):
        self.course = course_svc
        self.study = study_svc
        self.exam = exam_svc
        self.credit = credit_svc

    def run(self, project_id: str, *, apply_credit: bool = False) -> RunResult:
        result = RunResult(project_id=project_id)
        try:
            detail = self.course.get_detail(project_id)
            self._ensure_joined(project_id, detail, result)
            self._drive_lessons(project_id, detail, result)
            self._take_exam(project_id, detail, result)
            if apply_credit and self.credit is not None:
                self._apply_credit(project_id, result)
            result.final_state = "applied" if result.credit_applied else "learned"
        except Exception as exc:
            result.error = str(exc)
            result.final_state = "failed"
            result.logs.append(StageLog("runner", False, str(exc)))
        return result

    def _ensure_joined(self, project_id, detail, result):
        if detail.get("joined"):
            result.joined = True
            result.logs.append(StageLog("join", True, "already joined"))
            return
        resp = self.study.join_project(project_id)
        result.joined = resp.ok
        result.logs.append(StageLog("join", resp.ok, resp.message))
        if not resp.ok:
            raise RuntimeError(f"join failed: {resp.message}")

    def _drive_lessons(self, project_id, detail, result):
        for lesson in detail["lessons"]:
            phase = self._classify(lesson)
            if phase == LessonPhase.DONE:
                continue
            if phase == LessonPhase.EXAM_PENDING:
                continue
            self._watch_lesson(project_id, lesson, resume=(phase == LessonPhase.IN_PROGRESS))
            result.logs.append(StageLog(f"lesson:{lesson['id']}", True, "watched"))
        result.watched = True

    def _classify(self, lesson) -> LessonPhase:
        if lesson.get("completed"):
            return LessonPhase.DONE
        if lesson.get("exam_pending"):
            return LessonPhase.EXAM_PENDING
        played = lesson.get("play_time", 0)
        if played >= lesson["duration"] * 0.95:
            return LessonPhase.STUCK
        if played > 0:
            return LessonPhase.IN_PROGRESS
        return LessonPhase.NOT_STARTED

    def _watch_lesson(self, project_id, lesson, *, resume: bool):
        start = lesson["play_time"] if resume else 0
        self.study.watch_video(
            project_id=project_id,
            study_id=lesson["study_id"],
            duration=lesson["duration"],
            start_at=start,
        )

    def _take_exam(self, project_id, detail, result):
        if not detail.get("has_exam"):
            result.exam_passed = True
            return
        if self.exam is None:
            raise RuntimeError("course has exam but ExamService is not configured")
        outcome = self.exam.pass_exam(project_id, detail["exam_study_id"])
        result.exam_passed = outcome.ok
        result.logs.append(StageLog("exam", outcome.ok, outcome.message))
        if not outcome.ok:
            raise RuntimeError(f"exam failed: {outcome.message}")

    def _apply_credit(self, project_id, result):
        if self.credit is None:
            raise RuntimeError("credit application in scope but CreditService is not configured")
        outcome = self.credit.apply_credit(project_id, auto_survey=True)
        result.credit_applied = outcome.ok
        result.logs.append(StageLog("credit", outcome.ok, outcome.message,
                                    detail={"code": outcome.code, "hint": outcome.hint}))
```

Adapt the lesson-classification logic to whatever fields the site's detail endpoint actually returns (you discovered them in phase 2).

## Progress increment probe (gate before full run)

**Mandatory gate**: do **not** start the full-course smoke test until a short progress probe passes on the same `project_id` you will use for the full run (typically `<smallest-course>`).

Purpose: confirm join + `record_play_time` (or site equivalent) actually moves server-side progress, without waiting for a multi-hour video to finish.

### Protocol

1. `get_detail(project_id)` → pick the **first incomplete lesson** (skip `DONE` / `EXAM_PENDING`).
2. If the course requires join and is not joined → `join_project` (same as full run).
3. Record `play_time_before` from that lesson (field names per phase-2 recon).
4. For **`probe_seconds` wall-clock** (default **60**), loop `record_play_time` using the site's calibrated `step` / `interval` from phase 2 (`phase2-api-tools.md` § Video Progress). **Do not** set `is_complete=1` and **do not** cross `WATCH_THRESHOLD` — stop the probe before the lesson would count as finished.
5. `get_detail(project_id)` again → read `play_time_after` on the same lesson.
6. **Pass** when `delta = play_time_after - play_time_before` is **≥ `min_delta`** (default **1** second, or one successful `step` if the site quantizes progress).

Expose on `CourseRunner`:

```python
@dataclass
class ProgressProbeResult:
    ok: bool
    project_id: str
    lesson_id: str = ""
    play_time_before: float = 0
    play_time_after: float = 0
    delta: float = 0
    probe_seconds: int = 60
    error: str | None = None
    logs: list[StageLog] = field(default_factory=list)

def probe_progress(self, project_id: str, *, probe_seconds: int = 60, min_delta: float = 1) -> ProgressProbeResult:
    ...
```

CLI (mutually exclusive with full run):

```bash
python run_course.py --account data/account.json --project-id <smallest-course> --probe-progress
python run_course.py --account data/account.json --project-id <uuid> --probe-progress --probe-seconds 60
```

On failure: fix `step`/`interval`, join path, or lesson field mapping in phase 2 — **do not** proceed to full-course smoke.

## `run_course.py` (project root entry)

Three input modes, easiest to most explicit:

```bash
# Mode A: cookies file + project-id (assumes already logged in)
python run_course.py --cookies data/cookies.json --project-id <uuid>

# Mode B: account file + project-id (auto login, save cookies)
python run_course.py --account data/account.json --project-id <uuid>

# Mode C: full inline
python run_course.py -u 13800000000 -p ******** --project-id <uuid> --apply-credit

# Gate (run this first on the same project-id):
python run_course.py --account data/account.json --project-id <smallest-course> --probe-progress
```

Skeleton:

```python
import argparse, json, sys
from pathlib import Path
from <pkg> import get_session_manager

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cookies")
    p.add_argument("--account")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--project-id", required=True)
    p.add_argument("--probe-progress", action="store_true",
                   help="60s progress-increment gate; do not run full course")
    p.add_argument("--probe-seconds", type=int, default=60)
    p.add_argument("--apply-credit", action="store_true")
    p.add_argument("--user-id", default="default")
    args = p.parse_args()

    mgr = get_session_manager()
    if args.cookies:
        mgr.load_user_cookies_file(args.user_id, Path(args.cookies))
        username = password = ""
    elif args.account:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]
    elif args.username and args.password:
        username, password = args.username, args.password
    else:
        sys.exit("need --cookies / --account / -u+-p")

    if username:
        cookies = mgr.get_client(args.user_id).export_cookies() if args.cookies else None
        reused, cookies, info, err = mgr.ensure_session(
            args.user_id, username, password, cookies=cookies,
            probe=lambda: mgr.get_course_service(args.user_id).list_subjects(),
        )
        if err:
            sys.exit(f"login failed: {err}")
        Path("data/cookies.json").write_text(json.dumps(cookies), encoding="utf-8")

    runner = mgr.get_course_runner(args.user_id)
    if args.probe_progress:
        result = runner.probe_progress(args.project_id, probe_seconds=args.probe_seconds)
        print(json.dumps({k: v for k, v in result.__dict__.items()}, ensure_ascii=False, indent=2))
        sys.exit(0 if result.ok else 1)
    result = runner.run(args.project_id, apply_credit=args.apply_credit)
    print(json.dumps({
        "project_id": result.project_id,
        "final_state": result.final_state,
        "joined": result.joined,
        "watched": result.watched,
        "exam_passed": result.exam_passed,
        "credit_applied": result.credit_applied,
        "error": result.error,
        "logs": [log.__dict__ for log in result.logs],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

Add a `get_course_runner(user_id)` factory on `SessionManager` for ergonomics.

## Smoke Test Checklist

Run, in order, against the test account. **Step 0 is a hard gate** — if it fails, fix phase-2 progress reporting before attempting steps 1–5.

0. **Progress increment probe** (same `project_id` as step 1):
   `python run_course.py --account data/account.json --project-id <smallest-course> --probe-progress`
   → JSON `ok: true`, `delta >= 1` (or ≥ one `step`); record `play_time_before` / `play_time_after` in `PHASE4_REPORT.md`
1. `python run_course.py --account data/account.json --project-id <smallest-course>` → mandatory stage booleans true; optional booleans are asserted only when selected in `docs/API_REQUIREMENTS.md`
2. Same command again → should be a no-op (everything `DONE`), exits cleanly
3. Delete `data/cookies.json`, run again → fresh login + full run
4. Pick a course you've already half-watched in browser, run → confirms resume behavior
5. If credit application is in scope per `docs/API_REQUIREMENTS.md`, pass `--apply-credit` → check `credit_applied=true` and surface the hint dict if the site returned a code. If not in scope, verify the CLI rejects or omits `--apply-credit` clearly.

If step 0 fails, tune `step`/`interval` or field mapping — not `WATCH_THRESHOLD`. If step 4 fails, the lesson-classification heuristic is wrong — adjust thresholds.

## End-of-phase Decision Point

This is the LAST mandatory phase. Use `AskQuestion` to ask:

- Continue to phase 5 (always-on multi-account service with web console)?
- Or stop at phase 4 (caller will integrate the runner themselves)?

If the user stops here, summarize the API surface they need to call: `get_session_manager`, `ensure_session`, `get_course_runner`, `CourseRunner.run`.

## Pitfalls

- **Skipping the progress probe**: long videos make full smoke painful, but step 0 exists precisely to catch broken `record_play_time` early — never skip it for convenience.
- **`played >= duration * 0.95` heuristic**: too aggressive, the site may consider 95% as not-watched. Read the site's own JS to find the actual completion threshold. Common values: 98%, 100%, or `tail_time` check.
- **Re-joining a finished course**: some sites error out; check `detail.joined` first.
- **Survey/eval required before exam**: rare but exists. Add a pre-exam stage if you see it during phase 2 recon.
- **Background tab throttling not relevant**: we're pure HTTP, no browser tabs.
- **Don't run two courses in parallel for the same user**: serialize within an account. Parallelism is across accounts (that's phase 5).
