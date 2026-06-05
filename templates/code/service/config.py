"""
服务级常量（复制到 <svc>/config.py 后按站点改配额）。
引擎模块（store / orchestrator / apply_worker / scheduling）从此读取默认值。
"""
from __future__ import annotations

# ── 调度并发（与 templates/requirements.md §8 一致）────────────────────────────
DEFAULT_CONCURRENCY = 400
MAX_CONCURRENCY = 400
MIN_CONCURRENCY = 1

TICK_SECONDS = 3
TICK_STARTS_PER_SECOND = 10
RETRY_DELAY_SEC = 60
MAX_RETRY = 5

# ── 8:00 日窗错峰（A 型）；B 型可不使用 scheduling ───────────────────────────
DAILY_START_HOUR = 8
DAILY_SPREAD_SECONDS = 1800

# ── 单日配额（A 型；B 型设为 0 表示不启用对应闸门）────────────────────────────
MAX_LEARN_PER_DAY = 1
MAX_APPLY_PER_DAY = 1
APPLY_RATE_LIMIT_BACKOFF_SEC = 300
MAX_APPLY_ATTEMPTS = 5

SERVICE_PORT = 17865
