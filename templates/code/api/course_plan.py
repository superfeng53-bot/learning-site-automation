"""按项目需求学分规划课程（不必学完项目下全部课程）。

复制到 <pkg>/course_plan.py，对接站点字段名与 CourseService 方法。
参考实现：医学24 yixue24_api/course_plan.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .course import CourseService  # TODO: 改为实际 CourseService 路径

# ── TODO: 替换为站点 API 字段名 ─────────────────────────────────────────────
FIELD_PROJECT_REQUIRED = "N_ZXF"   # 项目需求总分（非考试门数 N_KKSJS）
FIELD_PROJECT_EARNED = "N_JGS"     # 站点已获学分
FIELD_COURSE_CREDITS = "N_XF"      # 单课学分
FIELD_LEARNED_MINUTES = "xxsj_fz"  # 已学分钟
FIELD_REQUIRED_MINUTES = "zdxxsc_fz"  # 最低学习分钟

_DEFAULT_MIN_STUDY_RATIO = 0.05  # 「进行中」阈值：避免 1 分钟误纳入计划


def project_required_credits(project: dict[str, Any]) -> float:
    """项目需求总分。"""
    return float(project.get(FIELD_PROJECT_REQUIRED) or project.get("N_KKSJS") or 0)


def project_earned_credits(project: dict[str, Any]) -> float:
    return float(project.get(FIELD_PROJECT_EARNED) or 0)


def passed_credits_from_courses(
    courses: list[dict[str, Any]],
    course_svc: "CourseService",
) -> float:
    return sum(
        float(course.get(FIELD_COURSE_CREDITS) or 0)
        for course in courses
        if course_svc.is_course_exam_passed(course)
    )


def effective_earned_credits(
    project_meta: dict[str, Any],
    courses: list[dict[str, Any]],
    course_svc: "CourseService",
) -> float:
    """已获学分 = max(站点 N_JGS, 计划内已通过课程学分之和)。"""
    return max(
        project_earned_credits(project_meta),
        passed_credits_from_courses(courses, course_svc),
    )


def _course_study_ratio(course: dict[str, Any]) -> float:
    learned = int(course.get(FIELD_LEARNED_MINUTES) or 0)
    required = int(course.get(FIELD_REQUIRED_MINUTES) or 900)
    if required <= 0:
        return 0.0
    return min(1.0, learned / required)


def _course_sort_key(
    course: dict[str, Any],
    course_svc: "CourseService",
    original_index: int,
    *,
    min_study_ratio: float = _DEFAULT_MIN_STUDY_RATIO,
) -> tuple[int, float, int]:
    """选课优先级（值越小越靠前）：已考完 → 已学完待考 → 在学 → 未开始。"""
    if course_svc.is_course_exam_passed(course):
        return (0, 0.0, original_index)
    if course_svc.is_course_study_done(course):
        return (1, 0.0, original_index)
    ratio = _course_study_ratio(course)
    if ratio >= min_study_ratio:
        return (2, -ratio, original_index)
    return (3, -ratio, original_index)


def sort_courses_by_priority(
    courses: list[dict[str, Any]],
    course_svc: "CourseService",
    *,
    min_study_ratio: float = _DEFAULT_MIN_STUDY_RATIO,
) -> list[dict[str, Any]]:
    indexed = list(enumerate(courses))
    return [
        course
        for _, course in sorted(
            indexed,
            key=lambda item: _course_sort_key(
                item[1], course_svc, item[0], min_study_ratio=min_study_ratio
            ),
        )
    ]


def _course_in_progress(
    course: dict[str, Any],
    course_svc: "CourseService",
    *,
    min_study_ratio: float = _DEFAULT_MIN_STUDY_RATIO,
) -> bool:
    if course_svc.is_course_exam_passed(course):
        return False
    if course_svc.is_course_study_done(course):
        return True
    return _course_study_ratio(course) >= min_study_ratio


@dataclass
class ProjectCoursePlan:
    display_courses: list[dict[str, Any]]
    actionable_courses: list[dict[str, Any]]
    earned_credits: float
    remaining_credits: float
    required_credits: float


def build_project_course_plan(
    project_meta: dict[str, Any],
    courses: list[dict[str, Any]],
    course_svc: "CourseService",
) -> ProjectCoursePlan:
    """构建项目课程规划：学分累加至需求上限即停。"""
    required = project_required_credits(project_meta)
    earned = effective_earned_credits(project_meta, courses, course_svc)
    remaining = max(0.0, required - earned) if required > 0 else 0.0
    use_credit_cap = required > 0

    ordered = sort_courses_by_priority(courses, course_svc)
    display: list[dict[str, Any]] = []
    actionable: list[dict[str, Any]] = []
    pending_remaining = remaining

    for course in ordered:
        if course_svc.is_course_exam_passed(course):
            display.append(course)
            continue

        credits = float(course.get(FIELD_COURSE_CREDITS) or 0)
        in_progress = _course_in_progress(course, course_svc)

        if in_progress:
            display.append(course)
            actionable.append(course)
            if use_credit_cap and credits > 0:
                pending_remaining = max(0.0, pending_remaining - credits)
            continue

        if use_credit_cap and pending_remaining <= 0:
            continue

        display.append(course)
        actionable.append(course)
        if use_credit_cap and credits > 0:
            pending_remaining = max(0.0, pending_remaining - credits)

    if not use_credit_cap:
        display = list(ordered)
        actionable = [c for c in ordered if not course_svc.is_course_exam_passed(c)]

    return ProjectCoursePlan(
        display_courses=display,
        actionable_courses=actionable,
        earned_credits=earned,
        remaining_credits=remaining,
        required_credits=required,
    )


def plan_actionable_courses(
    project_meta: dict[str, Any],
    courses: list[dict[str, Any]],
    course_svc: "CourseService",
) -> list[dict[str, Any]]:
    """Runner 待执行列表（已通过课程跳过）。"""
    return build_project_course_plan(project_meta, courses, course_svc).actionable_courses
