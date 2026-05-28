# Phase 2 — Business API Toolkit

Goal: wrap each business endpoint the site exposes (course listing, joining, video progress, exam submission, credit application, member info, recharge, etc.) into thin `<pkg>/*.py` service classes, each operating on a shared `HttpClient`. Produce `<pkg>/API_REFERENCE.md` that future phases will read.

## Definition of Done

- [ ] One `*Service` class per business domain, each owning its endpoints
- [ ] One `cli_*.py` per service, runnable via `python -m <pkg>.cli_<name>`
- [ ] `<pkg>/API_REFERENCE.md` lists every endpoint: method, path, params, sample response, failure codes
- [ ] Every service uses the shared `HttpClient` (no ad-hoc `requests.post` calls)
- [ ] All failure paths return a `SwwResponse`-shaped dataclass (or equivalent) with `ok / message / code / hint / raw`

## Discovery Loop (repeat for each domain)

**Cursor 编排**：每个 domain 单独一轮——先用 **`cursor-ide-browser` MCP**（内置浏览器，playbook §1.1）+ `Task explore` 或 `api-recon` subagent → `docs/api-discovery/<domain>.md`，再 `Task generalPurpose` 实现 `*Service`。每完成 **2 个 domain** 写 `docs/handoffs/PHASE2_<domains>_done.md` 并建议用户 **New Chat**。详见 playbook §3、§5。

1. **Browse with the test account** using **`cursor-ide-browser` MCP** (not external automation), perform the action manually
2. Capture the network calls via `browser_cdp Network.enable` and `Network.requestWillBeSent` / `responseReceived`. Use `Network.getResponseBody` for response shapes you cannot read from the snapshot
3. Note: request body (form vs JSON), required headers, response codes
4. After browser recon is written to `docs/api-discovery/<domain>.md`, optionally use **`shell` skill** / a tiny `curl` script with `data/cookies.json` to confirm parity (do not use this step to *discover* endpoints)
5. Confirm parity with browser behaviour
6. Promote the script into a service method

Do this for each of the domains below in roughly this order.

## Canonical Domains (skip any irrelevant ones)

| Domain | Typical endpoints | File |
|--------|-------------------|------|
| Course catalog | `/course/list`, `/course/detail`, `/subject/list` | `course.py` |
| Join / enroll | `/study/join`, `/member/join` | `study.py` (join section) |
| Video progress | `/study/recordPlayTime`, `/study/progress` | `study.py` |
| Exam | `/exam/start`, `/exam/submit`, `/exam/result` | `exam.py` |
| Credit application | `/member/creditMsg`, `/member/requestCredit`, `/projecteva/saveEva` | `credit.py` |
| Member / profile | `/member/balance`, `/member/projects`, `/member/info` | `member.py` |
| Recharge | `/card/recharge`, `/recharge/...` | `recharge.py` |

## Service Class Pattern

Every service follows the same shape:

```python
from .client import HttpClient
from .responses import ApiResponse, parse_member_response


class CourseService:
    def __init__(self, client: HttpClient):
        self.client = client

    def list_subjects(self) -> list[dict]:
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

1. Domains implemented (checkboxes vs canonical table above).
2. Notable site-specific quirks (e.g. "video needs `recordPlayTime` every 30s exactly").
3. Anything skipped and why.
4. Ask: "OK to enter phase 3 (stability + retry)?"

## Pitfalls Observed In The Wild

- **Silent 200 with `result=error`**: many sites never return HTTP 4xx; rely on `result` field, not status code.
- **`msg` is sometimes a JSON-encoded string**: parse twice (e.g. `{"study_abnormal":"study_time_more"}`).
- **Form vs JSON**: AJ-Captcha endpoints are JSON, business endpoints are usually form. Mixing breaks silently.
- **`Content-Type` matters**: some sites reject the body if `charset=UTF-8` is missing.
- **Trailing `;`/`,` in cookies**: don't manually join — let `requests.Session` manage them.
