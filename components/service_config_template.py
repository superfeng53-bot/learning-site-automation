"""__SVC__ 引擎配置 + 能力开关 + adapter 工厂（站点覆盖点）。

部署到 <svc>/config.py。引擎所有模块从这里读常量、能力开关与 adapter。
站点要做的：
1. 设 CAPABILITIES（profile / has_exam / has_credit / ...）—— 引擎据此裁剪。
2. build_adapter() 返回站点 adapter 实例（连到 <pkg> 的业务 Service）。
3. 按站点改配额/限频常量。
"""
from __future__ import annotations

import sys
from pathlib import Path

from __PKG__.adapter import Capabilities
from __PKG__.site_adapter import build_adapter as _build_adapter

# ---- 站点能力开关（引擎据此裁剪状态机/表/worker/UI/Excel） ----
CAPABILITIES = Capabilities(
    profile="A",          # "A" 学科规划型 | "B" 公需年度型
    has_exam=False,       # 站点是否有考试
    has_credit=False,     # 是否有申请学分（决定 apply_queue / waiting_apply / ApplyWorker）
    has_recharge=False,   # 是否有购卡/充值
    has_subjects=False,   # 是否需要学科/分类列表
    credential_input_mode="split",  # "split" 两栏 | "combined" 一栏（见 data/account.json）
)


def build_adapter():
    return _build_adapter()


PLATFORM = "__PLATFORM__"
LOGO_LETTER = PLATFORM[:1]

# ---- 运行时路径（PyInstaller 冻结时用 exe 同目录） ----
def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DATA_DIR = project_root() / "data"
RUN_DIR = project_root() / ".run"
DB_PATH = RUN_DIR / "__DB_NAME__"

# ---- 调度（通用） ----
TICK_SECONDS = 3                 # orchestrator tick 间隔
TICK_STARTS_PER_SECOND = 10      # 1s 滚动窗口内最多新拉起的 worker 数
DEFAULT_CONCURRENCY = 400        # 默认并发账号数（UI 可调，上限见 MAX_CONCURRENCY）
MAX_CONCURRENCY = 400
MIN_CONCURRENCY = 1
RETRY_DELAY_SEC = 60             # 瞬时失败重试延迟
MAX_RETRY = 5                    # 超过则 failed

# ---- 8:00 日窗错峰（A 型）；B 型公需无单日限制，可忽略 ----
DAILY_START_HOUR = 8
DAILY_SPREAD_SECONDS = 1800      # 账号按 id 稳定散列到 8:00~8:30

# ---- 单日配额（仅 A 型；B 型不设、不实现） ----
MAX_LEARN_PER_DAY = 1
MAX_APPLY_PER_DAY = 1
APPLY_RATE_LIMIT_BACKOFF_SEC = 300

# ---- HTTP ----
SERVICE_PORT = 17865
