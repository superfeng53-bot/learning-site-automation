"""从站点 API 拉取已报名项目并计算 Web UI 展示用进度。

复制到 <svc>/project_sync.py，对接 CourseService 与 course_plan。
Phase 5 Web 控制台通过 POST /api/accounts/{id}/sync-projects 调用。
参考实现：医学24 yixue24_service/project_sync.py
"""
from __future__ import annotations

import math
from typing import Any

# TODO: 改为项目实际 import 路径
# from <pkg>.course import CourseService
# from <pkg>.course_plan import (
#     build_project_course_plan,
#     planned_credit_total,
#     project_required_credits,
#     sort_courses_by_priority,
# )


def _course_row(course: dict[str, Any], course_svc) -> dict[str, Any]:
    """将原始课程 dict 转为 Web UI 行。TODO: 对接站点字段名。"""
    learned = int(course.get("xxsj_fz") or 0)
    required = int(course.get("zdxxsc_fz") or 900)
    passed = course_svc.is_course_exam_passed(course)
    if passed:
        phase, pct = "passed", 100
    elif course_svc.course_needs_exam(course):
        phase, pct = "exam", 100
    elif course_svc.course_needs_study(course):
        phase = "study"
        pct = min(100, round(100 * learned / required)) if required else 0
    else:
        phase, pct = "pending", 0

    return {
        "course_id": int(course.get("N_KJXH") or 0),  # TODO
        "title": str(course.get("C_KJMC") or ""),
        "credits": float(course.get("N_XF") or 0),
        "learned_minutes": learned,
        "required_minutes": required,
        "status": str(course.get("C_KJZT") or ""),
        "phase": phase,
        "progress_percent": pct,
    }


def _progress_credits(
    *,
    earned_exam: float,
    planned_courses: list[dict[str, Any]],
    min_study_ratio: float = 0.05,
) -> float:
    """项目进度学分 = 已获 + 计划内未通过课的学时/考试折算。"""
    total = float(earned_exam)
    for row in planned_courses:
        if row.get("phase") == "passed":
            continue
        credits = float(row.get("credits") or 0)
        if credits <= 0:
            continue
        if row.get("phase") == "exam":
            total += credits
        elif row.get("phase") == "study":
            req = max(1, int(row.get("required_minutes") or 900))
            ratio = min(1.0, int(row.get("learned_minutes") or 0) / req)
            if ratio >= min_study_ratio:
                total += credits * ratio
    return total


def build_project_status(client) -> dict[str, Any]:
    """
    返回 extra_json.project_status 结构：
    { "<project_id>": { title, total_credits, earned_credits, progress_percent, courses, ... } }

    TODO: 实现 list_enrolled_projects / list_exam_projects / get_project_snapshot
    """
    from <pkg>.course import CourseService  # noqa: E999 — 复制后替换
    from <pkg>.course_plan import build_project_course_plan, sort_courses_by_priority  # noqa: E999

    course_svc = CourseService(client)
    enrolled = {
        int(p["N_XMXH"]): p
        for p in course_svc.list_enrolled_projects()
        if p.get("N_XMXH")
    }
    exam_projects = course_svc.list_exam_projects()

    out: dict[str, Any] = {}
    for proj in exam_projects:
        pid = int(proj.get("N_XMXH") or 0)
        if not pid:
            continue

        enrolled_meta = enrolled.get(pid, {})
        project_meta = {**enrolled_meta, **proj}
        snap = course_svc.get_project_snapshot(pid)
        all_raw = snap.get("courses") or []
        plan = build_project_course_plan(project_meta, all_raw, course_svc)
        planned_raw = plan.display_courses
        courses = [_course_row(c, course_svc) for c in planned_raw]
        total_credits = plan.required_credits or float(enrolled_meta.get("N_ZXF") or 0)
        earned = plan.earned_credits
        completed = course_svc.is_project_completed(project_meta, courses=all_raw)
        progress_credits = _progress_credits(earned_exam=earned, planned_courses=courses)
        credit_pct = (
            100.0 if completed
            else min(100.0, round(1000 * progress_credits / total_credits) / 10)
            if total_credits > 0 else 0.0
        )

        out[str(pid)] = {
            "title": str(proj.get("C_XMMC") or enrolled_meta.get("C_XMMC") or ""),
            "total_credits": total_credits,
            "earned_credits": earned,
            "progress_credits": round(progress_credits, 4),
            "remaining_credits": max(0.0, total_credits - progress_credits),
            "completed": completed,
            "planned_courses": len(courses),
            "actionable_courses": len(plan.actionable_courses),
            "progress_percent": credit_pct,
            "courses": courses,
        }

    return out


def merge_runtime_fields(
    synced: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """保留 worker 运行中写入的瞬时字段（若站点尚未刷新）。"""
    previous = previous or {}
    merged = dict(synced)
    for pid, row in merged.items():
        old = previous.get(pid) or {}
        if not row.get("current_course_title") and old.get("current_course_title"):
            row["current_course_title"] = old["current_course_title"]
            row["current_course_id"] = old.get("current_course_id")
    return merged
