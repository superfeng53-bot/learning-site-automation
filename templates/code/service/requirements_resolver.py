"""
学科需求解析（学科1/学科2 → 标准 requirements 列表）。

复制到 <svc>/requirements_resolver.py。
支持多种输入形态，统一为最多 MAX_SLOTS 条 {category, credits, key?}。
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from .config import MAX_REQUIREMENT_SLOTS

_SLOT_RE = re.compile(r"^category(\d+)$", re.I)
_CRED_RE = re.compile(r"^credits(\d+)$", re.I)


def requirement_slot_key(index: int) -> str:
    return f"学科{index}"


def _parse_requirements_text(text: str) -> list[dict[str, Any]]:
    """解析 "护士:10;中医:5" 形态。"""
    out: list[dict[str, Any]] = []
    for part in str(text or "").split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        cat, cr = part.split(":", 1)
        cat, cr = cat.strip(), cr.strip()
        if not cat:
            continue
        try:
            credits = float(cr)
        except ValueError:
            continue
        out.append({"category": cat, "credits": credits})
    return out


def normalize_requirements(
    raw: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None,
    *,
    max_slots: int = MAX_REQUIREMENT_SLOTS,
) -> list[dict[str, Any]]:
    """
    统一解析需求，优先级：
      1. requirements / requirements_json 列表
      2. requirements_text 字符串
      3. category1/credits1、category2/credits2（或学科1/学分1 Excel 已转成的键）
      4. 单条 category + required_credits / credits
    最多保留 max_slots 条；附加 key=学科1/学科2。
    """
    reqs: list[dict[str, Any]] = []

    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("["):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"requirements_text": raw}
        else:
            raw = {"requirements_text": raw}

    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for i, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping):
                continue
            cat = str(item.get("category") or "").strip()
            if not cat:
                continue
            reqs.append({
                "key": str(item.get("key") or requirement_slot_key(i)),
                "category": cat,
                "credits": float(item.get("credits") or item.get("credit") or 0),
            })
        return reqs[:max_slots]

    if not isinstance(raw, Mapping):
        return []

    data = dict(raw)

    if data.get("requirements_json"):
        try:
            parsed = json.loads(data["requirements_json"])
            if isinstance(parsed, list):
                return normalize_requirements(parsed, max_slots=max_slots)
        except (TypeError, json.JSONDecodeError):
            pass

    if data.get("requirements"):
        return normalize_requirements(data["requirements"], max_slots=max_slots)

    if data.get("requirements_text"):
        reqs = _parse_requirements_text(str(data["requirements_text"]))

    if not reqs:
        by_slot: dict[int, dict[str, Any]] = {}
        for k, v in data.items():
            m = _SLOT_RE.match(str(k))
            if m:
                idx = int(m.group(1))
                by_slot.setdefault(idx, {})["category"] = str(v or "").strip()
            m2 = _CRE_RE.match(str(k))
            if m2:
                idx = int(m2.group(1))
                try:
                    by_slot.setdefault(idx, {})["credits"] = float(v)
                except (TypeError, ValueError):
                    pass
        for idx in sorted(by_slot):
            row = by_slot[idx]
            cat = str(row.get("category") or "").strip()
            if cat:
                reqs.append({"category": cat, "credits": float(row.get("credits") or 0)})

    if not reqs:
        cat = str(data.get("category") or "").strip()
        if cat:
            cr = data.get("required_credits", data.get("credits", 0))
            try:
                credits = float(cr or 0)
            except (TypeError, ValueError):
                credits = 0.0
            reqs.append({"category": cat, "credits": credits})

    out: list[dict[str, Any]] = []
    for i, r in enumerate(reqs[:max_slots], start=1):
        out.append({
            "key": requirement_slot_key(i),
            "category": r["category"],
            "credits": float(r.get("credits") or 0),
        })
    return out


def primary_category(requirements: Sequence[Mapping[str, Any]]) -> str:
    """账号默认类别 = 学科1 文本（兼容旧逻辑）。"""
    if not requirements:
        return ""
    return str(requirements[0].get("category") or "").strip()


def dedupe_categories_preserve_order(requirements: Sequence[Mapping[str, Any]]) -> list[str]:
    """映射阶段：每条 category 单独处理，去重但保留首次出现顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for r in requirements:
        cat = str(r.get("category") or "").strip()
        if cat and cat not in seen:
            seen.add(cat)
            out.append(cat)
    return out
