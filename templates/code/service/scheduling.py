"""
每日窗口错峰：stable per-account offset 避免 8:00 雪崩。
完整通用，直接复制到 <svc>/scheduling.py，无需修改。
只在 A 型（学科规划型）使用；B 型（公需年度型）可省略本模块。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# 从 config.py 导入常量（在你的项目里设置这两个值）
try:
    from .config import DAILY_START_HOUR, DAILY_SPREAD_SECONDS
except ImportError:
    DAILY_START_HOUR = 8
    DAILY_SPREAD_SECONDS = 1800  # 30 分钟，最多 ~1800 账号无冲突

_TZ = ZoneInfo("Asia/Shanghai")


def spread_offset_seconds(account_id: int) -> int:
    """
    固定偏移，同一 account_id 每天相同，不用 random()。
    范围 [0, DAILY_SPREAD_SECONDS)。
    """
    return int(account_id) % DAILY_SPREAD_SECONDS


def daily_eligible_at(account_id: int, *, local_day: date) -> float:
    """
    Unix timestamp：local_day 的 DAILY_START_HOUR:00 (上海时区)
    + spread_offset_seconds(account_id)。
    所有「明日 8:00」「今日 8:00」延迟都必须调用本函数，不写裸 08:00:00。
    """
    base = datetime(
        local_day.year, local_day.month, local_day.day,
        DAILY_START_HOUR, 0, 0, tzinfo=_TZ,
    )
    return (base + timedelta(seconds=spread_offset_seconds(account_id))).timestamp()


def today_shanghai() -> date:
    return datetime.now(tz=_TZ).date()


def tomorrow_shanghai() -> date:
    return today_shanghai() + timedelta(days=1)
