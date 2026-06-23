# 学习进度同步 — B / B′ 型 Worker + Web UI 规范

> 从四川专技（SCZJ）项目沉淀。Phase 4 暴露回调，Phase 5 Worker 写 `extra_json`，Web 抽屉只读展示。

## 目标

1. **账号详情**展示：正在学的课程、单元/课节及各自进度。
2. **总进度**：每个课节完成时从**服务端**刷新年度/账号总进度（不靠本地累加）。
3. **列表 `status_msg`**：运行中显示 `2026年 · 课程名 · 课节名 85%`。
4. **列表进度条**：已获得学时为 0 时，展示**课程学习进度**（避免长期显示 0%）。

## 两套进度指标（勿混淆）

| 指标 | 来源 | 何时 > 0 |
|------|------|----------|
| **年度学时进度** `annual_progress_percent` | 服务端 `annual_completion`（如 `publicNum / 30`） | 课程完成、学时计入后 |
| **课程学习进度** `course_learning_percent` | 已购课程 `percent` 平均值 | 学习中即有值 |
| **展示用总进度** `progress_percent` | `annual` 优先；`annual==0` 时回退 `course_learning_percent` | 见 `build_year_progress` |

详情抽屉「已获得」仍显示真实 `earned_hours`；「总进度」与列表条使用展示用 `progress_percent`（学时未计入时显示课程进度并标注「（学习中）」）。

## 年度完成判定（`run_year_task`）

**勿仅用 `annual_completion.publicNum`** 判定年度是否完成。部分站点课程 100%、证书已通过，但 `publicNum` 仍为 0。

复制 `templates/code/pkg/year_task_template.py` → `<pkg>/year_task.py`，使用 `_resolve_year_completion()`：

| 优先级 | 条件 | 结果 |
|--------|------|------|
| 1 | 证书 `auditStatus == 1` | 已完成（跳过学习） |
| 2 | 全部课程 finished + 证书已提交（`auditStatus >= 0`） | 已完成 |
| 3 | `cert_svc.is_year_public_completed()` | 已完成 |
| 4 | `publicNum >= target_hours` | 已完成 |
| 否则 | | 失败「公需学时未达标（publicNum=…）」 |

学完后若证书已提交/已通过，**跳过** `cert_apply` 重复申请。

`build_year_progress(..., cert_svc=...)`：证书已通过时 `progress_percent=100`、`completed=true`（即使 `publicNum=0`）。

## 数据模型（`extra_json`）

| 字段 | 写入时机 | 内容 |
|------|----------|------|
| `learning_progress` | 课节开始 / 学习中（节流） | `{ year, course_id, course_title, hour_id, hour_title, chapter_title, percent, percent_name }` |
| `year_status[year]` | 课节开始 / **课节完成** + 年度任务结束 | `{ required_hours, earned_hours, annual_progress_percent, course_learning_percent, progress_percent, completed, courses[], ... }` |
| `progress_percent` | 同 `year_status` 刷新 + tick 轻量更新 | 列表进度条；取各年展示进度最大值 |
| `current_course_id` / `current_course_title` | 课节开始 | 快速展示 |

`year_status[year].courses[]` 每项：

```json
{
  "course_id": "...",
  "title": "...",
  "percent": 0.65,
  "percent_name": "65%",
  "finished": false,
  "hours": [
    {
      "hour_id": "...",
      "title": "第一节",
      "chapter_title": "第一章",
      "percent": 0.5,
      "percent_name": "50%",
      "finished": false
    }
  ]
}
```

**性能**：仅对**当前学习课程**（或首个未完成课）拉 `getLearnInfo` 课节树；已完成课只保留课程级 `percent`。

## Phase 4 — `StudyService.study_course` 回调

在 `<pkg>/study.py` 的 `study_course` 增加（模板见已对接站点）：

| 回调 | 签名 | 触发 |
|------|------|------|
| `on_hour_start` | `(course_id, course_title, hour)` | 每个待学课节开始前 |
| `on_progress_tick` | `(course_id, course_title, hour, play_seconds)` | `watch_hour` 每次上报（Worker 侧节流，建议 ≥20s） |
| `on_hour_complete` | `(course_id, course_title, hour, resp)` | 课节 `watch_hour` 结束 |

`year_task.run_year_task` / B′ 项目 runner 须把上述回调透传给 `study_course`。

## Phase 4 — `<pkg>/progress_snapshot.py`

复制 `templates/code/pkg/progress_snapshot_template.py` → `<pkg>/progress_snapshot.py`，对接：

- `build_year_progress(course_svc, study_svc, year, *, active_course_id=None)` — 年度总进度 + 已购课列表；**含 `annual_progress_percent` / `course_learning_percent` / 展示用 `progress_percent`**
- `snapshot_hour(study_svc, course_id, hour_id)` — 单课节进度
- `collect_learn_hours(study_svc, course_id)` — 课节树
- `format_status_msg(year, course_title, hour_title, percent_name)` — 中文 status_msg

`build_year_progress` 核心逻辑：

```python
annual_pct = round(100 * earned_hours / required)  # 来自 annual_completion API
course_learning_pct = average(in-progress course percent) * 100
display_pct = annual_pct if annual_pct > 0 else course_learning_pct
```

## Phase 5 — B 型 Worker 模式

复制 `templates/code/service/worker_b_template.py` → `<svc>/worker.py`，对接 `<pkg>` 的 `progress_snapshot` 与 `run_year_task`。

核心逻辑：

1. `on_hour_start` → `snapshot_hour` + **`build_year_progress`（刷新课程级进度）** → 写 `learning_progress` + `progress_percent` + 更新 `status_msg`
2. `on_progress_tick`（节流）→ 更新 `learning_progress` + `status_msg`；**若当前课节进度高于已存 `progress_percent`，轻量抬升列表进度**（不调年度 API）
3. **`on_hour_complete` → `build_year_progress(..., active_course_id=...)` → 合并进 `year_status[year]` + `progress_percent`**
4. 年度任务结束 → 再刷一次 `build_year_progress`

## Phase 5 — `store.requeue_account`

`requeue` 须清除运行期字段（保留 `cookies` / `report_mode` / `remark` 等配置）：

`learning_progress`, `progress_percent`, `year_status`, `current_course_id`, `current_course_title`, `phase`, …

见 `templates/code/service/store.py` 中 `_B_RUNTIME_EXTRA_KEYS`。

## Web UI（B 型 §14）

- **基本信息** tab：`正在学习` 一行（来自 `learning_progress`）
- **年度进度** tab：`renderYearProgressB()` + `yearDisplayPercent()` — 年度总进度条 + 课程块 + 课节列表（高亮 `learning_progress.hour_id`）；学时未计入时总进度显示课程进度并标注「（学习中）」
- 列表 `progressPercent()`：**勿**在 `progress_percent===0` 时直接返回 — 用 `yearDisplayPercent()` 回退到 `course_learning_percent` / 课程 `percent` / `learning_progress.percent`

CSS 类：`.course-block`, `.course-active`, `.unit-row`, `.unit-row.active`, `.unit-bar` — 见 `templates/code/web/index.html`。

## B′ 型

同模式，字段改为 `project_status[project_id]` + `learning_progress`（含 `project_id`）；课节完成时调用 `build_project_status()` 刷新项目总进度。见 `web-ui-spec.md` §15。

## 反模式

- **不要**在 Web UI 做「分列 / 一栏凭证」运行时切换 — `credential_input_mode` 是**项目级**配置（`data/account.json` + 重启服务）。
- **不要**仅用本地 `play_seconds` 推算**年度学时** — 课节完成必须调站点年度/项目完成度 API。
- **不要**每个 tick 都拉全量课表 — 课节完成（及课节开始时的课程快照）才刷新 `year_status`；tick 只更新 `learning_progress` 与可选的列表展示进度。
- **不要**在 `progressPercent()` 里见到 `extra.progress_percent === 0` 就返回 — 课程明细里可能有非零学习进度。
