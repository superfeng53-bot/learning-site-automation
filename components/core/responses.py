"""responses — 统一响应解析（站点无关骨架 + 站点定制 hint 字典）。

通用：ApiResponse 数据类、is_session_expired() 会话失效探测。
站点定制点：各 *_HINTS 失败码 → 中文提示、parse_*_response() 的 ok 判定字段
（不同站点 result/code/msg 字段名不同，phase 2 侦察后填）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiResponse:
    ok: bool
    raw: dict[str, Any]
    message: str
    code: str | None = None
    hint: str = ""


# 站点定制点：phase 2 只填**实际观察到**的失败码，不要臆测。
LOGIN_MSG_HINTS: dict[str, str] = {
    # "-1": "用户名或密码错误",
    # "-4": "验证码已失效",
}

CREDIT_CODE_HINTS: dict[str, str] = {
    # "-6": "未完成项目评价，需先访问 /html/survey",
    # "-8": "今日申请上限",
}

# 站点定制点：会话失效关键词（不同站点文案不同）
_SESSION_EXPIRED_KEYWORDS = (
    "未登录", "nologin", "会话已失效", "cookie 无效", "session expired", "登录超时",
)


def is_session_expired(exc_or_msg: Any) -> bool:
    """所有业务调用统一用本函数判定会话失效 → 触发一次 relogin（见 session_manager）。"""
    if isinstance(exc_or_msg, PermissionError):
        return True
    text = str(exc_or_msg or "").lower()
    return any(m.lower() in text for m in _SESSION_EXPIRED_KEYWORDS)


def parse_member_response(data: dict, *, ok_field: str = "result", ok_value: str = "ok",
                          ok_msg: str = "操作成功") -> ApiResponse:
    """站点定制点：默认按 {result: 'ok', msg: ...} 形态；不同站点改 ok_field/ok_value。"""
    ok = data.get(ok_field) == ok_value
    msg = str(data.get("msg") or "")
    return ApiResponse(ok=ok, raw=data, message=msg or ok_msg,
                       code=str(data.get(ok_field)),
                       hint=LOGIN_MSG_HINTS.get(msg, ""))
