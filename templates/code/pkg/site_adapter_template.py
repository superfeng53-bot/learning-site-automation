"""
站点适配器模板 — 学科1/2 完整链路已接 account_pipeline。

复制到 <pkg>/site_adapter.py，取消注释 import，实现 CoursePoolProvider。

链路（通用）：
  学科1/2 → ensure_subject_mappings → merge → prefill → course_results
  学习：pick_next_learn_course（不重跑映射）
"""
from __future__ import annotations

import json
from typing import Any

# 复制后取消注释并替换 <SVC> / <PKG>：
# from <SVC>.adapter import (
#     AccountView, ApplyResult, Capabilities, CourseUnit,
#     RunResult, SessionResult, SiteAdapter, YearResult,
# )
# from <SVC>.account_pipeline import (
#     AssignmentOutput, CoursePoolProvider, build_assignment_plan,
#     pick_next_learn_course, write_assignment_to_extra,
# )
# from <SVC>.config import (
#     AI_SUBJECT_MAP_KEY, COURSE_RESULTS_KEY, PUBLIC_SUBJECT_IDS,
#     SUBJECT_MAPPING_RULES, USE_LLM_SUBJECT_MAPPING,
# )
# from <SVC>.requirements_resolver import normalize_requirements
# from <SVC>.subject_mapper import MergedRequirement, PerCategoryLlmMapper
# from <PKG>.course import CourseService
# from <PKG>.login import LoginService
# from <PKG>.member import MemberService
# from <PKG>.session_manager import get_session_manager

AccountView = ApplyResult = Capabilities = CourseUnit = Any  # type: ignore
RunResult = SessionResult = SiteAdapter = YearResult = Any  # type: ignore
AssignmentOutput = CoursePoolProvider = build_assignment_plan = Any  # type: ignore
pick_next_learn_course = write_assignment_to_extra = normalize_requirements = Any  # type: ignore
MergedRequirement = PerCategoryLlmMapper = Any  # type: ignore
AI_SUBJECT_MAP_KEY = COURSE_RESULTS_KEY = ""
PUBLIC_SUBJECT_IDS: list = []
SUBJECT_MAPPING_RULES: list = []
USE_LLM_SUBJECT_MAPPING = False
CourseService = LoginService = MemberService = Any  # type: ignore


def get_session_manager():  # type: ignore
    raise NotImplementedError("复制后改为 from <PKG>.session_manager import get_session_manager")


class _SiteCoursePool(CoursePoolProvider):
    """
    站点实现 gather_pool：按 mapped_id 拉课，可选并入 PUBLIC_SUBJECT_IDS。
    复制后把 TODO 换成真实 API（get_course_list / 我的课程 / 跨学科已学完 等）。
    """

    def __init__(self, course_svc: Any, *, failed_ids: list[str] | None = None) -> None:
        self._svc = course_svc
        self._failed = set(failed_ids or [])

    def gather_pool(
        self,
        merged_req: MergedRequirement,
        *,
        include_public: bool,
    ) -> list[dict[str, Any]]:
        sub_id = merged_req.mapped_id
        # TODO: course_svc.get_course_list(sub_id=sub_id)
        courses: list[dict[str, Any]] = []

        # TODO: 标记/补入「我的课程」、跨学科已学完、按 projId 去重、排除 failed_ids
        # courses = self._svc.fetch_my_proj_courses(courses)
        # courses = self._svc.merge_cross_subject_finished(courses)

        if include_public and not merged_req.forbid_public_supplement:
            for pub_id in PUBLIC_SUBJECT_IDS:
                # TODO: courses += self._svc.get_course_list(sub_id=pub_id, mark_actual_subject=True)
                pass

        # 特殊上下文：标题关键词过滤在 course_matcher 内完成（merged_req.course_title_keywords）
        return [c for c in courses if str(c.get("project_id") or "") not in self._failed]


class PlatformAdapter(SiteAdapter):
    capabilities = Capabilities(
        profile="A",
        has_exam=True,
        has_credit=True,
        has_recharge=False,
        has_subjects=True,
    )

    def __init__(self, store=None) -> None:
        self._store = store
        self._sm = get_session_manager()

    def ensure_session(self, account: AccountView) -> SessionResult:
        client = self._sm.get_client(str(account.id))
        if account.cookies:
            client.load_cookies(account.cookies)
        result = LoginService(client).login(account.username, account.password)
        if not result.success:
            return SessionResult(reused=False, cookies={}, error=result.message)
        return SessionResult(reused=False, cookies=result.cookies, user_info=result.user_info)

    def profile_info(self, account: AccountView) -> dict[str, Any]:
        client = self._sm.get_client(str(account.id))
        client.load_cookies(account.cookies)
        return MemberService(client).get_profile() or {}

    def build_plan(self, account: AccountView, *, preserve_mappings: bool = False) -> list[CourseUnit]:
        client = self._sm.get_client(str(account.id))
        client.load_cookies(account.cookies)
        course_svc = CourseService(client)

        platform_subjects = course_svc.list_subjects()
        pool = _SiteCoursePool(
            course_svc,
            failed_ids=list((account.extra or {}).get("failed_course_ids") or []),
        )

        output: AssignmentOutput = build_assignment_plan(
            account.requirements,
            platform_subjects,
            pool,
            account_name=account.display_name,
            account_username=account.username,
            account_id=account.id,
            llm_mapper=_optional_llm_mapper(),
            store=self._store,
            existing_extra=account.extra,
            preserve_mappings=preserve_mappings,
        )

        extra = write_assignment_to_extra(output, dict(account.extra or {}))
        account.extra.update(extra)

        return [_row_to_course_unit(r) for r in output.course_results]

    def pick_next_course(self, account: AccountView) -> CourseUnit | None:
        """学习阶段：全局 queue_rank 最小，不重跑映射/预匹配。"""
        results = (account.extra or {}).get(COURSE_RESULTS_KEY) or []
        row = pick_next_learn_course(results)
        return _row_to_course_unit(row) if row else None

    def run_course(self, account: AccountView, unit: CourseUnit) -> RunResult:
        raise NotImplementedError("对接 CourseRunner.run(project_id)")

    def apply_credit(self, account: AccountView, unit: CourseUnit) -> ApplyResult:
        raise NotImplementedError("对接 CreditService.apply")

    def run_year(self, account: AccountView, year: str) -> YearResult:
        raise NotImplementedError("B 型对接 YearTaskRunner")


def build_adapter(store=None) -> PlatformAdapter:
    return PlatformAdapter(store=store)


def _row_to_course_unit(row: dict[str, Any] | None) -> CourseUnit | None:
    if not row:
        return None
    return CourseUnit(
        project_id=str(row.get("project_id") or ""),
        title=str(row.get("title") or ""),
        subject_label=str(row.get("subject_label") or row.get("actual_subject") or ""),
        credits=float(row.get("credits") or 0) or None,
        state=str(row.get("state") or ""),
        queue_rank=int(row.get("queue_rank") or 0),
        progress_tier=int(row.get("progress_tier") or 3),
        subject_tier=int(row.get("subject_tier") or 2),
        matched_requirement_key=row.get("matched_requirement_key"),
        extra={k: v for k, v in row.items() if k not in {
            "project_id", "title", "subject_label", "credits", "state",
            "queue_rank", "progress_tier", "subject_tier", "matched_requirement_key",
        }},
    )


def _optional_llm_mapper() -> PerCategoryLlmMapper | None:
    if not USE_LLM_SUBJECT_MAPPING:
        return None
    # from <SVC>.llm_subject import build_llm_mapper
    # return build_llm_mapper()
    return None
