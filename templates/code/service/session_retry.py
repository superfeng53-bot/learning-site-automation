"""
业务 HTTP 调用中的会话失效处理（需求 §5.1.1）。

用法：在 Service / run_pipeline 内包一层 call_with_session_retry(...)。
检测到会话失效 → relogin 至多 1 次 → 重试同一 callable 1 次。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_SESSION_KEYWORDS = (
    "未登录", "nologin", "会话已失效", "cookie 无效", "session expired", "登录超时",
)


def is_session_expired(exc_or_msg: Any) -> bool:
    """与 <pkg>/responses.is_session_expired 语义一致；站点可改为从 pkg 导入。"""
    try:
        from responses import is_session_expired as _site  # type: ignore
        return _site(exc_or_msg)
    except ImportError:
        pass
    if isinstance(exc_or_msg, PermissionError):
        return True
    text = str(exc_or_msg or "").lower()
    return any(m.lower() in text for m in _SESSION_KEYWORDS)


def call_with_session_retry(
    session_manager,
    *,
    user_id: str,
    username: str,
    password: str,
    cookies: dict | None,
    fn: Callable[[Any], T],
    on_cookies_updated: Callable[[dict, dict | None], None] | None = None,
) -> T:
    """执行 fn(client)。会话失效时 relogin 一次后重试 fn 一次。"""
    client = session_manager.get_client(user_id)
    if cookies:
        client.load_cookies(cookies)

    def _run() -> T:
        return fn(client)

    try:
        return _run()
    except Exception as exc:
        if not is_session_expired(exc):
            raise
        first_err = exc

    login_result = session_manager.relogin_user(user_id, username, password)
    success = getattr(login_result, "success", None)
    if success is None:
        success = bool(login_result)
    if not success:
        msg = getattr(login_result, "message", None) or str(first_err)
        raise RuntimeError(f"自动重登失败: {msg}") from first_err

    new_cookies = getattr(login_result, "cookies", None)
    if new_cookies is None and hasattr(client, "export_cookies"):
        new_cookies = client.export_cookies()
    user_info = getattr(login_result, "user_info", None)
    if on_cookies_updated and new_cookies:
        on_cookies_updated(new_cookies, user_info)

    try:
        return _run()
    except Exception as exc2:
        if is_session_expired(exc2):
            raise RuntimeError(f"重登后仍会话失效: {exc2}") from exc2
        raise
