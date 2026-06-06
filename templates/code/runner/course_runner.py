"""
单账号课程运行器（A 型：学科规划型）。
复制到 <pkg>/course_runner.py，然后调整：
  - _classify() 阈值（95% → 站点实际完成线，常见 98%/100%）
  - _watch_lesson() 参数名（适配站点 StudyService.watch_video 签名）
  - _take_exam() / _apply_credit() 按确认的能力范围启用/禁用

B 型（公需年度型）：使用 year_runner.py，不使用本文件。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── 枚举 & 数据类 ────────────────────────────────────────────────────────────

class LessonPhase(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS  = "in_progress"
    STUCK        = "stuck"        # progress 保存但低于完成阈值，需从头重跑
    EXAM_PENDING = "exam_pending"
    DONE         = "done"


@dataclass
class StageLog:
    stage:   str
    ok:      bool
    message: str = ""
    detail:  dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    project_id:    str
    joined:        bool  = False
    watched:       bool  = False
    exam_passed:   bool  = False
    credit_applied: bool = False
    final_state:   str   = "running"   # learned | applied | failed
    logs:          list[StageLog] = field(default_factory=list)
    error:         Optional[str]  = None


@dataclass
class ProgressProbeResult:
    """整课跑通前的 60 秒进度增量门禁结果。"""
    ok:               bool
    project_id:       str
    lesson_id:        str = ""
    play_time_before: float = 0
    play_time_after:  float = 0
    delta:            float = 0
    probe_seconds:    int = 60
    error:            Optional[str] = None
    logs:             list[StageLog] = field(default_factory=list)


# ── Runner ───────────────────────────────────────────────────────────────────

class CourseRunner:
    """
    组合模式：把 service 层对象注入进来。
    exam_svc 和 credit_svc 传 None 表示站点不需要该流程。
    """

    #: 视频完成阈值（已播放 / 总时长）。根据站点 JS 逻辑调整。
    WATCH_THRESHOLD = 0.95
    #: 进度探针：模拟步长与墙钟间隔（与 phase2 watch_video 校准值一致）。
    PROBE_STEP = 30
    PROBE_INTERVAL = 31

    def __init__(self, course_svc, study_svc, exam_svc=None, credit_svc=None):
        self.course  = course_svc
        self.study   = study_svc
        self.exam    = exam_svc    # [OPTIONAL:考试] 无考试流程传 None
        self.credit  = credit_svc  # [OPTIONAL:申请学分] 无申请流程传 None

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
        self,
        project_id: str,
        *,
        probe_seconds: int = 60,
        min_delta: float = 1,
    ) -> ProgressProbeResult:
        """
        整课测试前的门禁：约 probe_seconds 墙钟内上报进度，断言服务端 play_time 增加。
        不得在探针期间把章节标为完成。
        """
        result = ProgressProbeResult(ok=False, project_id=project_id, probe_seconds=probe_seconds)
        try:
            detail = self.course.get_detail(project_id)
            run_stub = RunResult(project_id=project_id)
            self._ensure_joined(project_id, detail, run_stub)
            result.logs.extend(run_stub.logs)

            lesson = self._first_incomplete_lesson(detail)
            if lesson is None:
                raise RuntimeError("no incomplete lesson to probe (course may already be done)")

            result.lesson_id = str(lesson.get("id") or lesson.get("study_id") or "")
            before = self._lesson_play_time(lesson)
            result.play_time_before = before

            deadline = time.monotonic() + max(1, probe_seconds)
            play_time = before
            duration = lesson.get("duration") or lesson.get("total_seconds") or 0
            cap = duration * self.WATCH_THRESHOLD if duration else float("inf")

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
                "probe", result.ok,
                f"delta={result.delta:.1f}s (before={before}, after={after})",
            ))
            if not result.ok:
                result.error = f"progress delta {result.delta} < min_delta {min_delta}"
        except Exception as exc:
            result.error = str(exc)
            result.logs.append(StageLog("probe", False, str(exc)))
        return result

    # ── 加入课程 ──────────────────────────────────────────────────────────────

    def _ensure_joined(self, project_id: str, detail: dict, result: RunResult) -> None:
        if detail.get("joined"):
            result.joined = True
            result.logs.append(StageLog("join", True, "already joined"))
            return
        resp = self.study.join_project(project_id)
        result.joined = resp.ok
        result.logs.append(StageLog("join", resp.ok, resp.message))
        if not resp.ok:
            raise RuntimeError(f"join failed: {resp.message}")

    # ── 驱动视频章节 ──────────────────────────────────────────────────────────

    def _drive_lessons(self, project_id: str, detail: dict, result: RunResult) -> None:
        for lesson in detail.get("lessons", []):
            phase = self._classify(lesson)
            if phase in (LessonPhase.DONE, LessonPhase.EXAM_PENDING):
                continue
            self._watch_lesson(
                project_id, lesson,
                resume=(phase == LessonPhase.IN_PROGRESS),
            )
            result.logs.append(StageLog(f"lesson:{lesson.get('id','?')}", True, "watched"))
        result.watched = True

    def _classify(self, lesson: dict) -> LessonPhase:
        """
        根据站点返回的 lesson 字段判断播放状态。
        ⚠️ 阈值和字段名必须按站点实际调整：
          - 完成标记字段（completed / finished / status）
          - 进度字段（play_time / progress / watched_seconds）
          - 总时长字段（duration / total_seconds）
        """
        if lesson.get("completed") or lesson.get("finished"):
            return LessonPhase.DONE
        if lesson.get("exam_pending"):
            return LessonPhase.EXAM_PENDING
        played   = lesson.get("play_time") or lesson.get("progress") or 0
        duration = lesson.get("duration")  or lesson.get("total_seconds") or 1
        ratio    = played / max(duration, 1)
        if ratio >= self.WATCH_THRESHOLD:
            return LessonPhase.STUCK
        if played > 0:
            return LessonPhase.IN_PROGRESS
        return LessonPhase.NOT_STARTED

    def _first_incomplete_lesson(self, detail: dict) -> Optional[dict]:
        for lesson in detail.get("lessons", []):
            if self._classify(lesson) not in (LessonPhase.DONE, LessonPhase.EXAM_PENDING):
                return lesson
        return None

    def _find_lesson(self, detail: dict, target: dict) -> Optional[dict]:
        tid = target.get("id") or target.get("study_id")
        for lesson in detail.get("lessons", []):
            lid = lesson.get("id") or lesson.get("study_id")
            if tid and lid == tid:
                return lesson
        return None

    def _lesson_play_time(self, lesson: dict) -> float:
        return float(lesson.get("play_time") or lesson.get("progress") or 0)

    def _record_play_time(
        self, project_id: str, lesson: dict, play_time: float, *, is_complete: int,
    ) -> None:
        """调用 StudyService.record_play_time；无此方法时回退 watch_video 的单次上报。"""
        study_id = lesson.get("study_id") or lesson.get("id")
        if hasattr(self.study, "record_play_time"):
            self.study.record_play_time(
                project_id, study_id, play_time, is_complete=is_complete,
            )
            return
        raise RuntimeError("StudyService.record_play_time not implemented — required for probe_progress")

    def _watch_lesson(self, project_id: str, lesson: dict, *, resume: bool) -> None:
        """
        调用 StudyService.watch_video。
        ⚠️ 参数名和字段名需按站点实际调整（study_id / lesson_id / chapter_id 等）。
        """
        start = lesson.get("play_time", 0) if resume else 0
        self.study.watch_video(
            project_id = project_id,
            study_id   = lesson["study_id"],   # TODO: 按站点字段名修改
            duration   = lesson["duration"],
            start_at   = start,
        )

    # ── 考试 ─────────────────────────────────────────────────────────────────

    def _take_exam(self, project_id: str, detail: dict, result: RunResult) -> None:
        """[OPTIONAL:考试] 站点无考试时 result.exam_passed=True 直接返回。"""
        if not detail.get("has_exam"):
            result.exam_passed = True
            result.logs.append(StageLog("exam", True, "site has no exam flow"))
            return
        if self.exam is None:
            raise RuntimeError("course has exam but ExamService is not configured")
        outcome = self.exam.pass_exam(project_id, detail.get("exam_study_id", ""))
        result.exam_passed = outcome.ok
        result.logs.append(StageLog("exam", outcome.ok, outcome.message))
        if not outcome.ok:
            raise RuntimeError(f"exam failed: {outcome.message}")

    # ── 申请学分 ──────────────────────────────────────────────────────────────

    def _apply_credit(self, project_id: str, result: RunResult) -> None:
        """[OPTIONAL:申请学分] 站点无申请流程时不调用本方法。"""
        if self.credit is None:
            raise RuntimeError("credit application in scope but CreditService is not configured")
        outcome = self.credit.apply_credit(project_id, auto_survey=True)
        result.credit_applied = outcome.ok
        result.logs.append(StageLog("credit", outcome.ok, outcome.message,
                                    detail={"code": getattr(outcome,"code",""),
                                            "hint": getattr(outcome,"hint","")}))
        if not outcome.ok:
            raise RuntimeError(f"credit apply failed: {outcome.message}")


# ── B 型年度任务运行器（公需年度型）────────────────────────────────────────────

@dataclass
class YearTaskResult:
    year:          str
    success:       bool
    earned_hours:  float = 0.0
    required_hours: float = 0.0
    summary:       str = ""
    error:         Optional[str] = None
    logs:          list[StageLog] = field(default_factory=list)


class YearTaskRunner:
    """
    [OPTIONAL:B型] 公需年度型站点使用本 runner 替代 CourseRunner。
    Phase 5 Worker 在 `for year in account.target_years` 中调用 run_year()。
    """

    def __init__(self, task_svc, study_svc, exam_svc=None):
        self.task  = task_svc
        self.study = study_svc
        self.exam  = exam_svc   # [OPTIONAL:考试]

    def run_year(self, year: str, report_mode: str = "normal") -> YearTaskResult:
        result = YearTaskResult(year=year, success=False)
        try:
            year_info = self.task.get_year_info(year)
            result.required_hours = year_info.get("required_hours", 0)
            result.earned_hours   = year_info.get("earned_hours",   0)

            if result.earned_hours >= result.required_hours > 0:
                result.success = True
                result.summary = f"{year} 年已完成（{result.earned_hours}/{result.required_hours} 小时）"
                result.logs.append(StageLog("year_check", True, result.summary))
                return result

            courses = self.task.get_pending_courses(year)
            for course in courses:
                self._study_course(year, course, result)
                if self.exam and course.get("has_exam"):
                    self._take_exam_year(year, course, result)

            year_info2 = self.task.get_year_info(year)
            result.earned_hours = year_info2.get("earned_hours", 0)
            result.success = result.earned_hours >= result.required_hours
            result.summary = f"{year} 年：{result.earned_hours}/{result.required_hours} 小时"
        except Exception as exc:
            result.error = str(exc)
            result.logs.append(StageLog("year_runner", False, str(exc)))
        return result

    def _study_course(self, year: str, course: dict, result: YearTaskResult) -> None:
        cid = course.get("id") or course.get("course_id", "")
        resp = self.study.study_course(year=year, course_id=cid)  # TODO: 按站点接口名调整
        ok   = getattr(resp, "ok", bool(resp))
        msg  = getattr(resp, "message", str(resp))
        result.logs.append(StageLog(f"study:{cid}", ok, msg))
        if not ok:
            raise RuntimeError(f"study_course failed: {msg}")

    def _take_exam_year(self, year: str, course: dict, result: YearTaskResult) -> None:
        cid = course.get("id") or course.get("course_id", "")
        outcome = self.exam.pass_exam(year=year, course_id=cid)  # TODO: 按站点接口名调整
        result.logs.append(StageLog(f"exam:{cid}", outcome.ok, outcome.message))
        if not outcome.ok:
            raise RuntimeError(f"exam failed: {outcome.message}")
