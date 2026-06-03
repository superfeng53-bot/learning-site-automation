"""captcha_limiter — 全局验证码限频 / 冷却（站点无关，直接用）。

站点定制点：`is_captcha_rate_limited()` 的关键词表（站点限频文案/码）。
其余（冷却、最小间隔、连续失败退避、跨进程持久化）通用。

接入（在站点 login.py 里）：
- 每次 /captcha/get 前：wait_before_captcha()
- /captcha/check 命中限频码：report_rate_limited(msg)
- 连续 3 次 ddddocr 误识：report_recognition_failure(msg)
- 成功：report_recognition_success()
启动时 configure_state_file(DATA_DIR / "captcha-state.json")。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

CAPTCHA_MAX_ATTEMPTS_PER_LOGIN = 5
GLOBAL_FAILURE_COOLDOWN_SEC = 90
MIN_INTERVAL_SEC = 1.2

_STATE_FILE: Path | None = None
_LOCK = threading.Lock()
_STATE = {
    "last_attempt_ts": 0.0,
    "cooldown_until": 0.0,
    "consecutive_failures": 0,
}

# 站点定制点：补充站点实际的限频文案 / 码
_RATE_LIMIT_KEYWORDS = ("过于频繁", "频率过快", "6112", "rate limit", "稍后再试")


class CaptchaRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


def configure_state_file(path: Path) -> None:
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
    return any(k in text for k in _RATE_LIMIT_KEYWORDS)


def wait_before_captcha(block: bool = True) -> None:
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


def report_recognition_failure(msg: str = "") -> bool:
    """连续失败达阈值则触发冷却，返回是否触发。"""
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


def report_rate_limited(msg: str = "", *, cooldown_sec: float = GLOBAL_FAILURE_COOLDOWN_SEC) -> float:
    with _LOCK:
        _STATE["cooldown_until"] = time.time() + cooldown_sec
        _save()
        return cooldown_sec


def format_cooldown_message(remaining: float) -> str:
    return f"验证码冷却中，还需 {remaining:.0f}s"


def state_snapshot() -> dict:
    return dict(_STATE)
