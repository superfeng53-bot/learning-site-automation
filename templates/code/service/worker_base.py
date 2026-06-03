"""
Worker 基类：处理通用状态转换、session 管理、重试矩阵。
复制到 <svc>/worker.py，继承 AccountWorkerBase，实现：
  - run_pipeline(account, session_client) -> PipelineResult
  - （B 型）run_year_pipeline(account, session_client, year) -> YearResult

状态机（A 型）：queued/retrying → running → [waiting_apply →] completed | failed
状态机（B 型）：queued/retrying → running → completed | failed（无 waiting_apply）
"""
from __future__ import annotations

import json
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ── 结果数据类 ────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    success: bool
    final_state: str = "failed"          # completed | waiting_apply | failed
    status_msg: str = ""
    extra_updates: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    logs: list[dict] = field(default_factory=list)
    hard_failure: bool = False           # True → 不重试，直接 failed


# ── Worker 基类 ───────────────────────────────────────────────────────────────

class AccountWorkerBase(ABC):
    """
    子类必须实现 run_pipeline()；可选覆盖 get_session_probe()。
    构造时传入 store、session_manager（来自 <pkg>）。
    """

    MAX_RETRY = 5
    RETRY_DELAY = 60       # 秒
    SESSION_PROBE_TIMEOUT = 10

    def __init__(self, account: dict, store, session_manager) -> None:
        self._account = account
        self._store = store
        self._sm = session_manager
        self._started_at = time.time()

    # ── 子类必须实现 ──────────────────────────────────────────────────────────

    @abstractmethod
    def run_pipeline(self, account: dict, client) -> PipelineResult:
        """
        执行登录后全流程（分配/选课 → 日闸门 → 学习 → 考试 → 申请）。
        client: session_manager.get_client(user_id)
        返回 PipelineResult。
        """
        ...

    def get_session_probe(self):
        """
        返回一个 callable，用于 ensure_session 探活。
        默认 None（表示每次都重新登录）；子类重写以提供便宜的 API 调用。
        """
        return None

    # ── 主入口（由 Orchestrator 线程调用） ───────────────────────────────────

    def run_once(self) -> None:
        account = self._account
        acc_id = account["id"]
        username = account["username"]
        password = account["password"]
        extra = json.loads(account.get("extra_json") or "{}")
        cookies = extra.get("cookies")

        self._set_phase(acc_id, "login")

        # 1. ensure_session
        try:
            client, new_cookies, err = self._ensure_session(
                acc_id, username, password, cookies
            )
        except Exception as exc:
            self._handle_transient_failure(acc_id, f"session 异常: {exc}")
            return

        if err:
            if self._is_hard_auth_error(err):
                self._store.update_account_status(acc_id, "failed", f"认证失败: {err}")
                self._write_run(acc_id, "failed", err)
            else:
                self._handle_transient_failure(acc_id, f"登录失败: {err}")
            return

        # 保存新 cookies
        if new_cookies:
            extra["cookies"] = new_cookies
            self._store.update_extra(acc_id, extra)

        # 2. 执行业务流水线（子类实现）
        self._set_phase(acc_id, "running")
        try:
            result = self.run_pipeline(account, client)
        except Exception as exc:
            traceback.print_exc()
            result = PipelineResult(
                success=False, final_state="failed",
                status_msg=f"流水线异常: {exc}", error=str(exc),
            )

        # 3. 持久化结果
        self._persist_result(acc_id, result, extra)

    # ── session 管理 ──────────────────────────────────────────────────────────

    def _ensure_session(self, acc_id: int, username: str, password: str,
                        cookies) -> tuple:
        """
        调用 session_manager.ensure_session；返回 (client, cookies, error_or_None)。
        子类可覆盖此方法以适配不同的 session_manager 接口。
        """
        user_id = str(acc_id)
        probe = self.get_session_probe()
        reused, new_cookies, info, err = self._sm.ensure_session(
            user_id, username, password,
            cookies=cookies,
            probe=probe,
        )
        client = self._sm.get_client(user_id)
        return client, new_cookies, err

    @staticmethod
    def _is_hard_auth_error(err: str) -> bool:
        """业务层认证错误（密码错/账号封禁）→ True；网络/超时 → False。"""
        hard_keywords = ("密码错误", "账号不存在", "账号已锁定", "credentials",
                         "invalid password", "unauthorized", "403")
        err_lower = err.lower()
        return any(k.lower() in err_lower for k in hard_keywords)

    # ── 状态写入 ──────────────────────────────────────────────────────────────

    def _set_phase(self, acc_id: int, phase: str) -> None:
        account = self._store.get_account(acc_id)
        if not account:
            return
        extra = json.loads(account.get("extra_json") or "{}")
        extra["phase"] = phase
        self._store.update_extra(acc_id, extra)

    def _handle_transient_failure(self, acc_id: int, msg: str) -> None:
        account = self._store.get_account(acc_id)
        retry_count = (account or {}).get("retry_count", 0) + 1
        if retry_count >= self.MAX_RETRY:
            self._store.update_account_status(acc_id, "failed", msg)
            self._write_run(acc_id, "failed", msg)
        else:
            now = time.time()
            self._store.update_account(
                acc_id,
                status="retrying",
                status_msg=msg,
                retry_count=retry_count,
                queued_at=now + self.RETRY_DELAY,
            )

    def _persist_result(self, acc_id: int, result: PipelineResult, extra: dict) -> None:
        # 合并 extra 更新
        if result.extra_updates:
            extra.update(result.extra_updates)
            extra.pop("phase", None)
            self._store.update_extra(acc_id, extra)

        ended_at = time.time()
        summary = result.status_msg or result.error or ""

        if result.success:
            self._store.update_account_status(acc_id, result.final_state, summary)
            self._write_run(acc_id, "success", summary, result.logs)
        elif result.hard_failure:
            self._store.update_account_status(acc_id, "failed", summary)
            self._write_run(acc_id, "failed", summary, result.logs)
        else:
            self._handle_transient_failure(acc_id, summary)
            self._write_run(acc_id, "failed", summary, result.logs)

    def _write_run(self, acc_id: int, result: str, summary: str,
                   logs: list | None = None) -> None:
        self._store.add_run(
            acc_id,
            started_at=self._started_at,
            ended_at=time.time(),
            result=result,
            summary=summary,
            logs=logs or [],
        )
