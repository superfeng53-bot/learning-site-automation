"""Build learning progress snapshots from site APIs for Worker / Web UI.

Copy to <pkg>/progress_snapshot.py and fill TODO blocks with site-specific endpoints.
Reference implementation: SCZJ (annual_completion + getLearnInfo + get_hour_progress).
See progress-sync.md in the skill root.
"""
from __future__ import annotations

from typing import Any

# TODO: site annual public-hours target (e.g. 30 for 公需)
TARGET_PUBLIC_HOURS = 30


def _float_percent(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def percent_label(percent: float, percent_name: str = "") -> str:
    if percent_name:
        return str(percent_name)
    if percent >= 1:
        return "100%"
    return f"{int(round(percent * 100))}%"


def collect_learn_hours(study_svc, course_id: str) -> list[dict[str, Any]]:
    """TODO: map site learn-tree API → list of hour dicts."""
    hours: list[dict[str, Any]] = []
    for chapter in study_svc.get_learn_tree(course_id):  # TODO: method name
        chapter_title = str(chapter.get("title") or chapter.get("name") or "")
        for child in chapter.get("children") or []:
            pct = _float_percent(child.get("percent"))
            hours.append({
                "hour_id": str(child.get("id") or ""),
                "title": str(child.get("title") or child.get("name") or ""),
                "chapter_title": chapter_title,
                "percent": pct,
                "percent_name": str(child.get("percentName") or percent_label(pct)),
                "finished": pct >= 1.0,
            })
    return hours


def snapshot_hour(
    study_svc,
    course_id: str,
    hour_id: str,
    *,
    learn_hours: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """TODO: read single hour progress from getVideo / learn tree."""
    hp = study_svc.get_hour_progress(course_id, hour_id)  # TODO: HourProgress shape
    if learn_hours is None:
        learn_hours = collect_learn_hours(study_svc, course_id)

    hour_title = ""
    chapter_title = ""
    for item in learn_hours:
        if item["hour_id"] == str(hour_id):
            hour_title = item["title"]
            chapter_title = item["chapter_title"]
            break

    pct = hp.percent
    if not pct and getattr(hp, "duration", 0):
        pct = min(1.0, hp.seconds / hp.duration)

    return {
        "hour_id": str(hour_id),
        "hour_title": hour_title,
        "chapter_title": chapter_title,
        "percent": pct,
        "percent_name": getattr(hp, "percent_name", "") or percent_label(pct),
        "seconds": getattr(hp, "seconds", 0),
        "duration": getattr(hp, "duration", 0),
    }


def build_year_progress(
    course_svc,
    study_svc,
    year: str | int,
    *,
    target_hours: int = TARGET_PUBLIC_HOURS,
    active_course_id: str | None = None,
    cert_svc=None,
) -> dict[str, Any]:
    """TODO: pull annual totals + enrolled courses from server."""
    year_str = str(year)
    annual = course_svc.annual_completion(year_str)  # TODO: endpoint + field names
    public_num = int(annual.get("publicNum") or 0)  # TODO: earned hours field
    required = int(target_hours)
    progress_percent = min(100, round(100 * public_num / required)) if required > 0 else 0

    cert_row = None
    if cert_svc is not None:
        try:
            cert_row = cert_svc.get_year_certificate(year_str)
            if cert_row and int(cert_row.get("auditStatus") or -1) == 1:
                public_num = required
                progress_percent = 100
        except Exception:
            cert_row = None

    enrolled = course_svc.list_year_enrolled(year_str)  # TODO: filter by nature if needed

    courses: list[dict[str, Any]] = []
    current_course_id = ""
    current_course_title = ""

    for row in enrolled:
        course_id = str(row["id"])
        title = str(row.get("courseName") or course_id)
        finished = course_svc.course_is_finished(row)
        pct = _float_percent(row.get("percent"))
        entry: dict[str, Any] = {
            "course_id": course_id,
            "title": title,
            "percent": pct,
            "percent_name": str(row.get("percentName") or percent_label(pct)),
            "finished": finished,
        }
        if course_id == active_course_id or (active_course_id is None and not finished):
            try:
                entry["hours"] = collect_learn_hours(study_svc, course_id)
            except Exception:
                entry["hours"] = []
        if not finished and not current_course_id:
            current_course_id = course_id
            current_course_title = title
        courses.append(entry)

    course_learning_percent = 0
    if courses:
        active_pcts = [
            _float_percent(c.get("percent"))
            for c in courses
            if not c.get("finished") and _float_percent(c.get("percent")) > 0
        ]
        if active_pcts:
            course_learning_percent = round(100 * sum(active_pcts) / len(active_pcts))
        elif all(c.get("finished") for c in courses):
            course_learning_percent = 100

    # 展示用总进度：已获得学时为 0 时回退到课程学习进度（避免列表长期显示 0%）
    display_percent = progress_percent
    if display_percent <= 0 and course_learning_percent > 0:
        display_percent = course_learning_percent

    return {
        "year": year_str,
        "required_hours": required,
        "earned_hours": public_num,
        "annual_progress_percent": progress_percent,
        "course_learning_percent": course_learning_percent,
        "progress_percent": display_percent,
        "completed": progress_percent >= 100 or (
            cert_row is not None and int(cert_row.get("auditStatus") or -1) == 1
        ),
        "current_course_id": current_course_id,
        "current_course_title": current_course_title,
        "courses": courses,
        "updated_from": "server",
    }


def build_learning_progress(
    *,
    year: str,
    course_id: str,
    course_title: str,
    hour_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "year": str(year),
        "course_id": course_id,
        "course_title": course_title,
        **hour_snapshot,
    }


def format_status_msg(
    year: str,
    course_title: str = "",
    hour_title: str = "",
    percent_name: str = "",
) -> str:
    parts = [f"{year}年"]
    if course_title:
        parts.append(course_title)
    if hour_title:
        parts.append(f"{hour_title} {percent_name}".strip())
    return " · ".join(parts)
