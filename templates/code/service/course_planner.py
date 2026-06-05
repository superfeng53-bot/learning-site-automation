"""
A 型选课规划与学習闸门辅助（需求 §3.2.1、§5.4）。

站点在分配阶段调用 assign_queue_ranks / build_plan；
学习前调用 check_learning_gates / pick_next_unit。
不 import 任何站点 Service。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from .states import UnitState


def progress_tier_from_state(state: str) -> int:
    """平台进度档：越小越优先（§3.2.1）。"""
    s = state or ""
    if s == UnitState.APPLIED:
        return 0
    if s == UnitState.LEARNED:
        return 1
    if s == UnitState.RUNNING:
        return 2
    if s in (UnitState.PREFILL, "pending"):
        return 3
    return 3


def subject_tier_for_unit(
    unit: Mapping[str, Any],
    *,
    requirement_keys: Sequence[str],
    public_labels: frozenset[str] | set[str] = frozenset(),
) -> int:
    """
    学科档：0=匹配 requirements 槽位，1=公共学科，2=其他。
    unit 可有 matched_requirement_key / subject_label。
    """
    key = unit.get("matched_requirement_key") or ""
    if key and key in requirement_keys:
        return 0
    label = str(unit.get("subject_label") or "")
    if label in public_labels:
        return 1
    return 2


def sort_units_for_plan(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (progress_tier, subject_tier, project_id) 稳定排序。"""
    return sorted(
        units,
        key=lambda u: (
            u.get("progress_tier", progress_tier_from_state(u.get("state", ""))),
            u.get("subject_tier", 2),
            str(u.get("project_id") or ""),
        ),
    )


def assign_queue_ranks(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """排序后写入 queue_rank = 0,1,2,…（原地修改并返回）。"""
    ordered = sort_units_for_plan(units)
    for i, u in enumerate(ordered):
        u["queue_rank"] = i
    return ordered


def pick_next_unit(units: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """在 state 为 pending/空/running 且 selected 的单元中选 queue_rank 最小的一门。"""
    candidates = [
        dict(u) for u in units
        if u.get("selected", True)
        and (u.get("state") or "") in (UnitState.PREFILL, UnitState.PENDING, UnitState.RUNNING)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda u: (u.get("queue_rank", 10**9), str(u.get("project_id") or "")))


def has_learned_pending_apply(
    units: Iterable[Mapping[str, Any]],
    *,
    has_credit_apply: bool,
) -> bool:
    """§5.4(1)：有 learned 且站点有申请流程 → 应转 waiting_apply，不开新学。"""
    if not has_credit_apply:
        return False
    return any((u.get("state") or "") == UnitState.LEARNED for u in units)


def count_learned_today(
    units: Iterable[Mapping[str, Any]],
    *,
    today: date,
) -> int:
    """按 daily_learn_date 统计今日已学完门数。"""
    today_s = today.isoformat()
    n = 0
    for u in units:
        if (u.get("state") or "") in (UnitState.LEARNED, UnitState.APPLIED):
            if u.get("daily_learn_date") == today_s:
                n += 1
    return n


def check_learning_gates(
    units: list[dict[str, Any]],
    *,
    account_id: int,
    has_credit_apply: bool,
    max_learn_per_day: int,
    today: date,
    daily_eligible_at_fn,
) -> tuple[bool, str, float | None]:
    """
    学习前闸门（§5.4）。返回 (blocked, reason, defer_queued_at)。
    blocked=True 时 reason 为状态说明；defer_queued_at 为应写入的 queued_at（Unix）。
    """
    if has_learned_pending_apply(units, has_credit_apply=has_credit_apply):
        return True, "存在已学完待申请单元", None

    if max_learn_per_day > 0 and count_learned_today(units, today=today) >= max_learn_per_day:
        from .scheduling import tomorrow_shanghai
        defer = daily_eligible_at_fn(account_id, local_day=tomorrow_shanghai())
        return True, f"今日已学满 {max_learn_per_day} 门", defer

    if pick_next_unit(units) is None:
        return True, "无待学单元", None

    return False, "", None


def knapsack_by_credits(
    ordered_units: Sequence[Mapping[str, Any]],
    *,
    target_credits: float,
    max_items: int | None = None,
    use_dp: bool = True,
    credit_step: float = 0.5,
) -> list[dict[str, Any]]:
    """
    在已排序列表上凑学分。默认 DP（支持 0.5 步长）；use_dp=False 时退化为贪心。
    调用方应传入已按 §3.2.1 排序的候选；pinned（applied/learned/running）须在外层先并入结果集。
    """
    if target_credits <= 0:
        return []
    if use_dp:
        return knapsack_dp_by_credits(
            ordered_units,
            target_credits=target_credits,
            max_items=max_items,
            credit_step=credit_step,
        )
    selected: list[dict[str, Any]] = []
    total = 0.0
    for u in ordered_units:
        if max_items is not None and len(selected) >= max_items:
            break
        c = float(u.get("credits") or 0)
        if c <= 0:
            continue
        if total >= target_credits:
            break
        selected.append(dict(u))
        total += c
    return selected


def knapsack_dp_by_credits(
    ordered_units: Sequence[Mapping[str, Any]],
    *,
    target_credits: float,
    max_items: int | None = None,
    credit_step: float = 0.5,
) -> list[dict[str, Any]]:
    """
    0-1 背包 DP：在有序候选中选子集使学分总和 >= target，门数尽量少。
    学分按 credit_step 缩放为整数（默认 0.5 → 乘 2）。
    """
    if target_credits <= 0 or credit_step <= 0:
        return []

    scale = max(1, round(1 / credit_step))
    cap = int(round(target_credits * scale))
    if cap <= 0:
        return []

    items: list[tuple[int, dict[str, Any]]] = []
    for u in ordered_units:
        w = int(round(float(u.get("credits") or 0) * scale))
        if w > 0:
            items.append((w, dict(u)))

    if not items:
        return []
    if max_items is not None:
        max_items = max(1, int(max_items))

    n = len(items)
    inf = 10**9
    # dp[i][w] = 达到至少 w 学分所需最少门数（-1 表示不可达）
    dp: list[list[int]] = [[inf] * (cap + 1) for _ in range(n + 1)]
    pick: list[list[int]] = [[-1] * (cap + 1) for _ in range(n + 1)]
    for w in range(cap + 1):
        dp[0][w] = 0 if w == 0 else inf

    for i in range(1, n + 1):
        weight, _ = items[i - 1]
        for w in range(cap + 1):
            skip = dp[i - 1][w]
            take = inf
            if w >= weight:
                prev = dp[i - 1][w - weight]
                if prev != inf:
                    take = prev + 1
            if take < skip:
                dp[i][w] = take
                pick[i][w] = i - 1
            else:
                dp[i][w] = skip
                pick[i][w] = pick[i - 1][w]

    best_w = cap
    while best_w > 0 and dp[n][best_w] == inf:
        best_w -= 1
    if dp[n][best_w] == inf:
        # 无法精确凑满：贪心兜底取前若干门直至达标
        return knapsack_by_credits(
            ordered_units, target_credits=target_credits, max_items=max_items, use_dp=False
        )

    chosen_idx: list[int] = []
    i, w = n, best_w
    while i > 0 and w >= 0:
        p = pick[i][w]
        if p == i - 1:
            chosen_idx.append(p)
            w -= items[p][0]
            i -= 1
        else:
            i -= 1

    selected = [items[j][1] for j in sorted(chosen_idx)]
    if max_items is not None and len(selected) > max_items:
        selected = selected[:max_items]
    return selected
