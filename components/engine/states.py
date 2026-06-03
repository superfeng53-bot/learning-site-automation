"""状态机（通用，直接用）。

集中定义账号主状态机与 apply_queue 子状态机：枚举、合法转移表、守卫函数、中文标签。
worker / apply_worker / store / web app 全部经由本模块做状态转移，禁止散落字符串。

按能力裁剪：`has_credit=False` 时 `waiting_apply` 不可达（reachable_account_states 自动剔除）。
"""
from __future__ import annotations

from enum import Enum


class AccountStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPLY = "waiting_apply"   # 仅 has_credit 时可达
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ApplyStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    SKIPPED = "skipped"


# 中文标签（UI Pill / Excel 状态列共用）
ACCOUNT_LABELS: dict[str, str] = {
    AccountStatus.QUEUED: "排队",
    AccountStatus.RUNNING: "进行中",
    AccountStatus.WAITING_APPLY: "等待申请",
    AccountStatus.RETRYING: "重试",
    AccountStatus.COMPLETED: "已完成",
    AccountStatus.FAILED: "失败",
    AccountStatus.PAUSED: "已暂停",
}

APPLY_LABELS: dict[str, str] = {
    ApplyStatus.PENDING: "待申请",
    ApplyStatus.IN_FLIGHT: "申请中",
    ApplyStatus.SUCCEEDED: "已申请",
    ApplyStatus.DEAD: "申请失败",
    ApplyStatus.SKIPPED: "已跳过",
}


# 合法转移表（from -> {to,...}）。* 表示任意来源（恢复/暂停）。
_ACCOUNT_TRANSITIONS: dict[AccountStatus, set[AccountStatus]] = {
    AccountStatus.QUEUED: {AccountStatus.RUNNING, AccountStatus.PAUSED},
    AccountStatus.RUNNING: {
        AccountStatus.COMPLETED, AccountStatus.WAITING_APPLY,
        AccountStatus.RETRYING, AccountStatus.FAILED,
        AccountStatus.QUEUED,  # 让位/中断重入队
    },
    AccountStatus.WAITING_APPLY: {
        AccountStatus.COMPLETED, AccountStatus.RUNNING,
        AccountStatus.FAILED, AccountStatus.QUEUED,
    },
    AccountStatus.RETRYING: {AccountStatus.RUNNING, AccountStatus.QUEUED, AccountStatus.PAUSED},
    AccountStatus.COMPLETED: {AccountStatus.QUEUED},   # 重学
    AccountStatus.FAILED: {AccountStatus.QUEUED},      # 重学
    AccountStatus.PAUSED: {AccountStatus.QUEUED},      # 恢复
}

_APPLY_TRANSITIONS: dict[ApplyStatus, set[ApplyStatus]] = {
    ApplyStatus.PENDING: {ApplyStatus.IN_FLIGHT, ApplyStatus.SKIPPED},
    ApplyStatus.IN_FLIGHT: {ApplyStatus.SUCCEEDED, ApplyStatus.PENDING, ApplyStatus.DEAD},
    ApplyStatus.SUCCEEDED: set(),
    ApplyStatus.DEAD: {ApplyStatus.PENDING},   # 人工重置可回 pending
    ApplyStatus.SKIPPED: {ApplyStatus.PENDING},
}


def reachable_account_states(*, has_credit: bool) -> list[str]:
    states = [s.value for s in AccountStatus]
    if not has_credit:
        states = [s for s in states if s != AccountStatus.WAITING_APPLY]
    return states


def can_transition(frm: str, to: str) -> bool:
    try:
        return AccountStatus(to) in _ACCOUNT_TRANSITIONS[AccountStatus(frm)]
    except (ValueError, KeyError):
        return False


def assert_account_transition(frm: str, to: str) -> str:
    """校验并返回目标状态字符串；非法转移抛 ValueError。恢复/暂停可绕过（见 force）。"""
    if not can_transition(frm, to):
        raise ValueError(f"非法账号状态转移：{frm} -> {to}")
    return to


def can_apply_transition(frm: str, to: str) -> bool:
    try:
        return ApplyStatus(to) in _APPLY_TRANSITIONS[ApplyStatus(frm)]
    except (ValueError, KeyError):
        return False


# 恢复/暂停等运维动作允许从任意状态强制设置
_FORCE_TARGETS = {AccountStatus.PAUSED, AccountStatus.QUEUED}


def is_force_target(to: str) -> bool:
    try:
        return AccountStatus(to) in _FORCE_TARGETS
    except ValueError:
        return False
