# <PLATFORM> 通用需求说明 — B′ 项目驱动型

> 复制为 `docs/通用需求说明.md`，替换 `<PLATFORM>` 等占位符。

## 1. 业务目标

- 多账号常驻服务：自动登录 → 遍历账号下**已报名且未完成**的项目 → 按**学分规划**学习 + 考试 → 项目达标后标记完成。
- **不必学完项目下全部课程**：只需凑够项目需求学分（`N_ZXF`）。
- 无学科匹配、无申请学分队列、无按年选课。

## 2. 单账号执行顺序

```
登录 / 会话复用
  → for project in pending_enrolled_projects:
       build_project_course_plan(project)   # course_plan.py
       for course in plan.actionable_courses:
         study（若需）→ exam（若需）
       项目 completed → 下一项目
  → 全部 pending 项目完成 → account completed
```

- **多账号**：线程池并行；**单账号内项目与课程均串行**。
- **无** `ApplyWorker`、`waiting_apply`、**无单日学习/申请配额**。

## 3. 学分规划规则（`course_plan.py`）

| 规则 | 说明 |
|------|------|
| 需求总分 | `N_ZXF`（项目总学分需求） |
| 已获学分 | `max(N_JGS, 已通过考试课程学分之和)` |
| 选课优先级 | 已考完 → 已学完待考 → 在学（进度 ≥ 5%）→ 未开始 |
| 计划上限 | 按优先级累加 `N_XF` 至需求总分即停 |
| 已通过考试 | 计入已获学分、保留在计划列表、runner 跳过重学 |
| 项目进度 | 已获 + 计划内未通过课的学时/考试折算学分 |

## 4. Web 控制台

- 添加区：账号、密码、备注、任务模式（标准/快速）；**无目标年度**。
- 列表：姓名、账号、备注、状态、进度（`project_status` 汇总）。
- 详情抽屉：按项目展示需求总分、已获学分、计划课程、进度条。
- 「同步项目」按钮：`POST /api/accounts/{id}/sync-projects`。
- 「正在执行」徽章：仅 runner 当前跑的课程；**不**展示站点「学习中」状态（易混淆）。

## 5. Excel

- 导入列：账号、密码、备注、任务模式（见 `excel-spec.md` §2B′）。
- 导出：导入列对齐 + 状态/说明/错误日志等追加列。

## 6. Phase 4 验证

- `--dry-run`：只列计划课程，不实际上报。
- `--max-study-rounds 1`：单课快速验证。
- `report_mode=fast`：缩短上报间隔（如 30s）。

## 7. 与标准 B（年度）的差异

| 项 | 标准 B | B′ |
|----|--------|-----|
| 课表 | 按年 `yearly_learning` | 已报名项目列表 |
| 规划 | 年内全部 pending 课 | `course_plan` 按 `N_ZXF` |
| Web | 年度 pill | `project_status` |
| Runner | `YearTaskRunner` | `ProjectTaskRunner` |
