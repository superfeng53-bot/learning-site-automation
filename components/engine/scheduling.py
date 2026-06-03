"""调度时间计算（通用，直接用）。

8:00 日窗 + 按 account_id 稳定散列错峰，避免日切时所有账号同一秒惊群。
A 型 worker/apply_worker 的「今日/明日 8:00」一律用 daily_eligible_at()，禁止裸 08:00。
B 型公需无单日限制，可不调用本模块。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import DAILY_SPREAD_SECONDS, DAILY_START_HOUR

_TZ = ZoneInfo("Asia/Shanghai")


def spread_offset_seconds(account_id: int) -> int:
    """[0, DAILY_SPREAD_SECONDS) 内稳定偏移：同 account_id 每天同偏移。"""
    return int(account_id) % DAILY_SPREAD_SECONDS


def daily_eligible_at(account_id: int, *, local_day: date) -> float:
    base = datetime(local_day.year, local_day.month, local_day.day,
                    DAILY_START_HOUR, 0, 0, tzinfo=_TZ)
    return (base + timedelta(seconds=spread_offset_seconds(account_id))).timestamp()


def today_shanghai() -> date:
    return datetime.now(tz=_TZ).date()


def tomorrow_shanghai() -> date:
    return today_shanghai() + timedelta(days=1)
