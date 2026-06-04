# API Requirements — <PLATFORM>

> **B — 公需年度型** 预填模板。Phase 2 选定 B 后由父 agent 复制为 `docs/API_REQUIREMENTS.md`，按侦察结果只改「if present / 购卡」等行，**不要**退回 A 型全量多选流程。权威画像说明：`site-profiles.md` §B 型快速路径。

## Site profile

- **B — 公需年度型**（参考 liangshangongxu；`templates/requirements-year-driven.md`）

## Mandatory

- Login / session continuity
- Account / profile info
- Yearly course catalog (`yearly_learning` / equivalent)
- Per-year course list + certificate / year completion check
- Course detail and status
- Course progress reporting
- Course exam, if present（由 Phase 2 浏览器侦察判定，不提前让用户勾选）

## Optional Selected

- （默认无；仅用户目标或 gap 确认后填写，例如「购卡 / 充值」）

## Optional Not Selected（B 型默认）

- 学科列表 / 分类列表
- 注册
- 购卡 / 充值
- Credit application（申请学分）

## Site-Specific Notes

- 公需 `parent_id`（或等价参数）：<待侦察填写>
- 购课策略 `not_purchased_policy`：<待侦察填写>
- `report_mode`：标准 / 快速（Web 与 Excel 已支持）

## Phase 2 Domain Plan

- member
- course（yearly_learning + get_year_courses + certificate / is_year_completed）
- study
- exam（discover and implement only if present）
- task 或 year_runner（`run_year_task` 流水线）
- ~~credit~~（不实现）
- ~~subject list~~（不实现）

## Explicit Skips（B 型默认，用户已确认画像）

| Capability | Reason | User confirmed |
|------------|--------|----------------|
| 学科列表 / 分类列表 | B 型按年取课，不用学科目录 | yes |
| Credit application | 公需年度达标以证书/学时为准，无申请队列 | yes |
| course_planner | 无学科匹配与 DP 规划 | yes |
| apply_queue / waiting_apply | 无申请流程 | yes |
| MAX_LEARN_PER_DAY / scheduling 日切 | 公需无单日学习上限 | yes |
