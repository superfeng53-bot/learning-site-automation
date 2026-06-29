"""CourseRunner — 单门课端到端驱动（A 型；通用骨架）。

通用：join → 逐节学习 → 考试(有则) → 申请(可选) 的编排与 RunResult 汇总。
站点定制点：`_classify()` 的完成阈值、lesson 字段名（duration/play_time/study_id/completed）
—— phase 2 侦察站点 detail 接口后调整。

site_adapter.run_course() 可直接 `CourseRunner(course, study, exam, credit).run(project_id)`。
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from .adapter import ProgressProbeResult, RunResult, StageLog


class LessonPhase(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    STUCK = "stuck"            # 进度已存但低于阈值，需整段重放
    EXAM_PENDING = "exam_pending"
    DONE = "done"


class CourseRunner:
    #: 进度探针：与 phase2 侦察的站点 native step/interval 一致（须 step >= interval）。
    PROBE_STEP = 30
    PROBE_INTERVAL = 30

    def __init__(self, course_svc, study_svc, exam_svc=None, credit_svc=None,
                 *, complete_ratio: float = 0.95):
        self.course = course_svc
        self.study = study_svc
        self.exam = exam_svc
        self.credit = credit_svc
        self.complete_ratio = complete_ratio  # 站点定制点：完成判定阈值

    def run(self, project_id: str, *, apply_credit: bool = False) -> RunResult:
        result = RunResult(project_id=project_id)
        try:
            detail = self.course.get_detail(project_id)
            self._ensure_joined(project_id, detail, result)
            self._drive_lessons(project_id, detail, result)
            self._take_exam(project_id, detail, result)
            if apply_credit and self.credit is not None:
                self._apply_credit(project_id, result)
            result.final_state = "applied" if result.credit_applied else "learned"
        except Exception as exc:
            result.error = str(exc)
            result.final_state = "failed"
            result.logs.append(StageLog("runner", False, str(exc)))
        return result

    def probe_progress(
        self, project_id: str, *, probe_seconds: int = 60, min_delta: float = 1,
    ) -> ProgressProbeResult:
        result = ProgressProbeResult(ok=False, project_id=project_id, probe_seconds=probe_seconds)
        try:
            detail = self.course.get_detail(project_id)
            run_stub = RunResult(project_id=project_id)
            self._ensure_joined(project_id, detail, run_stub)
            result.logs.extend(run_stub.logs)
            lesson = self._first_incomplete_lesson(detail)
            if lesson is None:
                raise RuntimeError("no incomplete lesson to probe")
            result.lesson_id = str(lesson.get("id") or lesson.get("study_id") or "")
            before = self._lesson_play_time(lesson)
            result.play_time_before = before
            deadline = time.monotonic() + max(1, probe_seconds)
            play_time = before
            duration = lesson.get("duration", 0) or 0
            cap = duration * self.complete_ratio if duration else float("inf")
            while time.monotonic() < deadline:
                play_time = min(play_time + self.PROBE_STEP, cap)
                if play_time <= before:
                    break
                self._record_play_time(project_id, lesson, play_time, is_complete=0)
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.PROBE_INTERVAL)
            detail2 = self.course.get_detail(project_id)
            lesson2 = self._find_lesson(detail2, lesson) or lesson
            after = self._lesson_play_time(lesson2)
            result.play_time_after = after
            result.delta = after - before
            result.ok = result.delta >= min_delta
            result.logs.append(StageLog(
                "probe", result.ok, f"delta={result.delta:.1f}s (before={before}, after={after})",
            ))
            if not result.ok:
                result.error = f"progress delta {result.delta} < min_delta {min_delta}"
        except Exception as exc:
            result.error = str(exc)
            result.logs.append(StageLog("probe", False, str(exc)))
        return result

    def _ensure_joined(self, project_id, detail, result):
        if detail.get("joined"):
            result.joined = True
            result.logs.append(StageLog("join", True, "already joined"))
            return
        resp = self.study.join_project(project_id)
        result.joined = bool(getattr(resp, "ok", resp))
        result.logs.append(StageLog("join", result.joined, getattr(resp, "message", "")))
        if not result.joined:
            raise RuntimeError(f"join failed: {getattr(resp, 'message', '')}")

    def _drive_lessons(self, project_id, detail, result):
        for lesson in detail["lessons"]:
            phase = self._classify(lesson)
            if phase in (LessonPhase.DONE, LessonPhase.EXAM_PENDING):
                continue
            self._watch_lesson(project_id, lesson, resume=(phase == LessonPhase.IN_PROGRESS))
            result.logs.append(StageLog(f"lesson:{lesson.get('id')}", True, "watched"))
        result.watched = True

    def _classify(self, lesson) -> LessonPhase:
        if lesson.get("completed"):
            return LessonPhase.DONE
        if lesson.get("exam_pending"):
            return LessonPhase.EXAM_PENDING
        played = lesson.get("play_time", 0)
        duration = lesson.get("duration", 0) or 0
        if duration and played >= duration * self.complete_ratio:
            return LessonPhase.STUCK
        if played > 0:
            return LessonPhase.IN_PROGRESS
        return LessonPhase.NOT_STARTED

    def _first_incomplete_lesson(self, detail) -> Optional[dict]:
        for lesson in detail.get("lessons", []):
            if self._classify(lesson) not in (LessonPhase.DONE, LessonPhase.EXAM_PENDING):
                return lesson
        return None

    def _find_lesson(self, detail, target) -> Optional[dict]:
        tid = target.get("id") or target.get("study_id")
        for lesson in detail.get("lessons", []):
            if (lesson.get("id") or lesson.get("study_id")) == tid:
                return lesson
        return None

    def _lesson_play_time(self, lesson) -> float:
        return float(lesson.get("play_time", 0))

    def _record_play_time(self, project_id, lesson, play_time: float, *, is_complete: int) -> None:
        study_id = lesson.get("study_id") or lesson.get("id")
        if not hasattr(self.study, "record_play_time"):
            raise RuntimeError("StudyService.record_play_time not implemented")
        self.study.record_play_time(project_id, study_id, play_time, is_complete=is_complete)

    def _watch_lesson(self, project_id, lesson, *, resume: bool):
        start = lesson.get("play_time", 0) if resume else 0
        self.study.watch_video(project_id=project_id, study_id=lesson["study_id"],
                               duration=lesson["duration"], start_at=start)

    def _take_exam(self, project_id, detail, result):
        if not detail.get("has_exam"):
            result.exam_passed = True
            return
        if self.exam is None:
            raise RuntimeError("course has exam but ExamService not configured")
        outcome = self.exam.pass_exam(project_id, detail["exam_study_id"])
        result.exam_passed = bool(getattr(outcome, "ok", outcome))
        result.logs.append(StageLog("exam", result.exam_passed, getattr(outcome, "message", "")))
        if not result.exam_passed:
            raise RuntimeError(f"exam failed: {getattr(outcome, 'message', '')}")

    def _apply_credit(self, project_id, result):
        if self.credit is None:
            raise RuntimeError("apply_credit requested but CreditService not configured")
        outcome = self.credit.apply_credit(project_id, auto_survey=True)
        result.credit_applied = bool(getattr(outcome, "ok", outcome))
        result.logs.append(StageLog("credit", result.credit_applied,
                                    getattr(outcome, "message", ""),
                                    detail={"code": getattr(outcome, "code", None),
                                            "hint": getattr(outcome, "hint", "")}))
