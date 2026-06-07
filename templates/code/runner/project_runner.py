"""B′ 型单账号项目流水线：study courseware then take exam。

复制到 <pkg>/project_task.py（或 project_runner.py），对接 CourseService / StudyService / ExamService。
Runner 只跑 course_plan.plan_actionable_courses() 返回的计划课程。
参考实现：医学24 yixue24_api/project_task.py
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# TODO: 改为项目实际 import
# from .client import HttpClient
# from .course import CourseService
# from .exam import ExamService
# from .study import StudyService


@dataclass
class CourseTaskResult:
    project_id: int
    course_id: int
    course_name: str
    study: dict[str, Any] = field(default_factory=dict)
    exam: dict[str, Any] | None = None
    skipped: str = ""
    error: str = ""


@dataclass
class ProjectTaskResult:
    project_id: int
    project_name: str
    completed: bool
    courses: list[CourseTaskResult] = field(default_factory=list)
    skipped: str = ""


class ProjectTaskRunner:
    def __init__(
        self,
        client,
        *,
        report_interval_sec: int = 90,
        dry_run: bool = False,
    ) -> None:
        from .course import CourseService  # noqa: PLC0415
        from .exam import ExamService
        from .study import StudyService

        self.course_svc = CourseService(client)
        self.study_svc = StudyService(client)
        self.exam_svc = ExamService(client)
        self.report_interval_sec = report_interval_sec
        self.dry_run = dry_run

    def list_pending_projects(self) -> list[dict[str, Any]]:
        projects = self.course_svc.list_exam_projects()
        return [p for p in projects if not self.course_svc.is_project_completed(p)]

    def list_pending_courses(self, project_id: int) -> list[dict[str, Any]]:
        """只跑 course_plan 规划出的 actionable 课程。"""
        return self.course_svc.list_actionable_courses(project_id)

    def run_course(
        self,
        project_id: int,
        course: dict[str, Any],
        *,
        max_study_rounds: int | None = None,
    ) -> CourseTaskResult:
        course_id = int(course["N_KJXH"])  # TODO: 字段名
        result = CourseTaskResult(
            project_id=project_id,
            course_id=course_id,
            course_name=str(course.get("C_KJMC") or ""),
        )
        try:
            if self.course_svc.course_needs_study(course):
                if self.dry_run:
                    result.skipped = "dry_run: would study"
                else:
                    result.study = self.study_svc.report_until_complete(
                        project_id,
                        course_id,
                        interval_sec=self.report_interval_sec,
                        max_rounds=max_study_rounds,
                    )
            elif self.course_svc.is_course_study_done(course):
                result.study = {"completed": True, "already_done": True}

            refreshed = self._find_course(project_id, course_id) or course
            if self.course_svc.course_needs_exam(refreshed) or (
                result.study.get("completed")
                and not self.course_svc.is_course_exam_passed(refreshed)
            ):
                if self.dry_run:
                    result.skipped = (result.skipped + "; dry_run: would exam").strip("; ")
                else:
                    result.exam = self.exam_svc.take_exam(project_id, course_id)
                    if not result.exam.get("passed"):
                        score = result.exam.get("score")
                        result.error = f"考试未通过（得分 {score}）"
        except Exception as exc:
            result.error = str(exc)
        return result

    def _find_course(self, project_id: int, course_id: int) -> dict[str, Any] | None:
        for row in self.course_svc.get_project_snapshot(project_id)["courses"]:
            if int(row.get("N_KJXH") or 0) == course_id:
                return row
        return None

    def run_project(
        self,
        project_id: int,
        *,
        max_study_rounds: int | None = None,
        on_course_start: Callable[[dict[str, Any]], None] | None = None,
    ) -> ProjectTaskResult:
        exam_projects = {
            int(p["N_XMXH"]): p for p in self.course_svc.list_exam_projects()
        }
        meta = exam_projects.get(project_id, {})
        out = ProjectTaskResult(
            project_id=project_id,
            project_name=str(meta.get("C_XMMC") or ""),
            completed=self.course_svc.is_project_completed(meta) if meta else False,
        )
        if out.completed:
            out.skipped = "project already completed"
            return out

        for course in self.list_pending_courses(project_id):
            if on_course_start:
                on_course_start(course)
            out.courses.append(
                self.run_course(project_id, course, max_study_rounds=max_study_rounds)
            )
            if out.courses[-1].error:
                break
            refreshed = self.course_svc.list_exam_projects()
            current = next(
                (p for p in refreshed if int(p["N_XMXH"]) == project_id), None
            )
            if current and self.course_svc.is_project_completed(current):
                out.completed = True
                break
        return out

    def run_account(
        self,
        *,
        max_study_rounds: int | None = None,
        on_course_start: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[ProjectTaskResult]:
        results: list[ProjectTaskResult] = []
        for project in self.list_pending_projects():
            results.append(
                self.run_project(
                    int(project["N_XMXH"]),
                    max_study_rounds=max_study_rounds,
                    on_course_start=on_course_start,
                )
            )
        return results
