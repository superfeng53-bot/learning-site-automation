"""
服务级常量（复制到 <svc>/config.py 后按站点改配额与映射规则）。
学科映射/选课规则全部在此配置，模板不写死任何站点科目名或 ID。
"""
from __future__ import annotations

# ── 调度并发（与 templates/requirements.md §8 一致）────────────────────────────
DEFAULT_CONCURRENCY = 400
MAX_CONCURRENCY = 400
MIN_CONCURRENCY = 1

TICK_SECONDS = 3
TICK_STARTS_PER_SECOND = 10
RETRY_DELAY_SEC = 60
MAX_RETRY = 5

# ── 8:00 日窗错峰（A 型）；B 型可不使用 scheduling ───────────────────────────
DAILY_START_HOUR = 8
DAILY_SPREAD_SECONDS = 1800

# ── 单日配额（A 型；B 型设为 0 表示不启用对应闸门）────────────────────────────
MAX_LEARN_PER_DAY = 1
MAX_APPLY_PER_DAY = 1
APPLY_RATE_LIMIT_BACKOFF_SEC = 300
MAX_APPLY_ATTEMPTS = 5

SERVICE_PORT = 17865

# ── A 型：需求槽位与 extra 字段名 ────────────────────────────────────────────
MAX_REQUIREMENT_SLOTS = 2
AI_SUBJECT_MAP_KEY = "ai_subject_map"
COURSE_RESULTS_KEY = "course_results"
COURSE_RESULTS_GROUPS_KEY = "course_results_groups"

# ── 平台学习进度字段映射（站点按 API 改值，非科目名）──────────────────────────
# priority_bucket 用这些值判断「已获学分 / 已学完 / 学中」
PLATFORM_PROGRESS = {
    "credited_values": (3, "credited", "applied"),
    "finished_values": (2, "finished", "learned"),
    "in_progress_values": (1, "in_progress", "running"),
}

# ── 公共科目（阶段2 补齐用；填平台 subject_id 或 label，站点自行配置）────────
PUBLIC_SUBJECT_IDS: list[str] = [
    # "109", "118",
]
PUBLIC_SUBJECT_LABELS: frozenset[str] = frozenset({
    # "公共卫生与预防医学", "全科医学",
})

# ── 学科映射规则链（按顺序匹配，命中且 fail_on_miss 时失败则不落 LLM）────────
# 示例结构（部署时替换 trigger_keywords / list_match_preferred_labels）：
# SUBJECT_MAPPING_RULES = [{
#     "id": "special_list_match",
#     "trigger_keywords": ["关键词A", "关键词B"],
#     "strategy": "list_match",
#     "list_match_preferred_labels": ["平台主类别名1", "平台主类别名2"],
#     "fallback_first": False,
#     "forbid_public_supplement": True,
#     "course_title_keywords": ["标题过滤词1", "标题过滤词2"],
#     "fail_on_miss": True,
# }]
SUBJECT_MAPPING_RULES: list[dict] = []

# 空人员类别（category 为空）→ 列表匹配默认学科
EMPTY_CATEGORY_FALLBACK = {
    "preferred_labels": [],       # 如 ["全科医学"]
    "fallback_first": True,       # 无匹配时取平台列表第一项
    "forbid_public_supplement": False,
    "course_title_keywords": [],
}

# 规则未命中时的静态映射（category 文本 → 平台 subject_id）
SUBJECT_STATIC_ID_MAP: dict[str, str] = {}

# 同义词（课级 rule_match_unit_to_slot 用）
SUBJECT_SYNONYMS: dict[str, list[str]] = {}

# LLM 单条映射（学科1、学科2 各调一次；见 llm_subject.py + .run/ai_config.json）
USE_LLM_SUBJECT_MAPPING = False
LLM_PROVIDER = "dashscope"
LLM_MODEL = "qwen3.5-flash"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 国际节点可改为 https://dashscope-intl.aliyuncs.com/compatible-mode/v1
