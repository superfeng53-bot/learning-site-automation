"""SessionManager — 每账号 HttpClient、登录锁、Token 复用探活（站点无关，直接用）。

依赖站点 `login.py` 提供的 `LoginService.login(username, password) -> LoginResult`
（接口固定；实现由 phase 1 站点侦察填）。

业务 Service 不在此创建：由 site_adapter 用 `mgr.get_client(user_id)` 构造，
probe 以 callable 形式传入 ensure_session（见 site_adapter 模板）。
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from .captcha_limiter import format_cooldown_message, get_cooldown_remaining
from .client import HttpClient


class SessionExpiredError(PermissionError):
    pass


_username_locks: dict[str, threading.Lock] = {}
_username_locks_guard = threading.Lock()


def _username_login_lock(username: str) -> threading.Lock:
    with _username_locks_guard:
        if username not in _username_locks:
            _username_locks[username] = threading.Lock()
        return _username_locks[username]


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

    # ---- 登录（受验证码冷却 + 同账号互斥保护） ----
    def login_user(self, user_id: str, username: str, password: str):
        from .login import LoginResult, LoginService  # 站点文件，延迟导入
        remaining = get_cooldown_remaining()
        if remaining > 0:
            return LoginResult(success=False, message=format_cooldown_message(remaining),
                               rate_limited=True, retry_after=remaining)
        with _username_login_lock(username):
            return LoginService(self.get_client(user_id)).login(username, password)

    def relogin_user(self, user_id: str, username: str, password: str):
        """业务调用中检测到会话失效时调用一次（每失败步最多一次）。"""
        self.remove(user_id)
        return self.login_user(user_id, username, password)

    # ---- Token 复用：load cookies → is_logged_in → 可选 probe → 命中则跳过登录 ----
    def ensure_session(self, user_id: str, username: str, password: str,
                       cookies: dict | None = None, *,
                       probe: Callable[[], None] | None = None,
                       require_probe: bool = False
                       ) -> tuple[bool, dict, dict | None, str | None]:
        """返回 (reused_token, cookies, user_info, error_message)。"""
        if cookies:
            try:
                client = self.get_client(user_id)
                client.load_cookies(cookies)
                if client.is_logged_in():
                    if probe is not None:
                        try:
                            probe()
                        except Exception:
                            if require_probe:
                                raise
                            return self._fresh_login(user_id, username, password)
                    return True, client.export_cookies(), None, None
            except Exception:
                pass
        return self._fresh_login(user_id, username, password)

    def _fresh_login(self, user_id, username, password):
        self.remove(user_id)
        result = self.login_user(user_id, username, password)
        if not result.success:
            self.remove(user_id)
            return False, {}, None, result.message
        return False, result.cookies, dict(result.user_info), None


_default: SessionManager | None = None
_default_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _default
    with _default_lock:
        if _default is None:
            _default = SessionManager()
        return _default
