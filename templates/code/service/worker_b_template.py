"""B 型公需年度 Worker 模板（含课节进度同步）。

复制到 <svc>/worker.py，替换 <PKG> 为实际包名，并按站点调整 fetch_member_profile / get_session_probe。
详见 progress-sync.md。
"""
from __future__ import annotations

import json
import time
from typing import Any

from <PKG>.captcha_limiter import get_cooldown_remaining  # TODO: 若无可删
from <PKG>.progress_snapshot import (
    TARGET_PUBLIC_HOURS,
    build_learning_progress,
    build_year_progress,
    format_status_msg,
    fraction_to_display_percent,
    percent_label,
    resolve_snapshot_progress,
    snapshot_hour,
)
from <PKG>.year_task import run_year_task

from .worker_base import AccountWorkerBase, PipelineResult


class AccountWorker(AccountWorkerBase):
    PROGRESS_TICK_INTERVAL = 20.0

    def run_pipeline(self, account: dict, client) -> PipelineResult:
        return PipelineResult(
            success=False,
            final_state="failed",
            status_msg="本站为 B 型公需年度，请使用 run_year_pipeline",
            hard_failure=True,
        )

    def get_session_probe(self):
        user_id = str(self._account["id"])
        return lambda: self._sm.profile_probe(user_id)  # TODO

    def fetch_member_profile(self, client) -> dict[str, Any]:
        data = self._sm.get_member_service(str(self._account["id"])).get_profile()
        # TODO: map realName / idCard fields
        real_name = str(data.get("realName") or data.get("userName") or "").strip()
        return {
            "display_name": real_name,
            "real_name": real_name,
            "id_card": str(data.get("idCard") or data.get("idcard") or "").strip(),
            "user_profile": data,
        }

    def _merge_extra(self, acc_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        account = self._store.get_account(acc_id) or {}
        extra = json.loads(account.get("extra_json") or "{}")
        extra.update(patch)
        self._store.update_extra(acc_id, extra)
        return extra

    def _refresh_year_snapshot(
        self,
        acc_id: int,
        user_id: str,
        year: str,
        *,
        active_course_id: str | None = None,
    ) -> dict[str, Any]:
        course_svc = self._sm.get_course_service(user_id)
        study_svc = self._sm.get_study_service(user_id)
        cert_svc = self._sm.get_certificate_service(user_id)
        snapshot = build_year_progress(
            course_svc,
            study_svc,
            year,
            target_hours=TARGET_PUBLIC_HOURS,
            active_course_id=active_course_id,
            cert_svc=cert_svc,
        )
        account = self._store.get_account(acc_id) or {}
        extra = json.loads(account.get("extra_json") or "{}")
        year_status = dict(extra.get("year_status") or {})
        prev = dict(year_status.get(str(year)) or {})
        prev.update(snapshot)
        year_status[str(year)] = prev
        extra["year_status"] = year_status
        extra["progress_percent"] = resolve_snapshot_progress(snapshot)
        self._store.update_extra(acc_id, extra)
        return snapshot

    def _hour_snap_live(
        self,
        study_svc,
        course_id: str,
        hour: dict[str, Any],
        play_seconds: int,
    ) -> dict[str, Any]:
        hour_id = str(hour.get("hour_id") or "")
        try:
            snap = snapshot_hour(study_svc, course_id, hour_id)
        except Exception:
            snap = {
                "hour_id": hour_id,
                "title": hour.get("title") or "",
                "hour_title": hour.get("title") or "",
                "chapter_title": hour.get("chapter_title") or "",
                "percent": 0,
                "percent_name": "0%",
            }
        title = str(
            snap.get("hour_title") or snap.get("title") or hour.get("title") or "",
        )
        snap["title"] = title
        snap["hour_title"] = title
        total = int(snap.get("total_seconds") or hour.get("total_seconds") or 0)
        learned = int(play_seconds or snap.get("learned_seconds") or 0)
        api_frac = float(snap.get("percent") or 0)
        live_frac = min(1.0, learned / total) if total > 0 else 0.0
        frac = max(api_frac, live_frac)
        snap["percent"] = frac
        snap["percent_name"] = percent_label(frac)
        snap["learned_seconds"] = learned
        snap["total_seconds"] = total
        return snap

    def run_year_pipeline(self, account: dict, client, year: str) -> PipelineResult:
        acc_id = account["id"]
        username = account["username"]
        password = account["password"]
        extra = json.loads(account.get("extra_json") or "{}")
        user_id = str(acc_id)
        report_mode = extra.get("report_mode") or "normal"
        course_svc = self._sm.get_course_service(user_id)
        study_svc = self._sm.get_study_service(user_id)
        last_tick_write = [0.0]
        last_snapshot_write = [0.0]

        def on_phase(phase: str, msg: str) -> None:
            cur_extra = json.loads((self._store.get_account(acc_id) or account).get("extra_json") or "{}")
            cur_extra["phase"] = phase
            cur_extra["current_year"] = year
            if phase == "video_play" and "：" in msg:
                cur_extra["current_course_title"] = msg.split("：", 1)[-1]
            self._store.update_extra(acc_id, cur_extra)

        def on_hour_start(course_id: str, course_title: str, hour: dict[str, str]) -> None:
            hour_id = hour.get("hour_id") or ""
            try:
                hour_snap = snapshot_hour(study_svc, course_id, hour_id)
            except Exception:
                hour_snap = {
                    "hour_id": hour_id,
                    "hour_title": hour.get("title") or "",
                    "chapter_title": "",
                    "percent": 0,
                    "percent_name": "0%",
                }
            learning = build_learning_progress(
                year=year,
                course_id=course_id,
                course_title=course_title,
                hour_snapshot=hour_snap,
            )
            status = format_status_msg(
                year, course_title,
                hour_snap.get("hour_title") or hour.get("title") or "",
                hour_snap.get("percent_name") or "",
            )
            self._store.update_account_status(acc_id, "running", status)
            try:
                snapshot = self._refresh_year_snapshot(
                    acc_id, user_id, year, active_course_id=course_id,
                )
                progress = resolve_snapshot_progress(snapshot)
            except Exception:
                progress = 0
            self._merge_extra(acc_id, {
                "learning_progress": learning,
                "current_course_id": course_id,
                "current_course_title": course_title,
                "progress_percent": progress,
            })

        def on_progress_tick(course_id: str, course_title: str, hour: dict[str, str], play_seconds: int) -> None:
            now = time.monotonic()
            if now - last_tick_write[0] < self.PROGRESS_TICK_INTERVAL:
                return
            last_tick_write[0] = now
            hour_snap = self._hour_snap_live(study_svc, course_id, hour, play_seconds)
            learning = build_learning_progress(
                year=year, course_id=course_id, course_title=course_title, hour_snapshot=hour_snap,
            )
            status = format_status_msg(
                year, course_title,
                hour_snap.get("hour_title") or hour.get("title") or "",
                hour_snap.get("percent_name") or "",
            )
            self._store.update_account_status(acc_id, "running", status)
            patch: dict[str, Any] = {"learning_progress": learning}
            if now - last_snapshot_write[0] >= 60.0:
                last_snapshot_write[0] = now
                try:
                    snapshot = self._refresh_year_snapshot(
                        acc_id, user_id, year, active_course_id=course_id,
                    )
                    patch["progress_percent"] = resolve_snapshot_progress(snapshot)
                    ys = dict(
                        json.loads((self._store.get_account(acc_id) or {}).get("extra_json") or "{}")
                        .get("year_status") or {},
                    )
                    ys[str(year)] = {**(ys.get(str(year)) or {}), **snapshot}
                    patch["year_status"] = ys
                except Exception:
                    pass
            self._merge_extra(acc_id, patch)

        def on_hour_complete(course_id: str, course_title: str, hour: dict[str, str], _resp) -> None:
            snapshot = self._refresh_year_snapshot(
                acc_id, user_id, year, active_course_id=course_id,
            )
            hour_id = hour.get("hour_id") or ""
            try:
                hour_snap = snapshot_hour(study_svc, course_id, hour_id)
            except Exception:
                hour_snap = {"hour_id": hour_id, "hour_title": hour.get("title") or "", "percent_name": "100%"}
            learning = build_learning_progress(
                year=year, course_id=course_id, course_title=course_title, hour_snapshot=hour_snap,
            )
            status = format_status_msg(
                year, course_title,
                hour_snap.get("hour_title") or hour.get("title") or "",
                hour_snap.get("percent_name") or "",
            )
            self._store.update_account_status(acc_id, "running", status)
            self._merge_extra(acc_id, {
                "learning_progress": learning,
                "progress_percent": resolve_snapshot_progress(snapshot),
            })

        def _execute(_client):
            return run_year_task(
                course_svc,
                study_svc,
                self._sm.get_certificate_service(user_id),
                self._sm.get_exam_service(user_id),
                year,
                report_mode=report_mode,
                on_phase=on_phase,
                on_hour_start=on_hour_start,
                on_hour_complete=on_hour_complete,
                on_progress_tick=on_progress_tick,
            )

        try:
            result = self.call_with_session_retry(acc_id, username, password, extra, _execute)
        except Exception as exc:
            msg = str(exc)
            hard = self._is_hard_auth_error(msg)
            if "验证码" in msg and get_cooldown_remaining() > 0:
                hard = False
            return PipelineResult(
                success=False, final_state="failed", status_msg=msg, error=msg, hard_failure=hard,
            )

        logs = [{"stage": result.phase, "ok": result.ok, "message": result.message, "year": result.year}]
        extra_updates: dict[str, Any] = {}
        try:
            final_snapshot = self._refresh_year_snapshot(acc_id, user_id, year)
        except Exception:
            final_snapshot = {}
        year_status = dict(extra.get("year_status") or {})
        year_entry = dict(year_status.get(str(year)) or {})
        year_entry.update(final_snapshot)
        year_entry.update({
            "ok": result.ok, "skipped": result.skipped, "phase": result.phase, "message": result.message,
        })
        year_status[str(year)] = year_entry
        extra_updates["year_status"] = year_status
        extra_updates["progress_percent"] = resolve_snapshot_progress(
            final_snapshot or year_entry,
        )
        if result.certificate:
            extra_updates["certificate_status"] = result.certificate

        cur_extra = json.loads((self._store.get_account(acc_id) or account).get("extra_json") or "{}")
        cur_extra.update(extra_updates)
        self._store.update_extra(acc_id, cur_extra)

        if result.ok or result.skipped:
            return PipelineResult(
                success=True, final_state="completed", status_msg=result.message,
                logs=logs, extra_updates=extra_updates,
            )

        hard = result.phase in ("purchase_check",) and "未购" in result.message
        return PipelineResult(
            success=False, final_state="failed", status_msg=result.message, error=result.message,
            logs=logs, extra_updates=extra_updates, hard_failure=hard,
        )
