# API Requirements — <PLATFORM>

> **B′ — 项目驱动型** 预填模板。Phase 2 选定 B′ 后由父 agent 复制为 `docs/API_REQUIREMENTS.md`，按侦察结果只改站点参数，**不要**退回 A 型全量多选或标准 B 型年度路径。权威画像说明：`site-profiles.md` §B′ 型快速路径。

## Site profile

- **B_prime — 项目驱动型**（参考 医学24；`templates/requirements-project-driven.md`）

## Mandatory

- Login / session continuity
- Account / profile info
- 已报名项目列表（如 `getXmxxList` / equivalent）
- 项目下课程列表与进度（如 `getKjxxList` / equivalent）
- Course progress reporting（时间上报 / 视频进度，按站点实际）
- Course exam, if present（由 Phase 2 浏览器侦察判定）
- 项目学分达标判断（`N_JGS >= N_ZXF` 或等价字段）
- **`course_plan.py`**：按项目需求学分 `N_ZXF` 规划计划课程（不必学完项目下全部课）

## Optional Selected

- （默认无；仅用户目标或 gap 确认后填写，例如「购卡 / 充值」）

## Optional Not Selected（B′ 型默认）

- 学科列表 / 分类列表
- 注册
- 购卡 / 充值
- Credit application（申请学分）
- `yearly_learning` / 按年选课 API
- `target_years` 年度字段

## Site-Specific Notes

- 项目需求总分字段：<待侦察，常见 `N_ZXF`>
- 已获学分字段：<待侦察，常见 `N_JGS`>
- 课程学分字段：<待侦察，常见 `N_XF`>
- 最低学习时长字段：<待侦察，常见 `zdxxsc_fz`（分钟）>
- 已学时长字段：<待侦察，常见 `xxsj_fz`（分钟）>
- 上报间隔：<待侦察，常见 90s 标准 / 30s 快速>
- 考试答案格式：<待侦察，常见 `C_ZQDA` 或 `TMXX.C_SFZQDA=1`>

## Phase 2 Domain Plan

- member
- course（enrolled_projects + project_courses + **course_plan**）
- study
- exam（discover and implement only if present）
- project_task（`ProjectTaskRunner` 流水线）
- ~~credit~~（不实现）
- ~~subject list~~（不实现）
- ~~yearly_learning~~（不实现）

## Explicit Skips（B′ 型默认）

| Capability | Reason | User confirmed |
|------------|--------|----------------|
| 学科列表 / 分类列表 | B′ 按已报名项目取课 | yes |
| Credit application | 项目学分达标即可，无申请队列 | yes |
| course_planner（A 型） | 无学科匹配 | yes |
| YearTaskRunner / target_years | 非年度驱动 | yes |
| apply_queue / waiting_apply | 无申请流程 | yes |
| MAX_LEARN_PER_DAY / scheduling | 无单日学习上限 | yes |
