"""Bootstrap a learning-site automation project skeleton.

Usage:
    python init_project.py --root <abs_path> --pkg <pkg_name> --svc <svc_name> \
        --site-url <url> \
        (--username <test_user> --password <test_pwd> | --credentials <combined>) \
        [--credential-input-mode split|combined] \
        [--platform <display_name>]

Creates the directory tree described in templates/project-skeleton.md, plus
.gitignore, requirements.txt, data/account.json, and stub __init__.py files.
Idempotent: re-running on an existing root only fills in missing files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from credential_parser import CredentialParseError, parse_combined_credentials


GITIGNORE = """\
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
"""

REQUIREMENTS = """\
requests>=2.31
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.5
ddddocr>=1.4.11
pycryptodome>=3.20
pillow>=10.0
openpyxl>=3.1
tzdata>=2024.1  # Windows has no system tz db; zoneinfo("Asia/Shanghai") fails without it (Excel import / year defaults)
"""

PKG_INIT = '''\
"""{pkg} — HTTP toolkit for {platform}."""
from .session_manager import SessionManager, get_session_manager

__all__ = ["SessionManager", "get_session_manager"]
'''

PKG_CONFIG = '''\
from pathlib import Path

BASE_URL = "{site_url}"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_ACCOUNT_FILE = DATA_DIR / "account.json"
DEFAULT_COOKIES_FILE = DATA_DIR / "cookies.json"

# Captcha standard image size (override after phase 1 recon).
STD_CAPTCHA_W = 310
STD_CAPTCHA_H = 155
'''

PKG_CLIENT = '''\
from __future__ import annotations

import time
from typing import Any

import requests

from .config import BASE_URL, DEFAULT_USER_AGENT


class HttpClient:
    def __init__(self, base_url: str = BASE_URL, user_id: str | None = None) -> None:
        self.user_id = user_id or str(id(self))
        self.base_url = base_url.rstrip("/")
        self.user_profile: dict[str, Any] | None = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": f"{self.base_url}/",
        })

    def load_cookies(self, cookies: dict[str, str]) -> None:
        self.session.cookies.clear()
        for k, v in cookies.items():
            self.session.cookies.set(k, v)

    def export_cookies(self) -> dict[str, str]:
        return self.session.cookies.get_dict()

    def _cookie(self, name: str) -> str:
        return self.session.cookies.get_dict().get(name, "")

    def json_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(f"{self.base_url}{path}", json=payload,
                              headers={"Content-Type": "application/json;charset=UTF-8"},
                              timeout=30)
        r.raise_for_status()
        return r.json()

    def form_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(f"{self.base_url}{path}", data=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def form_post_safe(self, path: str, payload: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.form_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if i + 1 == attempts:
                    break
                time.sleep(2.0 * (2 ** i))
        raise last  # type: ignore[misc]

    def is_logged_in(self) -> bool:
        """Override in phase 1 after observing the actual session-check endpoint."""
        return bool(self.export_cookies())
'''

PKG_LOGIN_STUB = '''\
"""Stub login service. Phase 1 of the learning-site-automation skill replaces this
with a real implementation tied to the site's captcha kind and login endpoint."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import HttpClient


@dataclass
class LoginResult:
    success: bool
    message: str
    session_key: str | None = None
    user_info: dict[str, Any] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)
    hint: str = ""
    rate_limited: bool = False
    retry_after: float = 0.0


class LoginService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def login(self, username: str, password: str) -> LoginResult:
        raise NotImplementedError(
            "LoginService.login is a stub. Implement in phase 1 after browser recon."
        )
'''

PKG_SESSION_MGR_STUB = '''\
"""Stub session manager. Phase 3 of the skill replaces this with full retry / lock /
token-reuse logic."""
from __future__ import annotations

import threading

from .client import HttpClient
from .login import LoginResult, LoginService


class SessionManager:
    def __init__(self) -> None:
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

    def login_user(self, user_id: str, username: str, password: str) -> LoginResult:
        client = self.get_client(user_id)
        return LoginService(client).login(username, password)


_default: SessionManager | None = None
_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _default
    with _lock:
        if _default is None:
            _default = SessionManager()
        return _default
'''

PKG_RESPONSES_STUB = '''\
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApiResponse:
    ok: bool
    raw: dict[str, Any]
    message: str
    code: str | None = None
    hint: str = ""
'''

CLI_LOGIN_STUB = '''\
"""Login CLI. After phase 1, this should work end-to-end against the test account."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_ACCOUNT_FILE, DEFAULT_COOKIES_FILE


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--user-id", default="default")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--account", default=str(DEFAULT_ACCOUNT_FILE))
    p.add_argument("-o", "--output", default=str(DEFAULT_COOKIES_FILE))
    p.add_argument("--check", action="store_true", help="check existing cookies only")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    args = p.parse_args()

    mgr = get_session_manager()

    if args.check:
        cookies = json.loads(Path(args.cookies).read_text(encoding="utf-8"))
        mgr.get_client(args.user_id).load_cookies(cookies)
        ok = mgr.get_client(args.user_id).is_logged_in()
        print("session_ok" if ok else "session_expired")
        sys.exit(0 if ok else 2)

    if args.username and args.password:
        username, password = args.username, args.password
    else:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]

    result = mgr.login_user(args.user_id, username, password)
    if not result.success:
        print(f"login failed: {result.message} ({result.hint})", file=sys.stderr)
        sys.exit(1)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(result.cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"login ok, cookies written to {args.output}")


if __name__ == "__main__":
    main()
'''

SVC_INIT = '''\
"""{svc} — multi-account always-on service for {platform}.

Filled in during phase 5 of the learning-site-automation skill.
"""
__version__ = "0.1.0"
'''

RUN_SERVICE_STUB = '''\
"""Placeholder. Phase 5 of the skill replaces this with a real FastAPI launcher."""
import sys
print("run_service.py: phase 5 of learning-site-automation has not been completed.",
      file=sys.stderr)
sys.exit(2)
'''

RUN_COURSE_STUB = '''\
"""Placeholder. Phase 4 of the skill replaces this with the real CourseRunner driver."""
import sys
print("run_course.py: phase 4 of learning-site-automation has not been completed.",
      file=sys.stderr)
sys.exit(2)
'''

README_STUB = """\
# {project_name}

Automated learning client for {platform} ({site_url}).

Bootstrapped with the `learning-site-automation` skill (Goal mode, phases 1–5).
Phases:

- [x] phase 1 (login)  — pending
- [ ] phase 2 (api tools)
- [ ] phase 3 (stability)
- [ ] phase 4 (end-to-end runner)
- [ ] phase 5 (always-on service + web UI)
- [ ] packaging (out of band — `docs/packaging/AGENT.md` on each target OS)
"""


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _resolve_test_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    """Return (username, password, credential_input_mode)."""
    mode = (args.credential_input_mode or "split").strip().lower()
    if mode not in ("split", "combined"):
        print("error: --credential-input-mode must be split or combined", file=sys.stderr)
        raise SystemExit(2)

    if args.credentials:
        try:
            parsed = parse_combined_credentials(args.credentials)
        except CredentialParseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        return parsed.username, parsed.password, mode

    if not args.username or not args.password:
        print(
            "error: provide --username + --password, or --credentials for combined input",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return args.username, args.password, mode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="absolute project root path")
    ap.add_argument("--pkg", required=True, help="api package name, e.g. sww_api")
    ap.add_argument("--svc", required=True, help="service package name, e.g. sww_service")
    ap.add_argument("--site-url", required=True, help="login URL")
    ap.add_argument("--username", default="", help="test username (split mode)")
    ap.add_argument("--password", default="", help="test password (split mode)")
    ap.add_argument(
        "--credentials",
        default="",
        help="single-field test credentials; auto-parses 账号/密码 labels",
    )
    ap.add_argument(
        "--credential-input-mode",
        choices=("split", "combined"),
        default="split",
        help="UI/Excel credential entry style: split=账号+密码两栏, combined=一栏自动识别",
    )
    ap.add_argument("--platform", default="", help="display name for the platform")
    args = ap.parse_args()

    username, password, credential_input_mode = _resolve_test_credentials(args)

    root = Path(args.root).expanduser().resolve()
    platform = args.platform or args.pkg.split("_")[0].upper()
    project_name = root.name
    skill_root = _SCRIPT_DIR.parent
    credential_parser_src = skill_root / "components" / "core" / "credential_parser.py"
    if not credential_parser_src.is_file():
        credential_parser_src = _SCRIPT_DIR / "credential_parser.py"
    credential_parser_py = (
        credential_parser_src.read_text(encoding="utf-8")
        if credential_parser_src.is_file()
        else ""
    )

    if root.exists() and any(root.iterdir()):
        print(f"warning: {root} is not empty, will only fill missing files", file=sys.stderr)
    root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []

    targets: list[tuple[Path, str]] = [
        (root / ".gitignore", GITIGNORE),
        (root / "requirements.txt", REQUIREMENTS),
        (root / "README.md", README_STUB.format(
            project_name=project_name, platform=platform, site_url=args.site_url)),
        (root / "data" / ".gitkeep", ""),
        (root / "data" / "account.json", json.dumps({
            "platform": platform,
            "site_url": args.site_url,
            "username": username,
            "password": password,
            "credential_input_mode": credential_input_mode,
            "notes": "Test account for local development only. Gitignored.",
        }, ensure_ascii=False, indent=2)),
        (root / "docs" / ".gitkeep", ""),
        (root / "scripts" / ".gitkeep", ""),

        (root / args.pkg / "__init__.py", PKG_INIT.format(pkg=args.pkg, platform=platform)),
        (root / args.pkg / "config.py", PKG_CONFIG.format(site_url=args.site_url)),
        (root / args.pkg / "client.py", PKG_CLIENT),
        (root / args.pkg / "login.py", PKG_LOGIN_STUB),
        (root / args.pkg / "session_manager.py", PKG_SESSION_MGR_STUB),
        (root / args.pkg / "responses.py", PKG_RESPONSES_STUB),
        (root / args.pkg / "cli_login.py", CLI_LOGIN_STUB),

        (root / args.svc / "__init__.py", SVC_INIT.format(svc=args.svc, platform=platform)),
        (root / args.svc / "persistence" / "__init__.py", ""),
        (root / args.svc / "web" / "__init__.py", ""),
        (root / args.svc / "web" / "templates" / ".gitkeep", ""),

        (root / "run_service.py", RUN_SERVICE_STUB),
        (root / "run_course.py", RUN_COURSE_STUB),
        (root / f"{args.pkg.replace('_api', '_login')}.py" if args.pkg.endswith("_api") else root / f"{args.pkg}_login.py",
         f"from {args.pkg}.cli_login import main\nif __name__ == '__main__':\n    main()\n"),
    ]

    if credential_parser_py:
        targets.append((root / args.pkg / "credential_parser.py", credential_parser_py))

    for path, content in targets:
        rel = path.relative_to(root)
        if write_if_missing(path, content):
            created.append(str(rel))
        else:
            skipped.append(str(rel))

    print(f"project root: {root}")
    print(f"created {len(created)} files, skipped {len(skipped)} existing files")
    if created:
        print("\ncreated:")
        for f in created:
            print(f"  {f}")
    if skipped:
        print("\nskipped (already exists):")
        for f in skipped[:10]:
            print(f"  {f}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more")

    print("\nNext: enter phase 1 of the skill — browser recon + real login.py")


if __name__ == "__main__":
    main()
