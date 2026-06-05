"""
[OPTIONAL:申请学分] — 站点无学分申请流程时删除本文件。
异步申请 worker：独立消费 apply_queue，与学习侧并行，paused 时也继续跑。
复制到 <svc>/apply_worker.py，实现 do_apply_credit()。
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any


# ── 申请结果 ──────────────────────────────────────────────────────────────────

class ApplyResult:
    __slots__ = ("ok", "message", "rate_limited", "hard_fail")

    def __init__(self, ok: bool, message: str = "",
                 rate_limited: bool = False, hard_fail: bool = False) -> None:
        self.ok = ok
        self.message = message
        self.rate_limited = rate_limited
        self.hard_fail = hard_fail


# ── Apply Worker 基类 ─────────────────────────────────────────────────────────

class ApplyWorkerBase(ABC):

    MAX_ATTEMPTS = 5
    RATE_LIMIT_DELAY = 300    # 5 分钟后重试
    HARD_FAIL_DELAY = 3600    # 1 小时后重试（达到 max 则标 dead）

    def __init__(self, store, session_manager) -> None:
        self._store = store
        self._sm = session_manager

    # ── 子类必须实现 ──────────────────────────────────────────────────────────

    @abstractmethod
    def do_apply_credit(self, client, project_id: str,
                        apply_task: dict[str, Any]) -> ApplyResult:
        """
        调用平台的学分申请接口。
        client: 已登录的 session client
        project_id: 课程/项目 id
        apply_task: apply_queue 行（含 subject_label, credits 等）
        """
        ...

    def get_daily_apply_limit(self) -> int:
        """每账号每日申请上限，默认 1；按站点覆盖。"""
        return 1

    # ── 主入口（由 Orchestrator tick 调用） ──────────────────────────────────

    def process_one(self, now: float) -> None:
        task = self._store.claim_next_apply(now)
        if not task:
            return

        acc_id = task["account_id"]
        apply_id = task["id"]
        project_id = task["project_id"]

        # 日配额检查
        if not self._check_daily_quota(acc_id):
            from .scheduling import daily_eligible_at, tomorrow_shanghai
            next_at = daily_eligible_at(acc_id, local_day=tomorrow_shanghai())
            self._store.finish_apply(apply_id, False, "日配额已满", next_attempt_at=next_at)
            return

        # 获取 session
        extra = json.loads(task.get("extra_json") or "{}")
        cookies = extra.get("cookies")
        username = task.get("username", "")
        try:
            client, _, err = self._get_client(acc_id, username, cookies)
        except Exception as exc:
            self._store.finish_apply(apply_id, False, f"session 异常: {exc}",
                                     next_attempt_at=now + self.RATE_LIMIT_DELAY)
            return
        if err:
            self._store.finish_apply(apply_id, False, f"登录失败: {err}",
                                     next_attempt_at=now + self.RATE_LIMIT_DELAY)
            return

        # 执行申请
        try:
            result = self.do_apply_credit(client, project_id, task)
        except Exception as exc:
            result = ApplyResult(False, str(exc))

        if result.ok:
            self._store.finish_apply(apply_id, True, result.message)
            self._on_apply_success(acc_id, project_id, task)
        elif result.rate_limited:
            self._store.finish_apply(apply_id, False, result.message,
                                     next_attempt_at=now + self.RATE_LIMIT_DELAY)
        else:
            attempts = task.get("attempts", 0) + 1
            dead = attempts >= self.MAX_ATTEMPTS or result.hard_fail
            self._store.finish_apply(apply_id, False, result.message,
                                     next_attempt_at=now + self.HARD_FAIL_DELAY,
                                     dead=dead)

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _check_daily_quota(self, acc_id: int) -> bool:
        """查 credit_applications 今日成功数；MAX_APPLY_PER_DAY<=0 表示不限制。"""
        try:
            from .config import MAX_APPLY_PER_DAY
        except ImportError:
            MAX_APPLY_PER_DAY = self.get_daily_apply_limit()
        limit = self.get_daily_apply_limit()
        if MAX_APPLY_PER_DAY > 0:
            limit = MAX_APPLY_PER_DAY
        if limit <= 0:
            return True
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz=tz)
        day_start = datetime(now.year, now.month, now.day, tzinfo=tz).timestamp()
        if not hasattr(self._store, "count_apply_success_today"):
            return True
        n = self._store.count_apply_success_today(acc_id, day_start_ts=day_start)
        return n < limit

    def _get_client(self, acc_id: int, username: str, cookies):
        user_id = str(acc_id)
        _, new_cookies, info, err = self._sm.ensure_session(
            user_id, username, "", cookies=cookies
        )
        client = self._sm.get_client(user_id)
        return client, new_cookies, err

    def _on_apply_success(self, acc_id: int, project_id: str, task: dict) -> None:
        """申请成功后检查账号是否全部完成；子类可覆盖。"""
        if self._store.pending_apply_count(acc_id) == 0:
            self._store.update_account_status(acc_id, "completed", "全部学分申请完毕")
