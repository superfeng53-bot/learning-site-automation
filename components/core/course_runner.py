"""CourseRunner — 单门课端到端驱动（A 型；通用骨架）。

通用：join → 逐节学习 → 考试(有则) → 申请(可选) 的编排与 RunResult 汇总。
站点定制点：`_classify()` 的完成阈值、lesson 字段名（duration/play_time/study_id/completed）
—— phase 2 侦察站点 detail 接口后调整。

site_adapter.run_course() 可直接 `CourseRunner(course, study, exam, credit).run(project_id)`。
"""
from __future__ import annotations

from enum import Enum

from .adapter import RunResult, StageLog


class LessonPhase(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    STUCK = "stuck"            # 进度已存但低于阈值，需整段重放
    EXAM_PENDING = "exam_pending"
    DONE = "done"


class CourseRunner:
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
