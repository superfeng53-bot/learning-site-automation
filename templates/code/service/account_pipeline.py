"""
A 型完整分配流水线（学科1/2 → 映射 → 预匹配 → course_results → 学习）。

复制到 <svc>/account_pipeline.py。

链路：
  resolve_requirements
    → ensure_subject_mappings（逐条 category，写入 ai_subject_map）
    → merge_requirements_by_mapped_subject
    → prefill_course_matches（每条合并需求 preview_match，两阶段凑课）
    → course_results 扁平列表 + 按 subject_group 分组
    → assign_global_queue_ranks

学习阶段：
  pick_next_learn_course（全局 queue_rank 最小，不重跑映射/预匹配）
  pending_subject_groups / flatten 补跑未处理分组

站点只需实现 CoursePoolProvider.gather_pool。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from .config import (
    AI_SUBJECT_MAP_KEY,
    COURSE_RESULTS_KEY,
    COURSE_RESULTS_GROUPS_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
)
from .course_matcher import match_two_phase
from .course_planner import assign_queue_ranks, pick_next_unit
from .requirements_resolver import normalize_requirements, primary_category
from .states import UnitState
from .subject_mapper import (
    MergedRequirement,
    PerCategoryLlmMapper,
    SubjectMappingError,
    SubjectMappingRecord,
    ensure_subject_mappings,
    mappings_to_extra,
    merge_requirements_by_mapped_subject,
    rule_match_unit_to_slot,
)


# ── 站点对接：候选池 ─────────────────────────────────────────────────────────

class CoursePoolProvider(Protocol):
    """
    站点实现本协议，对接拉课 API。
    merged_req: 合并后的单条需求（含 mapped_id / forbid_public_supplement 等）
    include_public: 阶段2 是否并入公共科目课
    """

    def gather_pool(
        self,
        merged_req: MergedRequirement,
        *,
        include_public: bool,
    ) -> list[dict[str, Any]]:
        ...


@dataclass
class AssignmentContext:
    """分配上下文（worker / site_adapter 构造）。"""
    requirements: list[dict[str, Any]]
    platform_subjects: list[dict[str, Any]]
    pool_provider: CoursePoolProvider
    account_name: str = ""
    account_username: str = ""
    account_id: int = 0
    llm_mapper: PerCategoryLlmMapper | None = None
    store: Any | None = None
    llm_provider: str = ""
    llm_model: str = ""
    failed_course_ids: list[str] = field(default_factory=list)
    existing_results: list[dict[str, Any]] | None = None
    preserve_mappings: bool = False
    existing_ai_subject_map: list[dict[str, Any]] | None = None
    synonym_map: dict[str, list[str]] | None = None


@dataclass
class AssignmentOutput:
    ai_subject_map: list[dict[str, Any]]
    course_results: list[dict[str, Any]]
    course_results_groups: dict[str, list[dict[str, Any]]]
    primary_category: str
    merged_requirements: list[MergedRequirement]


# ── 预匹配写入 ───────────────────────────────────────────────────────────────

def _course_row_from_match(
    course: dict[str, Any],
    merged_req: MergedRequirement,
    *,
    subject_group: str,
    requirements: Sequence[Mapping[str, Any]],
    synonym_map: dict[str, list[str]] | None,
) -> dict[str, Any]:
    row = dict(course)
    row.setdefault("project_id", str(course.get("project_id") or course.get("proj_id") or ""))
    row["subject_group"] = subject_group
    row["actual_subject"] = str(
        course.get("actual_subject") or course.get("_subject_name") or course.get("subject_label") or ""
    )
    row["mapped_subject_id"] = merged_req.mapped_id
    row["mapped_subject_label"] = merged_req.mapped_label
    row["source_categories"] = list(merged_req.categories)
    row["selected"] = True
    row["state"] = row.get("state") or UnitState.PREFILL
    row["matched_requirement_key"] = rule_match_unit_to_slot(
        row, requirements, synonym_map=synonym_map,
    ) or (merged_req.source_slots[0] if merged_req.source_slots else "")
    return row


def prefill_course_matches(
    merged_reqs: Sequence[MergedRequirement],
    pool_provider: CoursePoolProvider,
    requirements: Sequence[Mapping[str, Any]],
    *,
    failed_course_ids: Sequence[str] | None = None,
    synonym_map: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """
    每条合并需求单独 preview_match；按 actual_subject / subject_group 写入分组。
    公共科目补齐的课归入 actual_subject 对应分组（可能与主学科不同）。
    """
    flat: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()

    for mreq in sorted(merged_reqs, key=lambda x: x.process_order):
        max_courses = int(mreq.credits) if mreq.credits > 0 else None

        def gather(include_public: bool) -> list[dict[str, Any]]:
            return pool_provider.gather_pool(mreq, include_public=include_public)

        result = match_two_phase(
            gather,
            mreq.credits,
            forbid_public_supplement=mreq.forbid_public_supplement,
            title_keywords=mreq.course_title_keywords or None,
            failed_course_ids=failed_course_ids,
            max_courses=max_courses,
        )
        if result is None:
            groups.setdefault(mreq.mapped_label, [])
            continue

        for course in result.courses:
            pid = str(course.get("project_id") or "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            actual = str(
                course.get("actual_subject") or course.get("_subject_name")
                or course.get("subject_label") or mreq.mapped_label
            )
            row = _course_row_from_match(
                course, mreq,
                subject_group=actual,
                requirements=requirements,
                synonym_map=synonym_map,
            )
            flat.append(row)
            groups.setdefault(actual, []).append(row)

    return flat, groups


def _merge_existing_progress(
    new_results: list[dict[str, Any]],
    existing: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """保留平台已学/已申请进度，不覆盖 state。"""
    if not existing:
        return new_results
    by_id = {str(u.get("project_id") or ""): dict(u) for u in existing if u.get("project_id")}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    keep_states = {
        UnitState.RUNNING, UnitState.LEARNED, UnitState.APPLIED,
        "pending", UnitState.PREFILL,
    }

    for row in new_results:
        pid = str(row.get("project_id") or "")
        seen.add(pid)
        prev = by_id.get(pid)
        if prev and (prev.get("state") or "") in keep_states:
            merged = {**row, **{k: v for k, v in prev.items() if k in (
                "state", "daily_learn_date", "queue_rank", "selected",
            ) and v not in (None, "")}}
            out.append(merged)
        else:
            out.append(row)

    for pid, prev in by_id.items():
        if pid not in seen and (prev.get("selected") or prev.get("state") in keep_states):
            out.append(dict(prev))
    return out


def assign_global_queue_ranks(
    flat_results: list[dict[str, Any]],
    merged_reqs: Sequence[MergedRequirement],
) -> list[dict[str, Any]]:
    """
    全局 queue_rank：先按合并需求 process_order，同组内按 priority_bucket / project_id。
    学习时全局最小 queue_rank 优先（每日限额在 course_planner.check_learning_gates）。
    """
    group_order = {m.mapped_label: m.process_order for m in merged_reqs}
    default_order = len(merged_reqs)

    def sort_key(u: Mapping[str, Any]) -> tuple:
        grp = str(u.get("subject_group") or u.get("mapped_subject_label") or "")
        return (
            group_order.get(grp, default_order),
            u.get("priority_bucket", 9),
            str(u.get("project_id") or ""),
        )

    ordered = sorted(
        [u for u in flat_results if u.get("selected", True)],
        key=sort_key,
    )
    for i, u in enumerate(ordered):
        u["queue_rank"] = i
    return ordered


# ── 主入口 ───────────────────────────────────────────────────────────────────

def run_assignment_pipeline(ctx: AssignmentContext) -> AssignmentOutput:
    """
    完整分配：映射 → 合并 → 预匹配 → 写入 course_results。
    重新选课（preserve_mappings=True）时保留 ai_subject_map，仅清空后重跑预匹配。
    """
    reqs = ctx.requirements
    ai_maps: list[SubjectMappingRecord]

    if ctx.preserve_mappings and ctx.existing_ai_subject_map:
        ai_maps = [
            SubjectMappingRecord(
                category=str(x.get("category") or ""),
                mapped_label=str(x.get("mapped_label") or x.get("ai_subject") or ""),
                mapped_id=str(x.get("mapped_id") or x.get("ai_subject_id") or ""),
                source=str(x.get("source") or "cached"),
                forbid_public_supplement=bool(x.get("forbid_public_supplement")),
                course_title_keywords=list(x.get("course_title_keywords") or []),
            )
            for x in ctx.existing_ai_subject_map
        ]
    else:
        ai_maps = ensure_subject_mappings(
            reqs,
            ctx.platform_subjects,
            account_name=ctx.account_name,
            account_username=ctx.account_username,
            llm_mapper=ctx.llm_mapper,
            store=ctx.store,
            llm_provider=ctx.llm_provider,
            llm_model=ctx.llm_model,
        )

    merged = merge_requirements_by_mapped_subject(reqs, ai_maps)
    flat, groups = prefill_course_matches(
        merged,
        ctx.pool_provider,
        reqs,
        failed_course_ids=ctx.failed_course_ids,
        synonym_map=ctx.synonym_map,
    )
    flat = _merge_existing_progress(flat, ctx.existing_results)
    flat = assign_global_queue_ranks(flat, merged)

    return AssignmentOutput(
        ai_subject_map=mappings_to_extra(ai_maps),
        course_results=flat,
        course_results_groups=groups,
        primary_category=primary_category(reqs),
        merged_requirements=merged,
    )


def build_assignment_plan(
    raw_requirements: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str,
    platform_subjects: Sequence[Mapping[str, Any]],
    pool_provider: CoursePoolProvider,
    *,
    account_name: str = "",
    account_username: str = "",
    account_id: int = 0,
    llm_mapper: PerCategoryLlmMapper | None = None,
    store: Any | None = None,
    existing_extra: Mapping[str, Any] | None = None,
    preserve_mappings: bool = False,
    failed_course_ids: Sequence[str] | None = None,
    synonym_map: dict[str, list[str]] | None = None,
) -> AssignmentOutput:
    """site_adapter / worker 一站式入口。"""
    reqs = normalize_requirements(raw_requirements)
    extra = dict(existing_extra or {})
    ctx = AssignmentContext(
        requirements=reqs,
        platform_subjects=list(platform_subjects),
        pool_provider=pool_provider,
        account_name=account_name,
        account_username=account_username,
        account_id=account_id,
        llm_mapper=llm_mapper,
        store=store,
        llm_provider=LLM_PROVIDER,
        llm_model=LLM_MODEL,
        failed_course_ids=list(failed_course_ids or extra.get("failed_course_ids") or []),
        existing_results=extra.get(COURSE_RESULTS_KEY),
        preserve_mappings=preserve_mappings,
        existing_ai_subject_map=extra.get(AI_SUBJECT_MAP_KEY),
        synonym_map=synonym_map,
    )
    return run_assignment_pipeline(ctx)


def write_assignment_to_extra(
    output: AssignmentOutput,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """合并写入 extra 字段。"""
    extra = dict(extra)
    extra[AI_SUBJECT_MAP_KEY] = output.ai_subject_map
    extra[COURSE_RESULTS_KEY] = output.course_results
    extra[COURSE_RESULTS_GROUPS_KEY] = output.course_results_groups
    extra["primary_category"] = output.primary_category
    return extra


# ── 学习阶段（不重跑映射/预匹配）────────────────────────────────────────────

def pick_next_learn_course(
    course_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """
    全局 queue_rank 最小者优先；只学 selected=True 且 state 为 pending/空/running 的课。
    """
    candidates = [
        dict(u) for u in course_results
        if u.get("selected", True)
        and (u.get("state") or "") in (UnitState.PREFILL, UnitState.PENDING, UnitState.RUNNING, "")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda u: (u.get("queue_rank", 10**9), str(u.get("project_id") or "")))


def pending_subject_groups(
    course_results: Sequence[Mapping[str, Any]],
    merged_reqs: Sequence[MergedRequirement],
) -> list[str]:
    """
    主循环按 merged_reqs 顺序走后，补跑尚未完成预匹配/学习的分组名。
    """
    done_groups: set[str] = set()
    for u in course_results:
        if u.get("selected") and (u.get("state") or "") in (
            UnitState.RUNNING, UnitState.LEARNED, UnitState.APPLIED,
        ):
            done_groups.add(str(u.get("subject_group") or u.get("mapped_subject_label") or ""))

    pending: list[str] = []
    for m in sorted(merged_reqs, key=lambda x: x.process_order):
        if m.mapped_label not in done_groups and m.mapped_label not in pending:
            has_any = any(
                str(u.get("mapped_subject_label") or u.get("subject_group") or "") == m.mapped_label
                for u in course_results
            )
            if has_any:
                pending.append(m.mapped_label)
    return pending


def flatten_course_results(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _name, rows in groups.items():
        for u in rows:
            pid = str(u.get("project_id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                flat.append(dict(u))
    return assign_queue_ranks(flat)


# 向后兼容旧 build_assignment_plan(catalog=...) 签名 — 保留薄包装
def build_assignment_plan_legacy(*args, **kwargs):
    raise TypeError(
        "请改用 build_assignment_plan(raw_requirements, platform_subjects, pool_provider, ...)；"
        "拉课逻辑通过 CoursePoolProvider 注入。"
    )
