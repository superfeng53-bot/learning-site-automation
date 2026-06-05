"""
学科映射：学科1/2 各调一次 → 写入 ai_subject_map → 同学科合并。

复制到 <svc>/subject_mapper.py。
流程（通用，站点在 config 填规则，不写死科目名）：
  1. 每条去重 category 单独映射（不合并进同一次 LLM）
  2. 规则链优先（关键词 → 列表匹配 / 固定 ID）
  3. 空 category → EMPTY_CATEGORY_FALLBACK
  4. 其余 → 单条 LLM（须配置；失败则整账号失败，无本地兜底）
  5. merge_requirements_by_mapped_subject：同 mapped_id 合并学分

账号级结果写入 extra[AI_SUBJECT_MAP_KEY]；LLM 进程/库缓存按单条 category 复用。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .config import (
    AI_SUBJECT_MAP_KEY,
    EMPTY_CATEGORY_FALLBACK,
    SUBJECT_MAPPING_RULES,
    SUBJECT_STATIC_ID_MAP,
)
from .requirements_resolver import dedupe_categories_preserve_order, requirement_slot_key


# ── 数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class SubjectMappingRecord:
    """单条需求文本 → 平台主学科。"""
    category: str
    mapped_label: str
    mapped_id: str
    source: str
    forbid_public_supplement: bool = False
    course_title_keywords: list[str] = field(default_factory=list)


@dataclass
class MergedRequirement:
    """同学科合并后的预匹配/学习单元。"""
    categories: list[str]
    credits: float
    mapped_label: str
    mapped_id: str
    source_slots: list[str]
    forbid_public_supplement: bool = False
    course_title_keywords: list[str] = field(default_factory=list)
    process_order: int = 0


class PerCategoryLlmMapper(Protocol):
    """单条 category 映射；不批量合并学科1+学科2。"""

    def map_one_category(
        self,
        category: str,
        *,
        platform_subjects: Sequence[Mapping[str, str]],
        account_name: str = "",
        account_username: str = "",
        rule_preset: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """返回 {"id": "...", "label": "..."}；失败抛 SubjectMappingError。"""
        ...


class SubjectMappingError(Exception):
    pass


# ── 平台列表工具 ─────────────────────────────────────────────────────────────

def normalize_platform_subjects(
    subjects: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for s in subjects:
        sid = str(s.get("id") or s.get("subject_id") or "").strip()
        label = str(s.get("label") or s.get("name") or "").strip()
        if sid or label:
            rows.append({"id": sid, "label": label})
    return sorted(rows, key=lambda x: x["id"])


def _contains_keyword(text: str, keywords: Sequence[str]) -> bool:
    t = text.strip()
    return any(k and k in t for k in keywords)


def _pick_from_list_by_labels(
    platform_subjects: Sequence[Mapping[str, str]],
    preferred_labels: Sequence[str],
    *,
    fallback_first: bool = False,
) -> dict[str, str] | None:
    labels = [str(x).strip() for x in preferred_labels if str(x).strip()]
    for pref in labels:
        for s in platform_subjects:
            lab = str(s.get("label") or "").strip()
            if pref in lab or lab in pref:
                return {"id": str(s.get("id") or ""), "label": lab}
    if fallback_first and platform_subjects:
        s = platform_subjects[0]
        return {"id": str(s.get("id") or ""), "label": str(s.get("label") or "")}
    return None


def _normalize_llm_choice(
    choice: str,
    platform_subjects: Sequence[Mapping[str, str]],
) -> dict[str, str] | None:
    """LLM 输出须在平台列表中原样或模糊命中。"""
    c = str(choice or "").strip()
    if not c:
        return None
    for s in platform_subjects:
        lab = str(s.get("label") or "").strip()
        if c == lab:
            return {"id": str(s.get("id") or ""), "label": lab}
    compact = re.sub(r"\s+|学科", "", c)
    for s in platform_subjects:
        lab = str(s.get("label") or "").strip()
        if re.sub(r"\s+|学科", "", lab) == compact:
            return {"id": str(s.get("id") or ""), "label": lab}
    return None


def _llm_cache_key(
    category: str,
    catalog: Sequence[Mapping[str, str]],
    *,
    provider: str = "",
    model: str = "",
) -> str:
    cat_json = json.dumps(category.strip(), ensure_ascii=False)
    cat_snap = json.dumps(
        [{"id": c["id"], "label": c["label"]} for c in catalog],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = f"{cat_json}|{cat_snap}|{provider}|{model}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── 单条映射 ─────────────────────────────────────────────────────────────────

def _resolve_by_rule(
    category: str,
    rule: Mapping[str, Any],
    platform_subjects: Sequence[Mapping[str, str]],
) -> dict[str, Any] | None:
    strategy = str(rule.get("strategy") or "list_match")
    if strategy == "fixed_id":
        fid = str(rule.get("fixed_id") or "").strip()
        flab = str(rule.get("fixed_label") or "").strip()
        if fid:
            return {
                "id": fid,
                "label": flab or fid,
                "source": str(rule.get("id") or "fixed_id"),
                "forbid_public_supplement": bool(rule.get("forbid_public_supplement")),
                "course_title_keywords": list(rule.get("course_title_keywords") or []),
            }
    if strategy == "static_map":
        sid = SUBJECT_STATIC_ID_MAP.get(category, "").strip()
        if sid:
            for s in platform_subjects:
                if str(s.get("id") or "") == sid:
                    return {
                        "id": sid,
                        "label": str(s.get("label") or ""),
                        "source": str(rule.get("id") or "static_map"),
                        "forbid_public_supplement": bool(rule.get("forbid_public_supplement")),
                        "course_title_keywords": list(rule.get("course_title_keywords") or []),
                    }
    if strategy == "list_match":
        hit = _pick_from_list_by_labels(
            platform_subjects,
            rule.get("list_match_preferred_labels") or [],
            fallback_first=bool(rule.get("fallback_first")),
        )
        if hit and hit.get("id"):
            return {
                **hit,
                "source": str(rule.get("id") or "list_match"),
                "forbid_public_supplement": bool(rule.get("forbid_public_supplement")),
                "course_title_keywords": list(rule.get("course_title_keywords") or []),
            }
    return None


def _resolve_empty_category(
    platform_subjects: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    fb = EMPTY_CATEGORY_FALLBACK
    hit = _pick_from_list_by_labels(
        platform_subjects,
        fb.get("preferred_labels") or [],
        fallback_first=bool(fb.get("fallback_first", True)),
    )
    if not hit or not hit.get("id"):
        raise SubjectMappingError("空人员类别映射失败：平台学科列表为空或无匹配项")
    return {
        **hit,
        "source": "empty_rule",
        "forbid_public_supplement": bool(fb.get("forbid_public_supplement")),
        "course_title_keywords": list(fb.get("course_title_keywords") or []),
    }


def map_one_category(
    category: str,
    platform_subjects: Sequence[Mapping[str, Any]],
    *,
    account_name: str = "",
    account_username: str = "",
    llm_mapper: PerCategoryLlmMapper | None = None,
    store: Any | None = None,
    llm_provider: str = "",
    llm_model: str = "",
    rules: Sequence[Mapping[str, Any]] | None = None,
) -> SubjectMappingRecord:
    """
    单条 category 映射。学科1、学科2 各调一次，禁止合并批量 LLM。
    映射失败（无 subject_id）→ 抛 SubjectMappingError。
    """
    catalog = normalize_platform_subjects(platform_subjects)
    cat = str(category or "").strip()

    if not cat:
        resolved = _resolve_empty_category(catalog)
        return SubjectMappingRecord(
            category="",
            mapped_label=resolved["label"],
            mapped_id=resolved["id"],
            source=resolved["source"],
            forbid_public_supplement=resolved["forbid_public_supplement"],
            course_title_keywords=resolved["course_title_keywords"],
        )

    rules = rules if rules is not None else SUBJECT_MAPPING_RULES
    for rule in rules:
        keywords = rule.get("trigger_keywords") or []
        if keywords and not _contains_keyword(cat, keywords):
            continue
        hit = _resolve_by_rule(cat, rule, catalog)
        if hit and hit.get("id"):
            return SubjectMappingRecord(
                category=cat,
                mapped_label=hit["label"],
                mapped_id=hit["id"],
                source=hit["source"],
                forbid_public_supplement=hit["forbid_public_supplement"],
                course_title_keywords=hit["course_title_keywords"],
            )
        if keywords and bool(rule.get("fail_on_miss", True)):
            raise SubjectMappingError(f"规则 {rule.get('id')} 命中但列表匹配失败：{cat}")

    if llm_mapper is None:
        raise SubjectMappingError(f"无匹配规则且未配置 LLM：{cat}")

    cache_key = _llm_cache_key(cat, catalog, provider=llm_provider, model=llm_model)
    cached: dict[str, str] | None = None
    if store is not None:
        blob = store.get_ai_subject_cache(cache_key)
        if blob and cat in blob:
            cached = blob[cat]
        elif blob and blob.get("id"):
            cached = {"id": blob["id"], "label": blob.get("label", "")}

    if cached is None:
        preset = _pick_from_list_by_labels(catalog, [cat], fallback_first=False)
        raw = llm_mapper.map_one_category(
            cat,
            platform_subjects=catalog,
            account_name=account_name,
            account_username=account_username,
            rule_preset=preset,
        )
        normalized = _normalize_llm_choice(raw.get("label", ""), catalog) or raw
        if not normalized.get("id"):
            raise SubjectMappingError(f"LLM 映射无效：{cat}")
        cached = {"id": normalized["id"], "label": normalized.get("label", "")}
        if store is not None:
            store.upsert_ai_subject_cache(
                cache_key,
                requirement_texts_json=json.dumps([cat], ensure_ascii=False),
                catalog_snapshot_json=json.dumps(catalog, ensure_ascii=False),
                mapping_json=json.dumps({cat: cached}, ensure_ascii=False),
            )

    return SubjectMappingRecord(
        category=cat,
        mapped_label=cached["label"],
        mapped_id=cached["id"],
        source="ai",
        forbid_public_supplement=False,
        course_title_keywords=[],
    )


def ensure_subject_mappings(
    requirements: Sequence[Mapping[str, Any]],
    platform_subjects: Sequence[Mapping[str, Any]],
    *,
    account_name: str = "",
    account_username: str = "",
    llm_mapper: PerCategoryLlmMapper | None = None,
    store: Any | None = None,
    llm_provider: str = "",
    llm_model: str = "",
) -> list[SubjectMappingRecord]:
    """
    对去重后的每条 category 单独映射，返回 ai_subject_map 列表。
    任一条失败抛 SubjectMappingError（整账号失败）。
    """
    categories = dedupe_categories_preserve_order(requirements)
    if not categories:
        return []

    records: list[SubjectMappingRecord] = []
    for cat in categories:
        records.append(
            map_one_category(
                cat,
                platform_subjects,
                account_name=account_name,
                account_username=account_username,
                llm_mapper=llm_mapper,
                store=store,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
        )
    return records


def merge_requirements_by_mapped_subject(
    requirements: Sequence[Mapping[str, Any]],
    mappings: Sequence[SubjectMappingRecord],
) -> list[MergedRequirement]:
    """
    同学科（同 mapped_id）合并学分；保持首次出现顺序。
    例：医师:10 + 临床:5 均映射临床医学 → 临床医学:15。
    """
    mapping_by_cat = {m.category: m for m in mappings if m.category}
    empty_map = next((m for m in mappings if not m.category), None)

    merged: list[MergedRequirement] = []
    index_by_id: dict[str, int] = {}
    order = 0

    for req in requirements:
        cat = str(req.get("category") or "").strip()
        slot = str(req.get("key") or "")
        credits = float(req.get("credits") or 0)
        if not cat:
            if empty_map and empty_map.mapped_id:
                m = empty_map
            else:
                continue
        else:
            m = mapping_by_cat.get(cat)
            if not m or not m.mapped_id:
                continue

        mid = m.mapped_id
        if mid in index_by_id:
            idx = index_by_id[mid]
            merged[idx].categories.append(cat or "(空)")
            merged[idx].credits += credits
            if slot:
                merged[idx].source_slots.append(slot)
            merged[idx].forbid_public_supplement |= m.forbid_public_supplement
            if m.course_title_keywords:
                merged[idx].course_title_keywords = list(m.course_title_keywords)
        else:
            index_by_id[mid] = len(merged)
            merged.append(MergedRequirement(
                categories=[cat or "(空)"],
                credits=credits,
                mapped_label=m.mapped_label,
                mapped_id=mid,
                source_slots=[slot] if slot else [],
                forbid_public_supplement=m.forbid_public_supplement,
                course_title_keywords=list(m.course_title_keywords),
                process_order=order,
            ))
            order += 1

    return merged


def mappings_to_extra(ai_subject_map: Sequence[SubjectMappingRecord]) -> list[dict[str, Any]]:
    """序列化写入 extra[AI_SUBJECT_MAP_KEY]。"""
    return [
        {
            "category": m.category,
            "mapped_label": m.mapped_label,
            "mapped_id": m.mapped_id,
            "ai_subject": m.mapped_label,
            "ai_subject_id": m.mapped_id,
            "source": m.source,
            "forbid_public_supplement": m.forbid_public_supplement,
            "course_title_keywords": m.course_title_keywords,
        }
        for m in ai_subject_map
    ]


def is_special_subject_context(
    text: str,
    *,
    keywords: Sequence[str] | None = None,
    rules: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    """选课阶段判断是否禁止公共科目补齐（看 mapped_label 或原始 category）。"""
    rules = rules if rules is not None else SUBJECT_MAPPING_RULES
    t = str(text or "").strip()
    for rule in rules:
        if bool(rule.get("forbid_public_supplement")) and _contains_keyword(t, rule.get("trigger_keywords") or []):
            return True
    if keywords:
        return _contains_keyword(t, keywords)
    return False


# ── 课级 matched_requirement_key（学习列表展示用）────────────────────────────

def rule_match_unit_to_slot(
    unit: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    *,
    synonym_map: Mapping[str, Sequence[str]] | None = None,
    static_id_map: Mapping[str, str] | None = None,
) -> str | None:
    """将课程归到学科1/学科2 槽位（预匹配后写入 matched_requirement_key）。"""
    synonym_map = synonym_map or {}
    static_id_map = static_id_map or SUBJECT_STATIC_ID_MAP
    label = str(unit.get("subject_label") or unit.get("actual_subject") or "").strip()
    subject_id = str(unit.get("subject_id") or "").strip()

    for i, req in enumerate(requirements, start=1):
        cat = str(req.get("category") or "").strip()
        if not cat:
            continue
        slot = requirement_slot_key(i)
        syns = synonym_map.get(cat, ())
        if cat == label or cat in label or label in cat:
            return slot
        for syn in syns:
            if syn and (syn in label or label in syn):
                return slot
        mapped_id = static_id_map.get(cat, "").strip()
        if mapped_id and subject_id == mapped_id:
            return slot
    return None
