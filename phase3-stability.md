# Phase 3 — Stability, Session Reuse, Retry Policy

Goal: make the toolkit resilient to (a) session expiry, (b) transient network errors, (c) captcha rate-limiting, and (d) site-side anti-abuse soft errors. Add three modules: `session_manager.py`, `captcha_limiter.py`, and tighten `client.py`.

**Goal 编排**：由 **Phase 3 工人**一次做完。禁止 New Chat；禁止开始 Phase 4 / 打包。

## Definition of Done

- [ ] `SessionManager` provides per-`user_id` `HttpClient` instances (cookie isolation)
- [ ] `SessionManager.ensure_session(user_id, username, password, cookies, probe)` returns `(reused_token, cookies, user_info, error)` — Token reuse path skips fresh login when probe succeeds
- [ ] `captcha_limiter` enforces a global cooldown + per-username login lock + recognition-failure backoff
- [ ] `client.py` has `form_post_safe` / `json_post_safe` with bounded retries (3-4 attempts, exponential backoff, jitter)
- [ ] Login retry vs business retry are clearly separated (login is captcha-bounded, business uses session-expired detection + relogin)
- [ ] `responses.py` has an `is_session_expired(exc_or_msg)` helper that all callers use

## Read First

Read `docs/API_REQUIREMENTS.md` before adding service factories or probes. Session reuse is mandatory, but domain-specific helpers must match the confirmed Phase 2 scope:

- Always provide factories for mandatory services that were implemented (`member`, `course`, `study`, `exam` when the site has exams, and `credit` when the site has credit application).
- Provide optional factories (`recharge`, `registration`, subject-specific service, or other site-specific services) only when the user selected that capability in Phase 2.
- Pick the cheapest authenticated probe from the confirmed mandatory surface. Prefer account/profile or course list; use subject list only if `学科列表 / 分类列表` is selected or the site exposes it as the cheapest stable probe.

## Module 1 — `client.py` retry primitives

The base `HttpClient` already exists from phase 1. Add safe variants:

```python
import time
import requests

class HttpClient:
    # ... existing __init__, load_cookies, export_cookies, json_post, form_post ...

    def form_post_safe(self, path, payload, *, attempts=3):
        last = None
        for i in range(attempts):
            try:
                return self.form_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if i + 1 == attempts:
                    break
                time.sleep(2.0 * (2 ** i))  # 2s, 4s, 8s
        raise last

    def form_get_html(self, path, params=None, *, attempts=4):
        # Bounded retry with jittered exponential backoff
        ...
```

Rule of thumb: 3 attempts for write-ish endpoints, 4 for read-ish HTML scrapes. Never retry on HTTP 4xx — those are business failures, retry won't help.

### SSL 证书校验（macOS / 部分 Linux Python）

若运行期出现 `SSLCertVerificationError` / `certificate verify failed`，而浏览器可正常访问站点，在 `config.py` + `client.py` 增加可配置 `SSL_VERIFY`（默认关闭，环境变量可强制开启）。见 **`templates/code/pkg/client_ssl_snippet.md`**。

## Module 2 — `captcha_limiter.py`

Two reasons we need this:

1. The site has its own captcha rate-limit (e.g. `6112` "请求过于频繁") and will lock the whole IP if we hammer it.
2. Even when not rate-limited, ddddocr can fail repeatedly on bad luck; we need a cooldown before trying again so we don't burn captcha gets.

Skeleton (adapted from shuangwei `sww_api/captcha_limiter.py`):

```python
import json, time, threading
from pathlib import Path

CAPTCHA_MAX_ATTEMPTS_PER_LOGIN = 5
GLOBAL_FAILURE_COOLDOWN_SEC = 90
MIN_INTERVAL_SEC = 1.2  # between two captcha attempts

_STATE_FILE: Path | None = None
_LOCK = threading.Lock()
_STATE = {
    "last_attempt_ts": 0.0,
    "cooldown_until": 0.0,
    "consecutive_failures": 0,
}

class CaptchaRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


def configure_state_file(path: Path) -> None:
    """Persist state to disk so all processes share the cooldown."""
    global _STATE_FILE
    _STATE_FILE = path
    if path.is_file():
        try:
            _STATE.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass


def _save() -> None:
    if _STATE_FILE is None:
        return
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(_STATE, ensure_ascii=False), encoding="utf-8")


def get_cooldown_remaining() -> float:
    return max(0.0, _STATE["cooldown_until"] - time.time())


def is_captcha_rate_limited(msg: str | None) -> bool:
    if not msg:
        return False
    text = str(msg)
    keywords = ("过于频繁", "频率过快", "6112", "rate limit", "稍后再试")
    return any(k in text for k in keywords)


def wait_before_captcha(block: bool = True) -> None:
    """Enforce min interval and global cooldown before issuing a captcha get."""
    with _LOCK:
        remaining = get_cooldown_remaining()
        if remaining > 0:
            if block:
                time.sleep(min(remaining, 30))
            else:
                raise CaptchaRateLimitError(f"captcha cooldown: {remaining:.0f}s",
                                            retry_after=remaining)
        gap = time.time() - _STATE["last_attempt_ts"]
        if gap < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - gap)


def mark_captcha_attempt() -> None:
    with _LOCK:
        _STATE["last_attempt_ts"] = time.time()
        _save()


def report_recognition_failure(msg: str) -> bool:
    """Return True if cooldown was triggered."""
    with _LOCK:
        _STATE["consecutive_failures"] += 1
        if _STATE["consecutive_failures"] >= 3:
            _STATE["cooldown_until"] = time.time() + GLOBAL_FAILURE_COOLDOWN_SEC
            _STATE["consecutive_failures"] = 0
            _save()
            return True
        _save()
        return False


def report_recognition_success() -> None:
    with _LOCK:
        _STATE["consecutive_failures"] = 0
        _save()


def report_rate_limited(msg: str, *, cooldown_sec: float = GLOBAL_FAILURE_COOLDOWN_SEC) -> float:
    with _LOCK:
        _STATE["cooldown_until"] = time.time() + cooldown_sec
        _save()
        return cooldown_sec


def format_cooldown_message(remaining: float) -> str:
    return f"验证码冷却中，还需 {remaining:.0f}s"


def state_snapshot() -> dict:
    return dict(_STATE)
```

Wire it into `login.py`:

- Before every `/captcha/get`: `wait_before_captcha()`
- On `/captcha/check` failure: `if is_captcha_rate_limited(msg): report_rate_limited(msg)`
- On 3 consecutive ddddocr misses: `report_recognition_failure(msg)` → trigger cooldown
- On success: `report_recognition_success()`

## Module 3 — `session_manager.py`

Per-user `HttpClient`, login locking, Token reuse with probe:

```python
import threading
from collections.abc import Callable
from .client import HttpClient
from .login import LoginService, LoginResult
from .captcha_limiter import CaptchaRateLimitError, get_cooldown_remaining, format_cooldown_message


class SessionExpiredError(PermissionError):
    pass


def is_session_expired(exc_or_msg) -> bool:
    if isinstance(exc_or_msg, (PermissionError, SessionExpiredError)):
        return True
    text = str(exc_or_msg or "").lower()
    return any(m.lower() in text for m in (
        "未登录", "noLogin", "会话已失效", "cookie 无效", "session expired",
    ))


_username_locks: dict[str, threading.Lock] = {}
_username_locks_guard = threading.Lock()


def _username_login_lock(username: str) -> threading.Lock:
    with _username_locks_guard:
        if username not in _username_locks:
            _username_locks[username] = threading.Lock()
        return _username_locks[username]


class SessionManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._clients: dict[str, HttpClient] = {}

    def get_client(self, user_id: str) -> HttpClient:
        with self._lock:
            if user_id not in self._clients:
                self._clients[user_id] = HttpClient(user_id=user_id)
            return self._clients[user_id]

    def remove(self, user_id: str) -> None:
        with self._lock:
            self._clients.pop(user_id, None)

    def get_member_service(self, user_id): from .member import MemberService; return MemberService(self.get_client(user_id))
    def get_course_service(self, user_id): from .course import CourseService; return CourseService(self.get_client(user_id))
    def get_study_service(self, user_id): from .study import StudyService; return StudyService(self.get_client(user_id))

    # Add only when the capability is confirmed in docs/API_REQUIREMENTS.md.
    def get_exam_service(self, user_id): from .exam import ExamService; return ExamService(self.get_client(user_id))
    def get_credit_service(self, user_id): from .credit import CreditService; return CreditService(self.get_client(user_id))
    def get_recharge_service(self, user_id): from .recharge import RechargeService; return RechargeService(self.get_client(user_id))
    def get_registration_service(self, user_id): from .registration import RegistrationService; return RegistrationService(self.get_client(user_id))

    def login_user(self, user_id, username, password) -> LoginResult:
        remaining = get_cooldown_remaining()
        if remaining > 0:
            return LoginResult(success=False, message=format_cooldown_message(remaining),
                               rate_limited=True, retry_after=remaining)
        with _username_login_lock(username):
            client = self.get_client(user_id)
            return LoginService(client).login(username, password)

    def ensure_session(self, user_id, username, password, cookies=None, *,
                       probe: Callable[[], None] | None = None,
                       require_probe: bool = False) -> tuple[bool, dict, dict | None, str | None]:
        """Returns (reused_token, cookies, user_info, error_message)."""
        if cookies:
            try:
                self.get_client(user_id).load_cookies(cookies)
                if self.get_client(user_id).is_logged_in():
                    if probe is not None:
                        try:
                            probe()
                        except Exception:
                            if require_probe:
                                raise
                    return True, self.get_client(user_id).export_cookies(), None, None
            except Exception:
                pass
        self.remove(user_id)
        result = self.login_user(user_id, username, password)
        if not result.success:
            self.remove(user_id)
            return False, {}, None, result.message
        return False, result.cookies, dict(result.user_info), None


_default: SessionManager | None = None
def get_session_manager() -> SessionManager:
    global _default
    if _default is None:
        _default = SessionManager()
    return _default
```

Key behaviors:

- **Token reuse**: load saved cookies, hit `is_logged_in()`, optionally run a domain-specific `probe()` (e.g. `member_svc.get_profile()` or `course_svc.list_courses()` — proves the session can do real work). If probe throws, fall through to fresh login.
- **Per-username lock**: prevents two threads with the same account from doing concurrent captchas (which both burn ratelimit and confuse the backend).
- **Captcha-cooldown awareness**: refuses login attempts during global cooldown without burning a captcha.

## Retry Decision Matrix (apply everywhere)

| Failure | Action |
|---------|--------|
| `requests.ConnectionError`, `Timeout` | retry up to 3 with exponential backoff |
| `result == "error"`, `msg == "noLogin"` (or equivalent) | call `SessionManager.relogin_user()` once, then retry the call once |
| Captcha `/check` returned rate-limit code | abort login, surface `CaptchaRateLimitError` with `retry_after` |
| Login `msg == "账号或密码错误"` (or `-1`) | DO NOT retry. Return failure to user. |
| Login `msg == "-4"` (captcha expired) | retry up to `max_captcha_retries` |
| Business endpoint returns abnormal-time / anti-cheat marker | abort the run, mark course as `failed`, do not relogin |

Encode this matrix in code via the `is_session_expired()` helper and explicit `if msg in (...)` branches. Do not use blanket `except: retry`.

## Persisted Captcha State

The captcha cooldown should outlive process restarts. Call `configure_state_file(DATA_DIR / "captcha-state.json")` at module import time (e.g. inside `__init__.py` of `<pkg>`). The web app in phase 5 will read `state_snapshot()` to display "captcha cooldown remaining" in the UI.

## End-of-phase Report

1. Token-reuse success rate against the test account (run 5x, count how many skipped fresh login).
2. Captcha cooldown behavior smoke-tested: hit `/captcha/get` 5 times in a row, confirm `wait_before_captcha` kicks in.
3. Files added/changed.
4. Ask: "OK to enter phase 4 (end-to-end runner)?"

## Pitfalls

- **Forgetting to reset `consecutive_failures` on success** → cooldown never lifts even when things are working.
- **State file race condition**: use the in-process lock, don't rely on filesystem atomicity. Persist after every mutation.
- **Per-`user_id` vs per-`username` confusion**: `user_id` is your internal handle (could be `"account_42"`); `username` is the real login phone number. The login lock keys on `username`, the client cache keys on `user_id`.
- **Probe too expensive**: pick the cheapest authenticated GET available (often the subject/category list).
