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
| 2 | Wrap each business endpoint (course / video / exam / credit / member / recharge) | `<pkg>/course.py`, `study.py`, ... + `API_REFERENCE.md` | `phase2-api-tools.md` |
| 3 | Session reuse, error classification, retry policy | `session_manager.py`, `responses.py`, `captcha_limiter.py` | `phase3-stability.md` |
| 4 | End-to-end single-account runner | `course_runner.py` + `run_course.py` entry | `phase4-end-to-end.md` |
| 5 | Multi-account SQLite scheduler + FastAPI web console | `<svc>/orchestrator.py`, `worker.py`, `apply_worker.py`, `web/app.py` | `phase5-service.md` |
| 6 | One-click start, single-file build, CI | `start.sh`, `build.sh`, `scripts/build.py`, `.github/workflows/ci.yml` | `phase6-packaging.md` |

## Hard Workflow Rules

1. **Phase gate**: at the end of every phase you MUST stop, summarize what was built, and ask the user to confirm before starting the next phase. Each phase has a "Definition of Done" checklist inside its detail file — read it before announcing completion.
2. **Read the phase file before acting**: each phase has its own `phaseN-*.md` with concrete commands, code patterns, and pitfalls. Read it once at the start of that phase using the `Read` tool with the absolute path shown in the table above.
3. **Do not skip phases** unless the user explicitly says so (e.g. "我只要 API 工具，不要常驻服务" → stop after phase 4).
4. **Preserve site-specific knowledge in code, not in this skill**: every site differs in captcha kind, response shape, anti-bot tricks. The skill is a scaffold, not a copy-paste template.
5. **Never commit the test account**: add `data/`, `.run/`, cookies, and account JSONs to `.gitignore` in phase 1.

## Initial Project Layout (used from phase 1 onward)

```
<project_root>/
├── <pkg>/                     # HTTP toolkit (login, captcha, services, CLIs)
│   ├── __init__.py
│   ├── client.py
│   ├── captcha.py
│   ├── login.py
│   ├── session_manager.py
│   ├── responses.py
│   └── cli_*.py
├── <svc>/                     # Always-on service (phase 5+)
│   ├── orchestrator.py
│   ├── worker.py
│   ├── apply_worker.py
│   ├── persistence/store.py
│   └── web/app.py + templates/index.html
├── docs/
│   ├── LOGIN_FLOW.md          # produced in phase 1
│   └── 通用需求说明.md          # adapted from templates/requirements.md
├── data/                      # cookies, account JSON (gitignored)
├── .run/                      # SQLite, locks, AI config (gitignored)
├── scripts/                   # build / start helpers
├── run_course.py              # single-account entry (phase 4)
├── run_service.py             # service entry (phase 5)
├── start.sh / start.bat       # phase 6
├── build.sh / build.bat       # phase 6
├── requirements.txt
└── README.md
```

Use `scripts/init_project.py` (inside this skill) to generate the empty skeleton + `.gitignore` + `requirements.txt` in one shot. See `phase1-login-recon.md` for the exact invocation.

`<pkg>` and `<svc>` are placeholders — replace with concrete names derived from the site (e.g. `sww_api` + `sww_service` for 双卫网). Ask the user once if not obvious.

## Canonical Tech Stack (battle-tested, do not deviate without reason)

- Python 3.9+
- `requests` for HTTP, `requests.Session` per user for cookie isolation
- `ddddocr` for captcha (text-click / slider / char) — see phase 1 for which mode
- `pycryptodome` for AES (most captchas need ECB+PKCS7 with a per-request `secretKey`)
- `fastapi` + `uvicorn` + a single inlined `index.html` for the web console
- `sqlite3` (WAL mode) for persistence — schema in `phase5-service.md`
- `openpyxl` for Excel import/export
- `pyinstaller` for single-file build
- Optional: `zhipuai` / OpenAI-compatible LLM for any classification step (subject mapping, etc.)

## Captcha Decision Tree (site-specific tweak point)

In phase 1, identify which family the site uses, then pick the matching helper in `scripts/captcha_probe.py`:

| Site captcha kind | Detect by | Use |
|-------------------|-----------|-----|
| Click-word / point-touch (AJ-Captcha, NetEase Yidun-clickword) | `wordList` field, `/captcha/get` returning `originalImageBase64` | `ddddocr.DdddOcr(det=True)` for detection + `DdddOcr()` for OCR; AES-ECB on `(token---pointJson)` |
| Slider (Yidun slide / Geetest3 slide) | `bg`/`tile` images, `track` data | `ddddocr.slide_match(target, background)` + humanized track curve |
| Plain char OCR (4-6 letters/digits image) | a single `<img src="...captcha">` | `ddddocr.classification(img_bytes)` |
| SMS / face / passkey | login response with `phoneFormat=1`, biometric prompt | **stop and ask the user** — out of scope for unattended automation |

If you can't classify on first browser look, capture the captcha-related network call in phase 1 and paste it into chat before guessing.

## When to Call AskQuestion

Use `AskQuestion` at most three times across the whole 6-phase run:

1. At the very start if any of the 4 required inputs is missing.
2. At end of phase 1 if captcha kind is ambiguous (show the 4 captcha-family options).
3. At end of phase 4 to confirm: continue to phase 5 (always-on service) or stop here.

Beyond those, just announce the phase boundary in chat and ask for a free-form confirm.

## Anti-Patterns to Avoid

- Do NOT use Selenium/Playwright in the runtime. Browser is **only** for phase-1 reconnaissance. Production must be pure `requests`.
- Do NOT hard-code one captcha solver path. Always wrap captcha in a class with retry + cooldown — see `phase3-stability.md` for `captcha_limiter` pattern.
- Do NOT mix login retries with business retries. Login uses captcha-bounded retry; business calls use exponential backoff + session-expired detection.
- Do NOT bake the test credentials anywhere outside `data/account.json` (and that file must be in `.gitignore`).
- Do NOT generate emoji-laden UI text; the canonical console template uses plain Chinese labels.

## Auxiliary Resources In This Skill

- `templates/requirements.md` — generic "always-on service requirements" doc; adapt for the site in phase 5.
- `templates/account.json` — minimal credentials JSON shape (also produced by `init_project.py`).
- `templates/project-skeleton.md` — annotated tree of every file the bootstrap should produce.
- `templates/web-ui-template.html` — minimum-viable FastAPI single-page console (no third-party UI libs).
- `scripts/init_project.py` — one-shot scaffolder. Run: `python <skill>/scripts/init_project.py --root <project_root> --pkg <pkg_name> --svc <svc_name> --site-url <url>`.
- `scripts/captcha_probe.py` — quick local helper: feed a captcha image bytes + kind, prints what ddddocr sees. Useful in phase 1.

Read each phase file only when you actually enter that phase. Do not preload them.
