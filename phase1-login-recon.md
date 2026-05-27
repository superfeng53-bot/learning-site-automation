# Phase 1 — Login Reconnaissance

Goal: produce `docs/LOGIN_FLOW.md` and a working `<pkg>/login.py` that logs in with **pure HTTP requests** (no browser at runtime). Browser MCP is used here for reconnaissance only.

## Definition of Done

- [ ] `docs/LOGIN_FLOW.md` written (frontend flow, login endpoint, success/failure codes, session cookies, captcha sub-flow if any)
- [ ] `<pkg>/captcha.py` solves the site's captcha with `ddddocr` (or stops with a clear error if unsupported kind)
- [ ] `<pkg>/login.py` returns a `LoginResult` dataclass with `success / message / cookies / user_info / hint`
- [ ] `<pkg>/cli_login.py` can log in and dump cookies to `data/cookies.json`
- [ ] `data/account.json` exists and is `.gitignore`d
- [ ] Login succeeds against the user-provided test credentials at least once

## Step 1 — Bootstrap the skeleton

Run the scaffolder once. It creates the project root, `<pkg>/`, `data/`, `docs/`, `.gitignore`, `requirements.txt`, and writes `data/account.json` with the test credentials.

```bash
python ~/.cursor/skills/learning-site-automation/scripts/init_project.py \
  --root <project_root> \
  --pkg <pkg_name> \
  --svc <svc_name> \
  --site-url <site_url> \
  --username <test_username> \
  --password <test_password>
```

If `<pkg_name>` is unclear, derive from the site: e.g. `www.sww.com.cn` → `sww_api`, `www.example.com` → `ex_api`.

## Step 2 — Browser reconnaissance (mcp `cursor-ide-browser`)

Use the **cursor-ide-browser** MCP, not Playwright/Selenium. The browser is a forensics tool, not a runtime.

Workflow:

1. `browser_navigate` to the login URL (omit `position` so user keeps focus)
2. `browser_lock` to claim the tab
3. `browser_snapshot` to read the form's accessibility tree → find input refs for username, password, captcha, submit
4. Enable Network logging with `browser_cdp` `Network.enable`, then `browser_fill` username/password and click captcha trigger
5. Observe network requests:
   - `POST /login` (or equivalent) — note method, content-type, fields
   - Any `/captcha/get`, `/captcha/check`, `/secure/...` calls — note request body and `repData` keys
   - Response shape on success and on intentional wrong password
6. Read `localStorage` and any client UID via `Runtime.evaluate` (`localStorage`, `document.cookie`)
7. Capture the post-login cookie set with `Network.getCookies` or `document.cookie`
8. `browser_lock` action=`unlock`

**Stop conditions** (escalate to user, do not improvise):
- Login requires SMS, face scan, passkey, biometric, or any human-in-the-loop step.
- Captcha is image+audio dual-mode without a pure-image path.
- Login flow involves a redirected SSO on a different domain you haven't been authorized to touch.

## Step 3 — Classify the captcha

Match the site against the table in `SKILL.md`. The four common families and their patterns:

### A. Click-word (AJ-Captcha style)

Symptoms: `POST /secure/captcha/get` returns JSON with `repData.wordList`, `repData.token`, `repData.secretKey`, `repData.originalImageBase64`. Submission: `POST /secure/captcha/check` with `pointJson = AES-ECB-PKCS7(JSON.stringify(points), secretKey)`. Final `captchaVerification = AES(token + "---" + pointJson, secretKey)`.

Solver pattern (drop into `<pkg>/captcha.py`):

```python
import base64, json, time, uuid
from io import BytesIO
import ddddocr
from PIL import Image
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

STD_W, STD_H = 310, 155  # check site's frontend JS for exact std size

def aes_encrypt(plain: str, secret_key: str) -> str:
    cipher = AES.new(secret_key.encode(), AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(plain.encode(), 16))).decode()


class ClickCaptchaSolver:
    def __init__(self):
        self._det = ddddocr.DdddOcr(det=True, show_ad=False)
        self._ocr = ddddocr.DdddOcr(show_ad=False)

    def solve(self, rep_data):
        word_list = rep_data["wordList"]
        img_bytes = base64.b64decode(rep_data["originalImageBase64"])
        img = Image.open(BytesIO(img_bytes))
        img_w, img_h = img.size
        boxes = self._det.detection(img_bytes)
        if len(boxes) < len(word_list):
            raise RuntimeError(f"only {len(boxes)} boxes vs {len(word_list)} words")
        # OCR each box, match to wordList, compute centers, scale to std size
        # see shuangwei sww_api/captcha.py for the full reference impl
        ...

    @staticmethod
    def new_client_uid() -> str:
        return f"point-{uuid.uuid4()}"

    @staticmethod
    def timestamp_ms() -> int:
        return int(time.time() * 1000)
```

### B. Slider

Symptoms: response includes a background image + a small "puzzle piece" image. Slide track must look human (acceleration + brief overshoot).

```python
import ddddocr
det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
res = det.slide_match(target_bytes, background_bytes, simple_target=True)
gap_x = res["target"][0]
# Then synthesize a track: small acceleration, slight overshoot, jitter
```

### C. Plain char OCR

```python
import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)
text = ocr.classification(img_bytes)
```

### D. Unsupported

If face/SMS/passkey is on the critical path, halt and ask the user how to proceed (manual code paste, third-party SMS receiver, or scope cut).

Use `scripts/captcha_probe.py` from this skill as a quick CLI sanity check before wiring into the login flow.

## Step 4 — Write `<pkg>/login.py`

Pattern (the skeleton scaffolder leaves a stub; replace with real flow):

```python
from dataclasses import dataclass, field
from .client import HttpClient
from .captcha import ClickCaptchaSolver, aes_encrypt

@dataclass
class LoginResult:
    success: bool
    message: str
    session_key: str | None = None
    user_info: dict = field(default_factory=dict)
    cookies: dict = field(default_factory=dict)
    raw_response: dict = field(default_factory=dict)
    hint: str = ""
    rate_limited: bool = False
    retry_after: float = 0.0


class LoginService:
    def __init__(self, client: HttpClient, max_captcha_retries: int = 5):
        self.client = client
        self.solver = ClickCaptchaSolver()
        self.max_captcha_retries = max_captcha_retries

    def login(self, username: str, password: str) -> LoginResult:
        last_err = ""
        for attempt in range(self.max_captcha_retries):
            try:
                verification = self._solve()
            except Exception as exc:
                last_err = str(exc); continue
            resp = self.client.form_post("/login", {
                "user_name": username,
                "password": password,
                "captchaVerification": verification,
            })
            if resp.get("result") == "ok":
                return LoginResult(success=True, message="登录成功",
                                   cookies=self.client.export_cookies(),
                                   user_info=resp.get("msg") or {},
                                   raw_response=resp)
            err = str(resp.get("msg", "")).strip()
            if err in ("-4",):  # captcha expired -> retry captcha
                last_err = err; continue
            return LoginResult(success=False, message=err or "登录失败",
                               raw_response=resp,
                               hint=self._hint(err))
        return LoginResult(success=False,
                           message=f"验证码重试{self.max_captcha_retries}次仍失败: {last_err}",
                           hint="检查 OCR 准确度或验证码限频")
```

## Step 5 — Write `docs/LOGIN_FLOW.md`

Required sections:

1. **前端流程** — sequence from "open URL" to "POST login"
2. **登录请求** — method/URL/content-type/fields
3. **成功响应** — JSON shape, sample
4. **失败码表** — every code seen during recon (`-1`, `-2`, ... or whatever the site uses)
5. **登录后 Cookie** — name + meaning of each cookie set
6. **会话检查接口** — how to probe "still logged in?" without re-logging
7. **验证码流程** — full sub-protocol with sample request/response

Use the existing shuangwei `docs/LOGIN_FLOW.md` (in the parent project that birthed this skill) as a layout reference.

## Step 6 — Write `<pkg>/cli_login.py`

A CLI that:
- Loads `data/account.json` by default, or accepts `-u` / `-p` flags
- Calls `LoginService.login()`
- On success, writes `data/cookies.json` (and `data/user_profile.json` optional)
- Has `--check` mode: load existing cookies and verify the session is still alive

```bash
python -m <pkg>.cli_login                     # login with default account, save cookies
python -m <pkg>.cli_login -u 13800000000 -p ********
python -m <pkg>.cli_login --cookies data/cookies.json --check
```

## Step 7 — End-of-phase report

Tell the user:

1. Which captcha family was detected (A/B/C/D).
2. The login endpoint + observed failure codes.
3. A successful login attempt summary (real_name / phone / etc., redacted if sensitive).
4. Files created/changed (paths only).
5. Ask: "OK to enter phase 2 (wrap business endpoints)?"

## Pitfalls Observed In The Wild

- **`-4` after correct captcha**: the site's captcha already expired between `/get` and `/check`. Either reduce the gap, or refresh on `-4`.
- **Captcha rate-limit (`6112` / "过于频繁")**: implement a cooldown like the reference `captcha_limiter.py` — see phase 3.
- **Cookies aren't sticky**: confirm `requests.Session` is being reused; some sites also need a `Referer` header set on the captcha-get call.
- **`isLogin` always returns "noLogin"**: usually means the session cookie name differs (look at `Set-Cookie` from the login response, do not assume `JSESSIONID`).
- **AES key bytes**: `secretKey` is usually utf-8 of a short ASCII string; some sites send it base64-encoded — verify by checking length.
