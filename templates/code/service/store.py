"""
SQLite WAL 持久层。
复制到 <svc>/persistence/store.py，然后：
  1. 按 site_profile 删除不需要的可选表/列（见注释中的 [OPTIONAL:xxx]）
  2. 将所有 <PLATFORM> 占位符替换为实际平台名（仅用于日志字符串）
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .config import DEFAULT_CONCURRENCY, MAX_CONCURRENCY, MIN_CONCURRENCY
from .states import assert_account_transition, assert_apply_transition, is_force_target

# B 型重学时清除的运行期 extra 字段（见 progress-sync.md）
_B_RUNTIME_EXTRA_KEYS = frozenset({
    "phase", "failed_phase", "error_log_text",
    "year_status", "current_year", "certificate_status",
    "current_course_title", "current_course_id", "current_project_id", "project_status",
    "learning_progress", "progress_percent",
})

# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name     TEXT    NOT NULL DEFAULT '',
    username         TEXT    NOT NULL UNIQUE,
    password         TEXT    NOT NULL,
    requirements_json TEXT   NOT NULL DEFAULT '[]',   -- [OPTIONAL:A型学科] B型删此列，改用 target_years_json
    target_years_json TEXT   NOT NULL DEFAULT '[]',   -- [OPTIONAL:B型] A型删此列
    extra_json       TEXT    NOT NULL DEFAULT '{}',
    status           TEXT    NOT NULL DEFAULT 'queued',
    status_msg       TEXT    NOT NULL DEFAULT '',
    retry_count      INTEGER NOT NULL DEFAULT 0,
    queued_at        REAL    NOT NULL DEFAULT 0,
    created_at       REAL    NOT NULL DEFAULT 0,
    updated_at       REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL,
    started_at  REAL    NOT NULL,
    ended_at    REAL    NOT NULL,
    result      TEXT    NOT NULL,
    summary     TEXT    NOT NULL DEFAULT '',
    logs_json   TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id, id DESC);

-- [OPTIONAL:申请学分] 站点无学分申请流程时删除以下两个表
CREATE TABLE IF NOT EXISTS apply_queue (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id       INTEGER NOT NULL,
    project_id       TEXT    NOT NULL,
    subject_label    TEXT    NOT NULL DEFAULT '',
    project_name     TEXT    NOT NULL DEFAULT '',
    credits          REAL,
    status           TEXT    NOT NULL DEFAULT 'pending',
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  REAL    NOT NULL DEFAULT 0,
    last_error       TEXT    NOT NULL DEFAULT '',
    UNIQUE(account_id, project_id)
);

CREATE TABLE IF NOT EXISTS credit_applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL,
    project_id  TEXT    NOT NULL,
    success     INTEGER NOT NULL,
    message     TEXT    NOT NULL DEFAULT '',
    applied_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
);
-- [END OPTIONAL:申请学分]

-- [OPTIONAL:AI学科映射] 未选 LLM 时删除
CREATE TABLE IF NOT EXISTS ai_subject_cache (
    cache_key              TEXT PRIMARY KEY,
    requirement_texts_json TEXT NOT NULL,
    catalog_snapshot_json  TEXT NOT NULL,
    mapping_json           TEXT NOT NULL,
    created_at             REAL NOT NULL DEFAULT 0,
    updated_at             REAL NOT NULL DEFAULT 0
);
-- [END OPTIONAL:AI学科映射]

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ── Store ─────────────────────────────────────────────────────────────────────

class Store:
    """线程安全：每次调用开新连接（WAL 模式允许并发读，写串行）。"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Crash recovery ───────────────────────────────────────────────────────

    def startup_recovery(self) -> None:
        """服务启动时调用：把上次未正常结束的 running 账号重新入队。"""
        now = time.time()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, status FROM accounts WHERE status='running'",
            ).fetchall()
            for row in rows:
                assert_account_transition(row["status"], "queued", force=True)
            conn.execute(
                "UPDATE accounts SET status='queued', status_msg='startup recovery', "
                "updated_at=? WHERE status='running'",
                (now,),
            )
            # [OPTIONAL:申请学分]
            inflight = conn.execute(
                "SELECT id, status FROM apply_queue WHERE status='in_flight'",
            ).fetchall()
            for row in inflight:
                assert_apply_transition(row["status"], "pending")
            conn.execute("UPDATE apply_queue SET status='pending' WHERE status='in_flight'")
            # [END OPTIONAL:申请学分]

    # ── Account CRUD ─────────────────────────────────────────────────────────

    def create_account(self, display_name: str, username: str, password: str,
                       requirements_json: str = "[]", target_years_json: str = "[]",
                       extra_json: str = "{}") -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO accounts "
                "(display_name,username,password,requirements_json,target_years_json,"
                "extra_json,status,queued_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,'queued',?,?,?)",
                (display_name, username, password, requirements_json, target_years_json,
                 extra_json, now, now, now),
            )
            return cur.lastrowid

    def get_account(self, account_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            return dict(row) if row else None

    def get_account_by_username(self, username: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _accounts_filter_sql(
        status: str = "",
        search: str = "",
        date_from: float = 0,
        date_to: float = 0,
    ) -> tuple[str, list]:
        sql = ""
        params: list = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if search:
            sql += " AND (display_name LIKE ? OR username LIKE ? OR status_msg LIKE ?)"
            params.extend([f"%{search}%"] * 3)
        if date_from > 0:
            sql += " AND updated_at >= ?"
            params.append(date_from)
        if date_to > 0:
            sql += " AND updated_at <= ?"
            params.append(date_to)
        return sql, params

    def count_accounts(
        self,
        status: str = "",
        search: str = "",
        date_from: float = 0,
        date_to: float = 0,
    ) -> int:
        where, params = self._accounts_filter_sql(status, search, date_from, date_to)
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM accounts WHERE 1=1{where}",
                params,
            ).fetchone()
            return int(row["n"] if row else 0)

    def list_accounts(self, status: str = "", search: str = "",
                      limit: int = 50, offset: int = 0,
                      date_from: float = 0, date_to: float = 0) -> list[dict]:
        where, params = self._accounts_filter_sql(status, search, date_from, date_to)
        sql = f"SELECT * FROM accounts WHERE 1=1{where} ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def count_by_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM accounts GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["n"] for r in rows}
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            counts["total"] = total
            return counts

    def update_account(self, account_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE accounts SET {set_clause} WHERE id=?",
                (*fields.values(), account_id),
            )

    def update_account_status(self, account_id: int, status: str,
                              status_msg: str = "", retry_delta: int = 0,
                              *, force: bool = False) -> None:
        account = self.get_account(account_id)
        if account:
            frm = account.get("status") or ""
            if frm != status and not (force or is_force_target(status)):
                assert_account_transition(frm, status)
        now = time.time()
        with self._conn() as conn:
            if retry_delta:
                conn.execute(
                    "UPDATE accounts SET status=?,status_msg=?,retry_count=retry_count+?,"
                    "updated_at=? WHERE id=?",
                    (status, status_msg, retry_delta, now, account_id),
                )
            else:
                conn.execute(
                    "UPDATE accounts SET status=?,status_msg=?,updated_at=? WHERE id=?",
                    (status, status_msg, now, account_id),
                )

    def update_extra(self, account_id: int, extra: dict) -> None:
        self.update_account(account_id, extra_json=json.dumps(extra, ensure_ascii=False))

    def delete_account(self, account_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.execute("DELETE FROM runs WHERE account_id=?", (account_id,))
            # [OPTIONAL:申请学分]
            conn.execute("DELETE FROM apply_queue WHERE account_id=?", (account_id,))
            conn.execute("DELETE FROM credit_applications WHERE account_id=?", (account_id,))
            # [END OPTIONAL:申请学分]

    # ── Orchestrator claim ───────────────────────────────────────────────────

    def claim_next_queued(self, now: float) -> Optional[dict]:
        """原子 UPDATE+SELECT：取 queued_at <= now 的最早排队账号，设为 running。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE status IN ('queued','retrying') "
                "AND queued_at <= ? ORDER BY queued_at ASC LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            cur = conn.execute(
                "UPDATE accounts SET status='running', updated_at=? WHERE id=? AND status IN ('queued','retrying')",
                (now, row["id"]),
            )
            if cur.rowcount == 0:
                return None
            updated = conn.execute("SELECT * FROM accounts WHERE id=?", (row["id"],)).fetchone()
            return dict(updated) if updated else dict(row)

    # ── Requeue (重学) ────────────────────────────────────────────────────────

    def requeue_account(self, account_id: int, preserve_extra_keys: list[str] | None = None) -> None:
        """
        重学语义：保留 cookies/user_profile/配置型字段，清除运行期数据，重新入队。
        preserve_extra_keys: 额外保留的 extra 字段（如 ['card_no']），默认 None。
        """
        now = time.time()
        account = self.get_account(account_id)
        if not account:
            return
        extra = json.loads(account.get("extra_json") or "{}")

        keep_keys = {"cookies", "user_profile", "card_no", "region", "report_mode", "remark"}
        if preserve_extra_keys:
            keep_keys.update(preserve_extra_keys)
        new_extra = {k: v for k, v in extra.items() if k in keep_keys}
        for key in _B_RUNTIME_EXTRA_KEYS:
            new_extra.pop(key, None)
        # A 型：仍清除 *_results 等运行期产出
        for k in list(new_extra.keys()):
            if k.endswith("_results"):
                new_extra.pop(k, None)
        for key in ("phase", "failed_phase", "error_log_text"):
            new_extra.pop(key, None)

        frm = account.get("status") or ""
        if frm != "queued":
            assert_account_transition(frm, "queued", force=True)

        with self._conn() as conn:
            conn.execute(
                "UPDATE accounts SET status='queued', status_msg='', retry_count=0, "
                "queued_at=?, updated_at=?, extra_json=? WHERE id=?",
                (now, now, json.dumps(new_extra, ensure_ascii=False), account_id),
            )
            conn.execute("DELETE FROM runs WHERE account_id=?", (account_id,))
            # [OPTIONAL:申请学分]
            conn.execute("DELETE FROM apply_queue WHERE account_id=?", (account_id,))
            conn.execute("DELETE FROM credit_applications WHERE account_id=?", (account_id,))
            # [END OPTIONAL:申请学分]

    # ── Runs ──────────────────────────────────────────────────────────────────

    def add_run(self, account_id: int, started_at: float, ended_at: float,
                result: str, summary: str = "", logs: list | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO runs (account_id,started_at,ended_at,result,summary,logs_json) "
                "VALUES (?,?,?,?,?,?)",
                (account_id, started_at, ended_at, result, summary,
                 json.dumps(logs or [], ensure_ascii=False)),
            )
            return cur.lastrowid

    def get_runs(self, account_id: int, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM runs WHERE account_id=? ORDER BY id DESC LIMIT ?",
                    (account_id, limit),
                ).fetchall()
            ]

    # ── [OPTIONAL:申请学分] apply_queue ──────────────────────────────────────

    def enqueue_apply(self, account_id: int, project_id: str,
                      subject_label: str = "", project_name: str = "",
                      credits: float | None = None, next_attempt_at: float = 0) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO apply_queue "
                "(account_id,project_id,subject_label,project_name,credits,status,next_attempt_at) "
                "VALUES (?,?,?,?,?,'pending',?) "
                "ON CONFLICT(account_id,project_id) DO UPDATE SET "
                "status='pending', attempts=0, last_error='', next_attempt_at=excluded.next_attempt_at",
                (account_id, project_id, subject_label, project_name, credits, next_attempt_at),
            )

    def claim_next_apply(self, now: float) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT aq.*, a.username, a.extra_json FROM apply_queue aq "
                "JOIN accounts a ON a.id=aq.account_id "
                "WHERE aq.status='pending' AND aq.next_attempt_at<=? "
                "ORDER BY aq.next_attempt_at ASC LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            assert_apply_transition(row["status"], "in_flight")
            conn.execute(
                "UPDATE apply_queue SET status='in_flight' WHERE id=? AND status='pending'",
                (row["id"],),
            )
            return dict(row)

    def finish_apply(self, apply_id: int, success: bool, message: str = "",
                     next_attempt_at: float = 0, dead: bool = False) -> None:
        now = time.time()
        if dead:
            status = "dead"
        elif success:
            status = "succeeded"
        else:
            status = "pending"
        with self._conn() as conn:
            row = conn.execute(
                "SELECT status FROM apply_queue WHERE id=?", (apply_id,),
            ).fetchone()
            if row:
                assert_apply_transition(row["status"], status)
            conn.execute(
                "UPDATE apply_queue SET status=?,attempts=attempts+1,last_error=?,"
                "next_attempt_at=? WHERE id=?",
                (status, "" if success else message, next_attempt_at, apply_id),
            )

    def pending_apply_count(self, account_id: int) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM apply_queue WHERE account_id=? AND status IN ('pending','in_flight')",
                (account_id,),
            ).fetchone()[0]

    def list_apply_tasks(self, account_id: int) -> list[dict]:
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM apply_queue WHERE account_id=? ORDER BY id ASC",
                    (account_id,),
                ).fetchall()
            ]

    def latest_apply_error(self, account_id: int) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_error FROM apply_queue WHERE account_id=? AND last_error != '' "
                "ORDER BY id DESC LIMIT 1",
                (account_id,),
            ).fetchone()
            return row["last_error"] if row else ""

    # [END OPTIONAL:申请学分]

    # ── KV store (scheduler state) ────────────────────────────────────────────

    def kv_get(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def is_paused(self) -> bool:
        return self.kv_get("scheduler.paused", "0") == "1"

    def set_paused(self, paused: bool) -> None:
        self.kv_set("scheduler.paused", "1" if paused else "0")

    def count_apply_success_today(self, account_id: int, *, day_start_ts: float) -> int:
        """今日 credit_applications 成功次数（A 型日申请配额）。"""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM credit_applications "
                "WHERE account_id=? AND success=1 AND applied_at>=?",
                (account_id, day_start_ts),
            ).fetchone()[0]

    # [OPTIONAL:AI学科映射] 未选 LLM 时删除以下方法
    def get_ai_subject_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mapping_json FROM ai_subject_cache WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["mapping_json"])

    def upsert_ai_subject_cache(
        self,
        cache_key: str,
        *,
        requirement_texts_json: str,
        catalog_snapshot_json: str,
        mapping_json: str,
    ) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ai_subject_cache "
                "(cache_key, requirement_texts_json, catalog_snapshot_json, mapping_json, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "requirement_texts_json=excluded.requirement_texts_json, "
                "catalog_snapshot_json=excluded.catalog_snapshot_json, "
                "mapping_json=excluded.mapping_json, updated_at=excluded.updated_at",
                (
                    cache_key,
                    requirement_texts_json,
                    catalog_snapshot_json,
                    mapping_json,
                    now,
                    now,
                ),
            )

    def delete_ai_subject_cache(self, cache_key: str | None = None) -> int:
        """cache_key=None 时清空整表（运维用）。"""
        with self._conn() as conn:
            if cache_key is None:
                cur = conn.execute("DELETE FROM ai_subject_cache")
            else:
                cur = conn.execute(
                    "DELETE FROM ai_subject_cache WHERE cache_key=?",
                    (cache_key,),
                )
            return cur.rowcount
    # [END OPTIONAL:AI学科映射]

    def ensure_scheduler_defaults(self) -> None:
        if not self.kv_get("scheduler.concurrency_limit", ""):
            self.set_concurrency_limit(DEFAULT_CONCURRENCY)

    def get_concurrency_limit(self) -> int:
        raw = self.kv_get("scheduler.concurrency_limit", "")
        if not raw:
            return DEFAULT_CONCURRENCY
        return int(raw)

    def set_concurrency_limit(self, limit: int) -> None:
        clamped = max(MIN_CONCURRENCY, min(MAX_CONCURRENCY, int(limit)))
        self.kv_set("scheduler.concurrency_limit", str(clamped))
