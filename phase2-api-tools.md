# Phase 2 — Business API Toolkit

Goal: wrap the confirmed business endpoints the site exposes into thin `<pkg>/*.py` service classes, each operating on a shared `HttpClient`. The common learning workflow is mandatory; optional capabilities are selected and confirmed with the user before API discovery starts. Produce `<pkg>/API_REFERENCE.md` that future phases will read.

## Definition of Done

- [ ] One `*Service` class per business domain, each owning its endpoints
- [ ] One `cli_*.py` per service, runnable via `python -m <pkg>.cli_<name>`
- [ ] `<pkg>/API_REFERENCE.md` lists every endpoint: method, path, params, sample response, failure codes
- [ ] `docs/API_REQUIREMENTS.md` records the user-confirmed required and optional capability scope
- [ ] Every service uses the shared `HttpClient` (no ad-hoc `requests.post` calls)
- [ ] All failure paths return a `SwwResponse`-shaped dataclass (or equivalent) with `ok / message / code / hint / raw`

## Step 0 — Confirm Site Profile + API Capability Scope

Before any Phase 2 browser reconnaissance or service generation, read **`site-profiles.md`**（含 **§B 型快速路径**）。

### 0.1 定画像（A / B）

| 情况 | 动作 |
|------|------|
| 用户目标已写明公需 / 按年 / 年度学时，且无疑义 | 直接 `site_profile: B`，**不**单独 AskQuestion |
| 用户目标已写明学科规划 / 双卫式选课 / 申请学分 | 直接 `site_profile: A` |
| 不明 | **一次** `AskQuestion` 单选 A / B（文案见 `site-profiles.md`） |

### 0.2 定可选能力（按画像分叉）

**B — 公需年度型**

1. 复制 **`templates/api-requirements-b.md`** → `docs/API_REQUIREMENTS.md`，替换 `<PLATFORM>`。
2. **不要**跑「学科列表 / 注册 / 购卡 / 其他」全量多选。
3. **仅当** `site-profiles.md` §B 型快速路径「追加提问」表有触发项时，再 `AskQuestion` 补选（通常 0–1 次）。
4. 复制 `templates/requirements-year-driven.md` → `docs/通用需求说明.md`（可与 0.2 并行）。

**A — 学科规划型**

1. 用 **`AskQuestion` 多选**可选 API 能力（见下文 Suggested prompt）。
2. 从 **`templates/api-requirements.md`** 生成 `docs/API_REQUIREMENTS.md`，填入 Optional Selected / Not Selected。
3. 复制 `templates/requirements.md` → `docs/通用需求说明.md`。

Exam / 申请学分：**均不在 AskQuestion 里让用户勾选**——有无由浏览器侦察决定；B 型申请学分默认 **Explicit Skip**（见 B 模板）。

Profile-specific Phase 2 domains:

| Profile | Extra domains beyond login/member/study/exam |
|---------|-----------------------------------------------|
| A | `course` catalog + optional `credit`; optional subject list API |
| B | `course` as **yearly_learning + year_courses + certificate**; `task` or `year_runner`; **固定 skip** `credit` and subject-list APIs |

Mandatory capabilities are always in scope:

| Capability | Typical domains | Notes |
|------------|-----------------|-------|
| Login / session continuity | `login`, `member` | Phase 1 login plus Phase 3 session probe must keep working |
| Account / profile info | `member` | User profile, identity, balance or equivalent account metadata |
| Course list | `course` | Catalog, available courses, joined courses if separate |
| Course detail and status | `course`, `study` | Lessons, duration, joined state, progress, completion flags |
| Course progress reporting | `study` | Video/chapter progress, completion checkpoints |
| Course exam, if present | `exam` | Start paper, submit answers, read result; skip only when the site has no exam flow |
| Credit application, if present | `credit` | Credit preview, evaluation/survey, application, application status; skip only when the site has no credit-application flow |

Optional capabilities must be selected by the user:

| Option | Typical domain | When selected |
|--------|----------------|---------------|
| 学科列表 / 分类列表 | `course` | Need subject/category discovery, subject mapping, or account requirements by subject |
| 注册 | `registration` | Need to create platform accounts through API |
| 购卡 / 充值 | `recharge` | Need card purchase, card binding, recharge, or balance top-up |
| 其他 | site-specific | User describes extra business flow; create a named domain for it |

Suggested `AskQuestion` prompt（**仅 A 型**；B 型见 Step 0.2，默认跳过本问）：

```text
这个站点除了通用学习流程外，还需要实现哪些可选 API 能力？可多选；如果有其他需求，请选「其他」并补充说明。
```

B 型仅在购卡/注册/混合专题触发时，用窄问替代全量多选，例如：

```text
公需年度型默认不需要学科列表和申请学分。本站点是否需要额外实现：购卡/充值、注册、或其他流程？
```

After the user answers (**A 型**或 **B 型追加一问**), write or update:

```markdown
# API Requirements

## Mandatory
- Login / session continuity
- Account / profile info
- Course list
- Course detail and status
- Course progress reporting
- Course exam, if present
- Credit application, if present

## Optional Selected
- 学科列表 / 分类列表

## Optional Not Selected
- 注册
- 购卡 / 充值

## Site-Specific Notes
- ...

## Phase 2 Domain Plan
- member
- course
- study
- exam (discover and implement only if present)
- credit (discover and implement only if present)
```

If a mandatory-if-present capability is genuinely absent from the site (for example no exam or no credit-application flow), document it as `skipped: site has no exam flow` or `skipped: site has no credit application flow` in both `docs/API_REQUIREMENTS.md` and the phase verification report. Do not ask the user to opt out of exam or credit in the Phase 2 `AskQuestion` — presence is decided by browser recon, same as exam.

## Discovery Loop (repeat for each domain)

**Cursor 编排**：每个 confirmed domain 单独一轮——先用 **`cursor-ide-browser` MCP**（内置浏览器，playbook §1.1）+ `Task explore` 或 `api-recon` subagent → `docs/api-discovery/<domain>.md`，再 `Task generalPurpose` 实现 `*Service`。每完成 **2 个 domain** 写 `docs/handoffs/PHASE2_<domains>_done.md` 并建议用户 **New Chat**。详见 playbook §3、§5。

1. **Browse with the test account** using **`cursor-ide-browser` MCP** (not external automation), perform the action manually
2. Capture the network calls via `browser_cdp Network.enable` and `Network.requestWillBeSent` / `responseReceived`. Use `Network.getResponseBody` for response shapes you cannot read from the snapshot
3. Note: request body (form vs JSON), required headers, response codes
4. After browser recon is written to `docs/api-discovery/<domain>.md`, optionally use **`shell` skill** / a tiny `curl` script with `data/cookies.json` to confirm parity (do not use this step to *discover* endpoints)
5. Confirm parity with browser behaviour
6. Promote the script into a service method

Do this for each confirmed domain in roughly this order. Mandatory domains come first; optional domains are included only when selected by the user or required by a selected flow.

## Canonical Domains

| Scope | Domain | Typical endpoints | File |
|-------|--------|-------------------|------|
| Mandatory | Member / profile | `/member/balance`, `/member/projects`, `/member/info` | `member.py` |
| Mandatory | Course catalog | `/course/list`, `/course/detail` | `course.py` |
| Optional: 学科列表 | Subject / category list | `/subject/list`, `/category/list` | `course.py` or `subject.py` |
| Mandatory | Join / enroll | `/study/join`, `/member/join` | `study.py` (join section) |
| Mandatory | Video progress | `/study/recordPlayTime`, `/study/progress` | `study.py` |
| Mandatory if present | Exam | `/exam/start`, `/exam/submit`, `/exam/result` | `exam.py` |
| Mandatory if present | Credit application | `/member/creditMsg`, `/member/requestCredit`, `/projecteva/saveEva` | `credit.py` |
| Optional: 购卡 / 充值 | Recharge | `/card/recharge`, `/recharge/...` | `recharge.py` |
| Optional: 注册 | Registration | `/register`, `/user/create`, `/sms/send` | `registration.py` |
| Optional: 其他 | Site-specific | confirmed with user | named after the domain |

## Service Class Pattern

Every service follows the same shape:

```python
from .client import HttpClient
from .responses import ApiResponse, parse_member_response


class CourseService:
    def __init__(self, client: HttpClient):
        self.client = client

    def list_subjects(self) -> list[dict]:
        """Include only when 学科列表 / 分类列表 is selected or required by the site."""
        data = self.client.form_post_safe("/subject/list", {})
        if data.get("result") != "ok":
            raise RuntimeError(data.get("msg", "list_subjects failed"))
        return data.get("msg") or []

    def list_courses(self, speciality_id: str) -> list[dict]:
        ...

    def get_detail(self, project_id: str) -> dict:
        ...
```

Rules:

- Methods raise `RuntimeError` (or a domain-specific exception) on hard failure.
- Methods returning a soft-failure should return `ApiResponse` (the `responses.py` dataclass) so the caller can branch on `ok`.
- No retry logic here — that goes in phase 3.
- No session-expired handling here either — phase 3.

## Response Parsing Module

Create `<pkg>/responses.py` with one `ApiResponse` dataclass and per-domain parsers + hint dictionaries:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ApiResponse:
    ok: bool
    raw: dict[str, Any]
    message: str
    code: str | None = None
    hint: str = ""

LOGIN_MSG_HINTS = {
    "-1": "用户名或密码错误",
    "-4": "验证码已失效",
    # ...
}

CREDIT_CODE_HINTS = {
    "-6": "未完成项目评价，需先访问 /html/survey",
    "-8": "今日申请上限",
    # ...
}

def parse_member_response(data: dict, *, ok_msg: str = "操作成功") -> ApiResponse:
    ok = data.get("result") == "ok"
    msg = str(data.get("msg") or "")
    return ApiResponse(ok=ok, raw=data, message=msg or ok_msg,
                       code=data.get("result"),
                       hint=LOGIN_MSG_HINTS.get(msg, ""))
```

Populate the hint dictionaries with **only the codes you actually observed in browser recon**. Do not guess.

## CLI Pattern

Every service gets a thin CLI wrapper for manual testing:

```python
import argparse, json
from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("subjects")
    courses = sub.add_parser("courses"); courses.add_argument("--speciality-id", required=True)
    args = p.parse_args()

    mgr = get_session_manager()
    mgr.load_user_cookies_file(args.user_id, args.cookies)
    svc = mgr.get_course_service(args.user_id)

    if args.cmd == "subjects":
        print(json.dumps(svc.list_subjects(), ensure_ascii=False, indent=2))
    elif args.cmd == "courses":
        print(json.dumps(svc.list_courses(args.speciality_id), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

## Video Progress — Site-Specific Calibration

This is the most fragile part. Sites detect "fake watching" by:

- Comparing `play_time` increase vs wall-clock time (must look natural)
- Requiring a `recordPlayTime` checkpoint at fixed intervals
- A final `is_complete=1` call with a plausible `play_time` equal to the video duration

Pattern that has worked in practice (tunable):

```python
import time

def watch_video(study_svc, project_id, study_id, duration_sec, step=30, interval=31):
    """Report progress every `interval` real seconds, claim `step` simulated seconds.
    The frontend usually polls every 30s, hence step=30 + interval=31 (1s slack)."""
    play_time = 0
    while play_time < duration_sec:
        play_time = min(play_time + step, duration_sec)
        is_complete = 1 if play_time >= duration_sec else 0
        study_svc.record_play_time(project_id, study_id, play_time, is_complete)
        if is_complete:
            return
        time.sleep(interval)
```

Tune `step`/`interval` after observing the site's own JS for a real session. If the site enforces `study_time_more`, you went too fast.

## Exam Pattern

```python
def pass_exam(exam_svc, project_id, study_id):
    paper = exam_svc.start(project_id, study_id)
    answers = exam_svc.auto_answer(paper)  # default: pick the only marked correct, fallback to A
    return exam_svc.submit(project_id, study_id, paper["paper_id"], answers)
```

Some sites embed correct answers in the paper JSON (sloppy backend); most require iteration over `paper["questions"]` and matching to a question bank. Start with the lazy path and only build a question bank if the site doesn't leak answers.

## Credit Application Pattern

If the site requires a course evaluation before credit can be applied (the `-6` case in shuangwei), bake that retry into the service:

```python
def apply_credit(self, project_id, auto_survey=True):
    preview = self.client.form_post("/member/creditMsg", {"project_id": project_id})
    if not preview.get("can_apply"):
        return ApiResponse(ok=False, raw=preview, message=preview.get("msg", "cannot apply"))
    result = self.client.form_post("/member/requestCredit", {"project_id": project_id})
    if result.get("message_code") == "-6" and auto_survey:
        self.client.form_post("/projecteva/saveEva", {"project_id": project_id, "score": 5, ...})
        result = self.client.form_post("/member/requestCredit", {"project_id": project_id})
    return parse_member_response(result)
```

## Writing `API_REFERENCE.md`

Layout:

```markdown
# <pkg> API Reference

## CourseService
### list_subjects()
- Endpoint: POST /subject/list (form)
- Response: { "result": "ok", "msg": [{...}] }
- Failure: msg = "-1" → not logged in
### list_courses(speciality_id)
...
```

One section per service, one sub-section per method. Include real (sanitized) response samples.

## End-of-phase Report

1. Domains implemented (checkboxes vs `docs/API_REQUIREMENTS.md`).
2. Notable site-specific quirks (e.g. "video needs `recordPlayTime` every 30s exactly").
3. Anything skipped and why, including optional capabilities not selected and mandatory-if-present flows not found.
4. Ask: "OK to enter phase 3 (stability + retry)?"

## Pitfalls Observed In The Wild

- **Silent 200 with `result=error`**: many sites never return HTTP 4xx; rely on `result` field, not status code.
- **`msg` is sometimes a JSON-encoded string**: parse twice (e.g. `{"study_abnormal":"study_time_more"}`).
- **Form vs JSON**: AJ-Captcha endpoints are JSON, business endpoints are usually form. Mixing breaks silently.
- **`Content-Type` matters**: some sites reject the body if `charset=UTF-8` is missing.
- **Trailing `;`/`,` in cookies**: don't manually join — let `requests.Session` manage them.
