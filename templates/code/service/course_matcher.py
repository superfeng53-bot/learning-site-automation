"""
候选池凑课 + 优先级分桶 DP（通用，站点无关）。

复制到 <svc>/course_matcher.py。
平台进度字段名、状态值在 config.PLATFORM_PROGRESS 中配置；
站点在 account_pipeline.CoursePoolProvider 中实现拉课逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .config import PLATFORM_PROGRESS


@dataclass(frozen=True)
class MatchResult:
    courses: list[dict[str, Any]]
    total_credits: float
    remaining_after_credited: float


def _credit(course: Mapping[str, Any]) -> float:
    return float(course.get("credits") or course.get("credit") or 0)


def _platform_state(course: Mapping[str, Any]) -> Any:
    return course.get("platform_proj_state", course.get("proj_state", course.get("state_code")))


def is_platform_credited(course: Mapping[str, Any]) -> bool:
    ps = _platform_state(course)
    credited = PLATFORM_PROGRESS.get("credited_values", ())
    return ps in credited or str(ps) in {str(x) for x in credited}


def is_my_course(course: Mapping[str, Any]) -> bool:
    if course.get("is_my_course") is not None:
        return bool(course.get("is_my_course"))
    return bool(course.get("from_my_courses") or course.get("in_my_list"))


def priority_bucket(course: Mapping[str, Any]) -> int:
    """
    优先级分桶（数字越小越优先）：
      0 = 平台已获学分
      1~4 = 我的课：已学完 > 学中 > 未学
      5~8 = 其它课：同上
    """
    if is_platform_credited(course):
        return 0

    finished = PLATFORM_PROGRESS.get("finished_values", ())
    in_progress = PLATFORM_PROGRESS.get("in_progress_values", ())
    ps = _platform_state(course)
    ps_str = str(ps)

    def _in(vals) -> bool:
        return ps in vals or ps_str in {str(v) for v in vals}

    my = is_my_course(course)
    if my:
        if _in(finished):
            return 1
        if _in(in_progress):
            return 2
        return 4
    if _in(finished):
        return 5
    if _in(in_progress):
        return 6
    return 8


def _bucket_cost(bucket: int) -> int:
    return max(0, bucket - 1)


def pick_courses_with_priority(
    courses: Sequence[Mapping[str, Any]],
    required_credits: float,
    *,
    max_courses: int | None = None,
    credit_tolerance: float = 0.01,
) -> list[dict[str, Any]] | None:
    """
    两阶段组合：
      1. 强制纳入 bucket=0（已获学分），扣减 remaining
      2. 在其余候选中 DP 精确凑满 remaining（学分和误差 < tolerance，门数 ≤ left_slots）

    max_courses 默认 int(required_credits)（目标 N 分最多 N 门）。
    无解返回 None。
    """
    if required_credits <= 0:
        return []

    max_courses = max_courses if max_courses is not None else int(required_credits)
    if max_courses <= 0:
        return None

    all_courses = [dict(c) for c in courses]
    credited = [c for c in all_courses if priority_bucket(c) == 0]
    others = [c for c in all_courses if priority_bucket(c) != 0 and _credit(c) > 0]

    credited_sum = sum(_credit(c) for c in credited)
    remaining = required_credits - credited_sum
    left_slots = max_courses - len(credited)

    if remaining <= credit_tolerance:
        return credited[:max_courses]
    if left_slots <= 0:
        return None

    scale = 100
    target = int(round(remaining * scale))
    if target <= 0:
        return credited

    # memo[sum] = (cost_tuple, course_list); cost_tuple = (priority_cost, course_count)
    memo: dict[int, tuple[tuple[int, int], list[dict[str, Any]]]] = {
        0: ((0, 0), []),
    }

    for course in others:
        w = int(round(_credit(course) * scale))
        if w <= 0 or w > target:
            continue
        bucket = priority_bucket(course)
        step_cost = _bucket_cost(bucket)
        updates: dict[int, tuple[tuple[int, int], list[dict[str, Any]]]] = {}
        for s, (cost, combo) in memo.items():
            ns = s + w
            if ns > target:
                continue
            new_cost = (cost[0] + step_cost, cost[1] + 1)
            prev = memo.get(ns)
            if prev is None or new_cost < prev[0]:
                updates[ns] = (new_cost, combo + [course])
        memo.update(updates)

    if target not in memo:
        return None

    dp_combo = memo[target][1]
    if len(credited) + len(dp_combo) > max_courses:
        return None

    for c in credited + dp_combo:
        c.setdefault("priority_bucket", priority_bucket(c))
    return credited + dp_combo


def filter_by_title_keywords(
    courses: Sequence[Mapping[str, Any]],
    keywords: Sequence[str],
) -> list[dict[str, Any]]:
    """特殊学科上下文：标题须含任一关键词（站点在 MappingRule 配置）。"""
    if not keywords:
        return [dict(c) for c in courses]
    kws = [k.strip() for k in keywords if k and str(k).strip()]
    if not kws:
        return [dict(c) for c in courses]
    out: list[dict[str, Any]] = []
    for c in courses:
        title = str(c.get("title") or c.get("name") or "")
        if any(k in title for k in kws):
            out.append(dict(c))
    return out


def dedupe_by_project_id(
    courses: Sequence[Mapping[str, Any]],
    *,
    key: str = "project_id",
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in courses:
        pid = str(c.get(key) or c.get("proj_id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(dict(c))
    return out


def exclude_failed_ids(
    courses: Sequence[Mapping[str, Any]],
    failed_ids: Sequence[str] | set[str],
) -> list[dict[str, Any]]:
    blocked = {str(x) for x in failed_ids}
    return [dict(c) for c in courses if str(c.get("project_id") or "") not in blocked]


def preview_match_courses(
    pool: Sequence[Mapping[str, Any]],
    required_credits: float,
    *,
    max_courses: int | None = None,
    title_keywords: Sequence[str] | None = None,
    failed_course_ids: Sequence[str] | None = None,
) -> MatchResult | None:
    """单条合并需求上的预匹配（不含公共科目补齐，由上层两阶段调用）。"""
    courses = dedupe_by_project_id(pool)
    if failed_course_ids:
        courses = exclude_failed_ids(courses, failed_course_ids)
    if title_keywords:
        courses = filter_by_title_keywords(courses, title_keywords)

    combo = pick_courses_with_priority(
        courses,
        required_credits,
        max_courses=max_courses,
    )
    if combo is None:
        return None
    total = sum(_credit(c) for c in combo)
    credited_sum = sum(_credit(c) for c in combo if priority_bucket(c) == 0)
    return MatchResult(
        courses=combo,
        total_credits=total,
        remaining_after_credited=max(0.0, required_credits - credited_sum),
    )


def match_two_phase(
    gather_pool: Callable[[bool], Sequence[Mapping[str, Any]]],
    required_credits: float,
    *,
    forbid_public_supplement: bool = False,
    title_keywords: Sequence[str] | None = None,
    failed_course_ids: Sequence[str] | None = None,
    max_courses: int | None = None,
) -> MatchResult | None:
    """
    两阶段凑课：
      阶段1: include_public=False（仅当前映射学科）
      阶段2: include_public=True（非 forbid 时允许公共科目补齐）
    """
    r1 = preview_match_courses(
        gather_pool(False),
        required_credits,
        max_courses=max_courses,
        title_keywords=title_keywords,
        failed_course_ids=failed_course_ids,
    )
    if r1 is not None:
        return r1
    if forbid_public_supplement:
        return None
    return preview_match_courses(
        gather_pool(True),
        required_credits,
        max_courses=max_courses,
        title_keywords=title_keywords,
        failed_course_ids=failed_course_ids,
    )
