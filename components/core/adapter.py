"""SiteAdapter — the single seam between the generic engine and a site.

通用引擎（orchestrator / worker / apply_worker / store / web app）**只**依赖本文件
定义的 `SiteAdapter` 抽象与数据类，从不 import 任何站点 Service。

接一个新站点 = 继承 `SiteAdapter`，按 `Capabilities` 开关实现需要的方法
（见 `site_adapter.py` 模板）。用不到的能力把开关设 False，对应方法可不实现。

依赖方向：`<svc>`(引擎) → `<pkg>`(本文件 + 站点 Service)。不要反向 import 引擎。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# 能力开关：引擎据此裁剪状态机、表结构、worker 流程、UI/Excel 列
# --------------------------------------------------------------------------- #
@dataclass
class Capabilities:
    profile: str = "A"            # "A" 学科规划型 | "B" 公需年度型
    has_exam: bool = False        # 站点是否存在考试流程
    has_credit: bool = False      # 是否有申请学分流程 → apply_queue / waiting_apply / ApplyWorker
    has_recharge: bool = False    # 是否有购卡 / 充值
    has_subjects: bool = False    # 是否需要学科 / 分类列表（A 型选课匹配用）
    credential_input_mode: str = "split"  # "split" 账号+密码两栏 | "combined" 一栏自动识别

    def __post_init__(self) -> None:
        if self.profile not in ("A", "B"):
            raise ValueError(f"profile must be 'A' or 'B', got {self.profile!r}")
        mode = (self.credential_input_mode or "split").strip().lower()
        if mode not in ("split", "combined"):
            raise ValueError(f"credential_input_mode must be 'split' or 'combined', got {mode!r}")
        self.credential_input_mode = mode
        if self.profile == "B":
            # B 型公需年度：无申请、无学科规划
            self.has_credit = False
            self.has_subjects = False


# --------------------------------------------------------------------------- #
# 引擎传给 adapter 的账号视图（已脱离 DB / ORM）
# --------------------------------------------------------------------------- #
@dataclass
class AccountView:
    id: int
    username: str
    password: str
    display_name: str = ""
    cookies: dict[str, str] = field(default_factory=dict)
    requirements: list[dict[str, Any]] = field(default_factory=list)  # A: [{category, credits}]
    target_years: list[str] = field(default_factory=list)             # B: ["2026", "2025"]
    extra: dict[str, Any] = field(default_factory=dict)               # 运行期快照（cookies/user_profile/results...）


# --------------------------------------------------------------------------- #
# 通用结果数据类
# --------------------------------------------------------------------------- #
@dataclass
class StageLog:
    stage: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionResult:
    reused: bool                      # True=复用 cookies 成功，跳过登录
    cookies: dict[str, str]
    user_info: dict[str, Any] | None = None
    error: str | None = None          # 非空表示登录/会话失败
    rate_limited: bool = False
    retryable: bool = True            # 凭据错误 -> False（不要重试）


@dataclass
class CourseUnit:
    """A 型选课/学习的最小单元。引擎按 queue_rank 升序逐门学。"""
    project_id: str
    title: str = ""
    subject_label: str = ""
    credits: float | None = None
    state: str = ""                   # "" | running | learned | applied | failed | skipped
    queue_rank: int = 0
    progress_tier: int = 3            # 0 applied / 1 learned / 2 in-progress / 3 not-started
    subject_tier: int = 2             # 0 required / 1 public / 2 other
    matched_requirement_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """单门课（A 型 CourseRunner）或单次业务调用的结果。"""
    project_id: str
    joined: bool = False
    watched: bool = False
    exam_passed: bool = False
    credit_applied: bool = False
    final_state: str = "running"      # learned / applied / failed
    logs: list[StageLog] = field(default_factory=list)
    error: str | None = None
    retryable: bool = False           # True=瞬时失败（可 retrying）；False=硬失败（failed）


@dataclass
class ProgressProbeResult:
    """整课跑通前的进度增量门禁（默认 60 秒墙钟）。"""
    ok: bool
    project_id: str
    lesson_id: str = ""
    play_time_before: float = 0
    play_time_after: float = 0
    delta: float = 0
    probe_seconds: int = 60
    error: str | None = None
    logs: list[StageLog] = field(default_factory=list)


@dataclass
class ApplyResult:
    ok: bool
    message: str = ""
    code: str | None = None
    hint: str = ""
    rate_limited: bool = False
    retryable: bool = False


@dataclass
class YearResult:
    """B 型单个年度任务结果。"""
    year: str
    completed: bool = False
    earned_hours: float = 0.0
    required_hours: float = 0.0
    progress_percent: float = 0.0
    current_course_title: str = ""
    logs: list[StageLog] = field(default_factory=list)
    error: str | None = None
    retryable: bool = False


# --------------------------------------------------------------------------- #
# 适配器基类：站点继承并按能力开关实现
# --------------------------------------------------------------------------- #
class SiteAdapter:
    """站点适配器基类。

    必须设置 `self.capabilities`（`Capabilities`）。
    根据 profile / 能力开关实现下列方法；不需要的能力对应方法保持 NotImplementedError 即可，
    引擎不会调用被开关关闭的能力。
    """

    capabilities: Capabilities

    # ---- 会话（A/B 通用，必实现） ----
    def ensure_session(self, account: AccountView) -> SessionResult:
        """复用 cookies → probe；失败则登录。返回 SessionResult。

        参考实现：调用 `SessionManager.ensure_session(...)`（core/session_manager.py 已现成）。
        """
        raise NotImplementedError

    def profile_info(self, account: AccountView) -> dict[str, Any]:
        """登录后拉取账号资料（display_name / real_name / id_card / balance...）。
        返回写入 account.extra 的 dict。无则返回 {}。"""
        return {}

    # ---- A 型：学科规划型 ----
    def build_plan(self, account: AccountView) -> list[CourseUnit]:
        """构建该账号的课表（已排序、已写 queue_rank）。
        参考实现：course_planner.assign(requirements, catalog)（按 §3.2.1 tier 排序 + DP/贪心）。"""
        raise NotImplementedError

    def run_course(self, account: AccountView, unit: CourseUnit) -> RunResult:
        """学完一门课（join → watch → exam-if-present）。参考实现：CourseRunner.run(project_id)。"""
        raise NotImplementedError

    def apply_credit(self, account: AccountView, unit: CourseUnit) -> ApplyResult:
        """申请该课学分。仅当 capabilities.has_credit 时被 ApplyWorker 调用。"""
        raise NotImplementedError

    # ---- B 型：公需年度型 ----
    def ordered_years(self, account: AccountView) -> list[str]:
        """归一化目标年度顺序（当前年优先，其余降序）。默认用 account.target_years。"""
        years = [str(y) for y in account.target_years if str(y).strip()]
        if not years:
            from datetime import datetime
            return [str(datetime.now().year)]
        cur = str(__import__("datetime").datetime.now().year)
        rest = sorted((y for y in years if y != cur), reverse=True)
        return ([cur] if cur in years else []) + rest

    def run_year(self, account: AccountView, year: str) -> YearResult:
        """跑完单个年度（取年课表 → 串行学习 → 每课考试 → 证书复检）。
        参考实现：task_api.run_year_task(year, ...)。"""
        raise NotImplementedError

    # ---- 可选：购卡 / 充值 ----
    def recharge(self, account: AccountView, card_no: str, card_pwd: str) -> ApplyResult:
        raise NotImplementedError
