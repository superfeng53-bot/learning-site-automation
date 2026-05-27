# Phase 6 — One-Click Start, Single-File Build, CI

Goal: make the project trivial for non-developers to use. Double-click → service runs and browser opens. Plus a single `.exe` / mac binary build, plus a minimal CI that catches import-time regressions.

## Definition of Done

- [ ] `start.sh` (POSIX) and `start.bat` (Windows) create `.venv`, install deps, run `run_service.py`
- [ ] `build.sh` / `build.bat` produce a single-file binary in `dist/` with the naming convention `<site>_<DD>_<MM>` (e.g. `双卫网_27_05.exe`)
- [ ] `scripts/build.py` and `scripts/<site>.spec.template` drive PyInstaller; the binary opens browser on launch
- [ ] `.github/workflows/ci.yml` runs lint + import smoke test on push/PR
- [ ] `README.md` has install, run, build, layout sections
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
    suffix = f"{today.day:02d}_{today.month:02d}"
    binary_name = f"{SITE_NAME}_{suffix}"

    spec_template = (ROOT / "scripts" / "shuangwei.spec.template").read_text(encoding="utf-8")
    spec = spec_template.replace("{{BINARY_NAME}}", binary_name)
    spec_path = ROOT / "scripts" / f".{binary_name}.spec"
    spec_path.write_text(spec, encoding="utf-8")

    subprocess.check_call([sys.executable, "-m", "PyInstaller",
                           "--clean", "--noconfirm", str(spec_path)])
    print(f"\nBuilt: dist/{binary_name}{'.exe' if sys.platform == 'win32' else ''}")

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
4. `console=True` keeps the log visible so non-devs can copy errors when something breaks.

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
./build.sh    # macOS / Linux
build.bat     # Windows

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

1. Confirm `./start.sh` works on a clean clone (`rm -rf .venv data/cookies.json && ./start.sh`).
2. Confirm `./build.sh` produces the binary; run it from a different directory; confirm `.run/` and `data/` are created next to the binary.
3. Confirm CI passes (push to branch, wait for green).
4. Project is shippable. Suggest the user: rename remote `<user>/<repo>` in `pyproject.toml` and `README.md`, commit, push.

## Pitfalls

- **PyInstaller misses ONNX models**: confirm `collect_data_files('ddddocr')` covers the runtime; if not, manually add the model `.onnx` paths to `datas`.
- **Binary writes to wrong directory**: `runtime.project_root()` must check `sys.frozen` and use `Path(sys.executable).parent` when frozen — otherwise SQLite gets created in PyInstaller's `_MEIPASS` and is wiped on next launch.
- **Console window closes immediately on error**: keep `console=True`, add a `traceback.print_exc(); input("press enter to exit")` at the top-level except.
- **macOS Gatekeeper**: unsigned binaries trigger a "cannot be opened" dialog. Document `xattr -d com.apple.quarantine <binary>` as the workaround.
- **CI on Windows or macOS**: avoid unless really needed. The smoke test is import-only, ubuntu is enough.
