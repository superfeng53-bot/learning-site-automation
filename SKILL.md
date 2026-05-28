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
6. **Don't try to finish in one shot**: split work across phases + specs. **Read `cursor-agent-playbook.md`** before phase 1 for handoff files, New Chat boundaries, sub-agents, and other skill/MCP usage.

## Cursor Agent Playbook (read before phase 1)

**Full detail:** `cursor-agent-playbook.md`

| When | Action |
|------|--------|
| End of each phase | Write `docs/handoffs/PHASE<N>_*.md`; offer user **New Chat** with「新对话启动语」 |
| Phase 1 → 2 | Strongly suggest New Chat (browser capture bloat) |
| Phase 2, every 2 domains | Mid-phase handoff + optional New Chat |
| Phase 5 backend → UI | New Chat before generating `index.html` |
| Mid-phase pressure | Read >8 files OR >15 edits OR one file >600 LOC → stop & handoff |

**Phase 1–2 analysis:** use **`Task` sub-agents** + **`cursor-ide-browser` MCP** for site/API recon; parent agent merges into `docs/LOGIN_FLOW.md` / `API_REFERENCE.md`. See playbook §3.

**Phase 5:** Web UI per **`web-ui-spec.md`** (简体中文 + 复制日志); Excel per **`excel-spec.md`** + **`spreadsheet` skill**.

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
| Phase 5 web UI | Pure presentation | `index.html` per `web-ui-spec.md` + verification checklist |
| Phase 5 FastAPI | After store stable | `web/app.py` per `web-ui-spec.md` §8 + `excel-spec.md` |
| Phase 5 Excel | Formatting rules | Template/export xlsx under `spreadsheet` skill + `excel-spec.md` |
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
│   ├── handoffs/              # PHASE<N>_*.md — Cursor context handoffs
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
- `sqlite3` (WAL), `openpyxl` — import/export per **`excel-spec.md`** (中文文件名与表头)
- `pyinstaller`; optional LLM for subject mapping

## Operator-facing Chinese requirements (fixed)

These apply to every generated project unless the user explicitly opts out:

| Surface | Rule |
|---------|------|
| Web 控制台 | 全部简体中文；见 `web-ui-spec.md` §0 |
| Excel 模板 | 文件名 `{平台}账号模板.xlsx`；sheet/表头中文；见 `excel-spec.md` §2 |
| Excel 导出 | 前部列与导入模板完全一致；状态/日志等追加在后；见 `excel-spec.md` §3 |
| 复制日志 | 失败/重试账号一键复制 `error_log_text`；见 `web-ui-spec.md` §4.12 + `excel-spec.md` §4 |

## Captcha Decision Tree (site-specific tweak point)

| Site captcha kind | Detect by | Use |
|-------------------|-----------|-----|
| Click-word / point-touch | `wordList`, `originalImageBase64` | `ddddocr` det + OCR; AES-ECB |
| Slider | `bg`/`tile`, track | `ddddocr.slide_match` |
| Plain char OCR | single captcha `<img>` | `ddddocr.classification` |
| SMS / face / passkey | biometric / SMS gate | **stop and ask the user** |

## When to Call AskQuestion

At most three times across the whole run:

1. Start — missing inputs (1)–(4)
2. End of phase 1 — captcha kind ambiguous
3. End of phase 4 — continue to phase 5 or stop

## Anti-Patterns to Avoid

- Do NOT use Selenium/Playwright at runtime (browser MCP = recon only)
- Do NOT finish phases 1–5 in one chat without handoff files
- Do NOT paste large browser JSON into chat — write `docs/` files
- Do NOT use English UI labels or English Excel headers
- Do NOT reorder export columns relative to import template
- Do NOT use emoji in UI text; use plain Chinese labels
- Do NOT skip `ui.confirm` / `ui.toast` patterns in web UI

## Auxiliary Resources In This Skill

- `cursor-agent-playbook.md` — **Cursor orchestration**: context handoff, New Chat, sub-agents, MCP, other skills
- `web-ui-spec.md` — phase-5 web console (中文 UI, 复制日志, no HTML template)
- `excel-spec.md` — 中文模板/导出列对齐, `error_log_text`
- `phase1-login-recon.md` … `phase6-packaging.md` — per-phase detail (read only when entering that phase)
- `templates/requirements.md`, `templates/account.json`, `templates/project-skeleton.md`
- `scripts/init_project.py`, `scripts/captcha_probe.py`

Read phase files and specs **only when entering that phase/sub-task**. Do not preload everything.
