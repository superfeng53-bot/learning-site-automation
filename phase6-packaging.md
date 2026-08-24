# Packaging Spec — One-Click Start, Single-File Build, CI

**Not part of Goal mode.** Cursor Goal (this skill) ends at Phase 5. This file is the **host-agnostic** spec for the packaging agent (`templates/agents/packaging.md`). Any coding agent (Cursor, Claude Code, Codex, …) runs it **on the target OS** after Phase 5. In a generated project the copy lives at `docs/packaging/SPEC.md`.

Do **not** use Cursor-only orchestration: no `CreateGoal`, no New Chat, no browser MCP, no `AskQuestion`, no `rename_chat`, no babysit/PR skills. Shell + Python + this spec are enough.

Goal: make the project trivial for non-developers. Double-click → service runs and browser opens. Plus a single `.exe` / mac binary, plus optional CI that catches import-time regressions.

## Gate — 开发态通过 ≠ 打包通过

**硬性规则**：阶段 1–5 全部 `pass`（含 `python run_service.py`、Web UI、Excel）**不能**宣布打包完成。PyInstaller 单文件有独立的运行时路径、资源打包、动态 import 问题，**必须在打包产物上单独验收**。

| 验收面 | 能否替代打包 smoke |
|--------|-------------------|
| 阶段 5 `./start.sh` / venv 内 `run_service.py` | ❌ 不能 |
| CI `import <pkg>; import <svc>` | ❌ 不能（未走 PyInstaller） |
| `scripts/smoke_frozen.py` **pass** | ✅ 打包验收的权威依据 |
| 手动等效步骤（见 §Packaged Artifact Smoke Test）+ `PHASE6_REPORT` 证据 | ✅ 仅当脚本暂不可用时；须逐项等价 |

**禁止**：`build.sh` 成功生成 `dist/` 文件但未跑打包 smoke 就勾选 DoD；禁止用「源码 import 绿」代替「frozen 可运行」。

## Definition of Done

- [ ] `start.sh` (POSIX) and `start.bat` (Windows) create `.venv`, install deps, run `run_service.py` — **一键启动**（双击即可，无需手动 `pip`）
- [ ] `run_service.py` 满足 phase5「Service Entry」：单实例、**二次启动只打开已有 WebUI**、端口避让、`endpoint.json`；**顶层** `except` 在 frozen 下 `traceback.print_exc()` + `input("按 Enter 退出…")`，避免 console 闪退
- [ ] `build.sh` / `build.bat` produce a **single-file** binary in `dist/` with naming `<平台中文名>_<MM>_<DD>` (e.g. `双卫网_04_22.exe`) — **月、日** 两位，构建日当天
- [ ] PyInstaller **onefile**：`ddddocr` ONNX、FastAPI 模板、`uvicorn` hiddenimports 全部打进包；目标机**无需安装 Python** 即可运行
- [ ] 打包产物 `console=True`：**保留终端窗口**输出 uvicorn/报错（禁止 `console=False` / windowed 无控制台）
- [ ] **`scripts/smoke_frozen.py` 存在**（自 `templates/code/scripts/smoke_frozen.py` 复制），且 `./build.sh` 成功后**自动调用**；单独执行 `python scripts/smoke_frozen.py` **exit 0**
- [ ] 打包 smoke **在隔离临时目录**跑通（模拟「复制到另一目录」）：`GET /api/health` → 200 + `ok:true`；`GET /` → 200；`GET /api/config` → 200；`.run/`、`data/` 在 exe **同目录**创建
- [ ] 首次运行打包 exe：自动打开浏览器；**再次双击 exe**：只打开已有控制台 URL，不启动第二进程
- [ ] 将 `dist/` 内单文件复制到**另一台电脑或另一目录**运行：`data/`、`.run/` 在 exe 同目录创建，Web 可访问（`smoke_frozen.py` pass 即覆盖「另一目录」；跨机器仍建议抽测一次）
- [ ] `.github/workflows/ci.yml` runs lint + import smoke test on push/PR（**不**替代打包 smoke）
- [ ] `README.md` has install, run, build, layout sections；含「打包后验收：`python scripts/smoke_frozen.py`」
- [ ] `pyproject.toml` declares dependencies + metadata

## start.sh

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
python run_service.py "$@"
```

## start.bat

```bat
@echo off
cd /d "%~dp0"

if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python run_service.py %*
```

Both should be marked executable (`chmod +x start.sh`).

## build.sh / build.bat

Both delegate to `python scripts/build.py`, which does the platform-specific PyInstaller invocation.

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .build-venv 2>/dev/null || true
source .build-venv/bin/activate
pip install -q -r requirements.txt -r requirements-build.txt
python scripts/build.py "$@"
```

## scripts/build.py

```python
import argparse, datetime, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_NAME = "双卫网"  # replace per project

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clean", action="store_true")
    args = p.parse_args()

    if args.clean:
        for d in ("build", "dist"):
            shutil.rmtree(ROOT / d, ignore_errors=True)

    today = datetime.datetime.now()
    suffix = f"{today.month:02d}_{today.day:02d}"
    binary_name = f"{SITE_NAME}_{suffix}"

    spec_template = (ROOT / "scripts" / "shuangwei.spec.template").read_text(encoding="utf-8")
    spec = spec_template.replace("{{BINARY_NAME}}", binary_name)
    spec_path = ROOT / "scripts" / f".{binary_name}.spec"
    spec_path.write_text(spec, encoding="utf-8")

    subprocess.check_call([sys.executable, "-m", "PyInstaller",
                           "--clean", "--noconfirm", str(spec_path)])
    ext = ".exe" if sys.platform == "win32" else ""
    binary_path = ROOT / "dist" / f"{binary_name}{ext}"
    print(f"\nBuilt: {binary_path}")

    # ── 打包后 mandatory smoke（失败则 build 整体失败）────────────────────
    smoke = ROOT / "scripts" / "smoke_frozen.py"
    if smoke.is_file():
        print("\nRunning packaged artifact smoke test …")
        subprocess.check_call([sys.executable, str(smoke), "--binary", str(binary_path)])
    else:
        raise SystemExit(
            "缺少 scripts/smoke_frozen.py — 从 templates/code/scripts/ 复制。"
            "未通过打包 smoke 不得宣布打包完成。"
        )

if __name__ == "__main__":
    main()
```

## scripts/<site>.spec.template (PyInstaller spec)

```python
# {{BINARY_NAME}}
from PyInstaller.utils.hooks import collect_data_files
import os

block_cipher = None

a = Analysis(
    ['../run_service.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../<svc>/web/templates', '<svc>/web/templates'),
        *collect_data_files('ddddocr'),
    ],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        # zoneinfo tz database — Windows has no system tz db; without tzdata,
        # ZoneInfo("Asia/Shanghai") raises and Excel import / year defaults fail
        'tzdata', 'tzdata.zoneinfo',
    ],
    hookspath=[], runtime_hooks=[], excludes=[],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='{{BINARY_NAME}}',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None,
    console=True,  # keep console for log visibility
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
```

Critical bits:

1. `datas` MUST include the FastAPI HTML template (PyInstaller doesn't auto-discover).
2. `collect_data_files('ddddocr')` pulls in the ONNX models.
3. `hiddenimports` for uvicorn dynamic imports.
4. `console=True` **mandatory** — 打包后必须有终端窗口持续显示运行日志；非开发用户可复制报错。禁止改为无控制台 windowed 模式。
5. **onefile only** — 交付物是单个 `.exe` / 单个 macOS 可执行文件，不要把 `dist/<name>/` 文件夹当最终交付（除非用户明确要求目录版）。

## Packaged Artifact Smoke Test（blocking gate）

**目的**：在 PyInstaller 单文件上验证 uvicorn 起服、模板可读、SQLite/`endpoint.json` 路径正确。源码 venv 跑通**证明不了**这些。

### 脚本

复制 `templates/code/scripts/smoke_frozen.py` → `scripts/smoke_frozen.py`。逻辑概要：

1. 取 `dist/` 最新单文件（或 `--binary` 指定）
2. **复制到** `tempfile.mkdtemp()` 隔离目录（不污染仓库 `data/`）
3. 以 `--no-browser` 启动，轮询 `.run/service/endpoint.json`（默认 90s）
4. HTTP 探测：`/api/health`、`/api/config`、`/` 均 200
5. **Excel 导入探测**：先 `POST /api/scheduler/pause`，再上传一行假账号的最小 xlsx 到 `/api/accounts/upload`——覆盖 `zoneinfo("Asia/Shanghai")` 路径（Windows 缺 `tzdata` 时导入全挂但 health 正常，是该脚本的已知盲区，此步专防）
6. 断言 exe 同目录存在 `.run/service/service.lock`、`data/`
7. 进程仍存活；失败时打印 stdout 尾部并 exit 1

```bash
# build 后自动跑（build.py 内 check_call）
./build.sh

# 或单独重跑（改 spec / 修 hiddenimports 后）
python scripts/smoke_frozen.py
python scripts/smoke_frozen.py --binary dist/双卫网_04_22.exe --keep-temp
```

### 手动等效（仅当脚本环境不可用时）

在 `PHASE6_REPORT.md` 逐条记录等价证据：

| 步骤 | 预期 |
|------|------|
| 复制 `dist/*` 到 `/tmp/frozen-test/` | 仅单文件，无 `.venv` |
| 双击或 CLI 启动 | console 窗口保留，无 import / ModuleNotFound  traceback |
| 浏览器打开控制台 | 简体中文 UI，非 500/空白 |
| exe 旁出现 `data/`、`.run/service/endpoint.json` | 路径不在 `_MEIPASS` 内 |
| `curl -s http://127.0.0.1:<port>/api/health` | `{"ok":true,...}` |
| 不退出，再双击 exe | 只开浏览器，进程数不变 |

**任一失败**：打包 DoD 为 `fail`，修 spec / `runtime.project_root()` / `datas` / `hiddenimports` 后重跑 `./build.sh`，直至 `smoke_frozen.py` pass。

### run_service.py 冻结态错误可见性

在 `if __name__ == "__main__"` 外包一层，避免 Windows 上 console 一闪而过：

```python
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("启动失败，按 Enter 退出…")
        raise
```

## `requirements-build.txt`

```
pyinstaller>=6.0
```

## `requirements.txt` (canonical minimum)

```
requests>=2.31
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.5
ddddocr>=1.4.11
pycryptodome>=3.20
pillow>=10.0
openpyxl>=3.1
tzdata>=2024.1    # required on Windows: zoneinfo("Asia/Shanghai") fails without it
zhipuai>=2.0    # only if AI mapping is used
```

Pin to ranges (>=), not exact versions, so the venv on the user's machine resolves cleanly.

## `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: install
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install ruff
      - name: lint
        run: ruff check .
      - name: import smoke
        run: |
          python -c "import <pkg>; import <svc>; import <svc>.web.app"
```

Don't try to run integration tests in CI — they need real credentials and network access to the third-party site.

**CI 与打包 smoke 分工**：CI 只防「源码 import 回归」；**PyInstaller 产物验收只在本地/构建机**跑 `smoke_frozen.py`（或 Windows/macOS 构建 agent 上等价步骤）。不要在 CI 里强绑 PyInstaller（耗时长、平台差异大），但 **宣布打包完成前本地 smoke 必须 pass**。

## `pyproject.toml` minimum

```toml
[project]
name = "<project_name>"
version = "0.1.0"
description = "<one line>"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.31",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "ddddocr>=1.4.11",
    "pycryptodome>=3.20",
    "pillow>=10.0",
    "openpyxl>=3.1",
]

[project.urls]
Homepage = "https://github.com/<user>/<repo>"

[tool.ruff]
line-length = 100
target-version = "py39"
```

## README.md outline

```markdown
# <project_name>

<one-line summary>

## 一键启动
- Windows: 双击 start.bat
- macOS / Linux: ./start.sh

## 命令行
pip install -r requirements.txt
python run_service.py

## 打包
./build.sh    # macOS / Linux；成功后自动跑 smoke_frozen
build.bat     # Windows

### 打包验收
```bash
python scripts/smoke_frozen.py   # 单独重跑；须 exit 0
```
开发态 `./start.sh` 通过不能代替上述命令。

## 目录结构
... (the tree from SKILL.md)

## CLI 常用命令
... (a few cli_*.py examples)

## 免责声明
仅供学习与研究。使用自动化访问第三方平台时请遵守平台条款与法律法规。
```

## .gitignore (set in phase 1, double-check now)

```
.venv/
.build-venv/
__pycache__/
*.pyc
build/
dist/
*.spec
.run/
data/
!data/.gitkeep
*.log
.DS_Store
```

`data/.gitkeep` ensures the empty data folder still appears in fresh clones.

## End-of-phase Report

**顺序**：先 `./build.sh`（含 smoke）→ 再填 `PHASE6_REPORT.md`。任一 smoke 失败则打包 **未完成**。

1. Confirm `./start.sh` works on a clean clone (`rm -rf .venv data/cookies.json && ./start.sh`).
2. **二次启动**：服务仍在运行时再执行 `./start.sh`（或再双击 exe）→ 仅打开浏览器，任务管理器里仍只有一个服务进程。
3. Confirm `./build.sh` produces `dist/<平台>_<MM>_<DD>.exe` (or mac binary); filename matches build date.
4. Confirm **`python scripts/smoke_frozen.py` exit 0** — 粘贴终端 `[smoke] PASS` 行到 `PHASE6_REPORT.md`；若 fail，附 stdout 尾部与修复项（spec `datas` / `hiddenimports` / `project_root`）。
5. Run the binary from a **different directory** or copy to another machine; confirm `.run/`、`data/` beside the exe and Web UI loads（步骤 4 pass 已覆盖「另一目录」；跨机器抽测记入 report）。
6. Confirm packaged app shows a **console window** with live logs while running.
7. Confirm CI passes (push to branch, wait for green) — **import smoke only，不替代步骤 4**。
8. Project is shippable. Suggest the user: rename remote `<user>/<repo>` in `pyproject.toml` and `README.md`, commit, push.

## Pitfalls

- **「前面都过了，一打包就挂」**：最常见 — 未跑 `smoke_frozen.py` 就宣布完成。Fix：按 §Packaged Artifact Smoke Test 修 spec/路径后重 build。
- **PyInstaller misses ONNX models**: confirm `collect_data_files('ddddocr')` covers the runtime; if not, manually add the model `.onnx` paths to `datas`. 症状：首次登录/验证码时报找不到 `.onnx`。
- **PyInstaller misses FastAPI template**: `GET /` 500 或空白。Fix：`datas` 含 `('<svc>/web/templates', '<svc>/web/templates')`，且 `app.py` 里 `templates` 路径基于 `project_root()` 或可 import 的包路径。
- **Binary writes to wrong directory**: `runtime.project_root()` must check `sys.frozen` and use `Path(sys.executable).parent` when frozen — otherwise SQLite gets created in PyInstaller's `_MEIPASS` and is wiped on next launch. smoke 可能仍短暂 pass（内存态），重启丢数据。
- **uvicorn / stdlib hiddenimports**: 症状 `ModuleNotFoundError: uvicorn.loops.auto`。Fix：补 spec `hiddenimports`（见上文模板）。
- **zoneinfo 时区库缺失（Windows 必踩）**: 症状 `ZoneInfoNotFoundError: No time zone found with key Asia/Shanghai`，Excel 导入/目标年度默认值全挂，但 `/api/health` 正常、smoke 可能照常 PASS（盲区）。Windows 没有系统时区库，`zoneinfo` 依赖 pip 包 `tzdata`。Fix：`requirements.txt` 加 `tzdata>=2024.1` + spec `hiddenimports` 加 `'tzdata', 'tzdata.zoneinfo'`。注意开发态 venv 也可能缺（该路径未触发时静默），构建 venv 与开发 venv 都要装。
- **Console window closes immediately on error**: keep `console=True`, add frozen 顶层 `except` + `input()`（见 §Packaged Artifact Smoke Test）。
- **macOS Gatekeeper**: unsigned binaries trigger a "cannot be opened" dialog. Document `xattr -d com.apple.quarantine <binary>` as the workaround.
- **CI on Windows or macOS**: avoid unless really needed. The smoke test is import-only, ubuntu is enough — **本地打包 smoke 仍是硬性门禁**。
