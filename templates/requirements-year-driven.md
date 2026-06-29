# 常驻自动任务服务 — 公需年度型需求说明（模板）

> **Site profile B** — 无学科匹配、无申请学分；账号仅配置 **目标年度**，按年串行完成学习+考试。  
> 参考：`liangshangongxu`（`/Users/fengsuper/Desktop/liangshangongxu`）。  
> 将 `<...>` 替换为站点实际值后，作为 `docs/通用需求说明.md` 落入项目。  
> 与 **学科规划型**（`templates/requirements.md`）二选一，勿混用。

---

## 1. 文档目的

说明：

1. **单账号运行逻辑**：登录 → 按 `target_years` 顺序 → 每年 `run_year_task`（学习 + 考试）→ 证书学时达标。
2. **状态机制**：账号主状态、`extra.phase`、按年 `year_status`、课程粒度状态（可选）。
3. **多账号并行**：线程池并行账号；**单账号内年度与课程串行**。
4. **Web 控制台**：近 5 年 pill 多选、列表按年进度、无学科表单。

须对齐 `docs/API_REQUIREMENTS.md`（`site_profile: B`；Phase 2 由 **`templates/api-requirements-b.md`** 生成，见 `site-profiles.md` §B 型快速路径，无需 A 型可选能力全量多选）。

---

## 2. 系统形态

与 A 型相同部分：SQLite WAL、单实例、端口避让、PyInstaller 单文件、中文 Web UI — 见 `templates/requirements.md` §2.1–2.3。

**不包含**：`apply_queue`、`ApplyWorker`、`waiting_apply`、`ai_subject_cache`、学科 LLM 映射、`course_planner` DP/贪心。

---

## 3. 核心业务对象

### 3.1 账号（Account）

| 字段 | 说明 |
|------|------|
| `display_name` / `username` / `password` | 与 A 型相同；B 型 Web 表单可仅「账号」列名 |
| **`target_years_json`** | JSON 字符串数组，如 `["2026","2025"]`；入库前 **当前年优先，其余降序** |
| `extra_json` | 见下表 |
| `status` | `queued` / `running` / `retrying` / `completed` / `failed` / `paused`（**无** `waiting_apply`） |

`extra_json` 运行期（示例）：

| 字段 | 说明 |
|------|------|
| `cookies` | 会话 |
| `user_profile` / `real_name` / `id_card` | 登录后解析 |
| `report_mode` | `normal` / `fast`（**标准**=站点步长+频率 1:1；**快速**=步长不变、仅缩短间隔；见 `phase2-api-tools.md` § Video Progress） |
| `target_years` | 与 DB 同步副本 |
| `current_year` | 正在执行的年份 |
| `target_years_done` | 已完成年度列表 |
| **`year_status`** | `{ "<year>": { required_hours, earned_hours, annual_progress_percent, course_learning_percent, progress_percent, completed, courses[{ course_id, title, percent, hours[] }], ... } }` — **课节开始/完成时从服务端刷新**（见 `progress-sync.md`） |
| **`learning_progress`** | 当前课节：`{ year, course_id, course_title, hour_id, hour_title, chapter_title, percent, percent_name }` |
| **`progress_percent`** | 列表进度条；展示用总进度（`annual_progress_percent` 优先，学时为 0 时回退 `course_learning_percent`） |
| `phase` | `auth` / `course_discover` / `cert_check` / `purchase_check` / `catalog` / `video_plan` / `video_play` / `exam_run` / `done` |
| `current_course_title` / `current_course_id` | UI 展示；课节开始时写入 |

**无** `requirements_json` 学科槽位。

### 3.2 年度与课程

- **年度完成**：证书页 **获得学时 ≥ 考核学时**（`<CERTIFICATE_API>`）。
- **单年待办**：`get_year_courses(year)` 中 `finished=false`，或已学完但仍需考试（`<NEEDS_EXAM_FN>`）。
- **未购课**：策略 `<NOT_PURCHASED_POLICY>`：`fail` / `skip` / `mark`（全局设置）。

### 3.3 考试

- **内置在年度流水线**：每门待处理课 `study_course` 成功后调用 `take_exam(exam_id)`（若存在）。
- 题库目录：`<ANSWERS_DIR>/exam_{id}.json`（站点定制）。
- **无** 账号级「自动考试」开关（相对旧版需求已移除）。

---

## 4. 单账号运行逻辑

### 4.1 会话恢复

同 A 型 §5.1：`cookies` + `is_logged_in()` + 业务 probe；成功则跳过登录。

### 4.2 执行主循环（无分配阶段）

1. 解析 `target_years`；空则 `[当前年]`。
2. **`for year in target_years`**（顺序 = 入库排序，勿在运行时重排）：
   - 若 `year_status[year].completed` 且无 pending 课 → **skip 该年**
   - 调用 `<RUN_YEAR_TASK>(year, report_mode, not_purchased_policy)`
   - 更新 `year_status`、`current_year`、`phase`
3. 全部目标年完成 → `completed`。

### 4.3 单日限制（公需：无）

**公需年度型默认无单日限制**（参考 `liangshangongxu`）：平台不按「每天只能学 N 门 / 每天只能申 N 次」卡进度，Worker **不得**实现 A 型那套日配额闸门。

| 规则 | B 型（公需） |
|------|----------------|
| `MAX_LEARN_PER_DAY` | **不配置、不实现** |
| `MAX_APPLY_PER_DAY` | **不适用**（无申请） |
| `daily_learn_date` / 学完推迟到明日 | **不使用** |
| `daily_eligible_at` 推迟 `queued_at` | **不因学习配额使用**；账号可连续跑完当前年所有待学/待考课 |
| 8:00 日切错峰 | **默认不需要**；多账号仅用 tick/线程池错峰 + 登录限速 |
| 完成节奏 | 仅受 **证书学时、购课、未购课策略、平台接口限频** 约束 |

`AccountWorker` 学习前闸门只保留：会话有效 → 按 `target_years` 顺序 → 年内下一门 pending；**不要**插入「今日已学完 N 门 → 推到明天 8:00」逻辑。

### 4.4 结果处理

| 结果 | 动作 |
|------|------|
| 单年成功 | 标记该年 `completed`，继续下一年 |
| 可重试 | `retrying`，60s 后重试当前年或当前课 |
| 不可重试 | `failed`，写 `error_log_text` |
| 用户停止 | `paused`，`failure_kind=cancelled` |

---

## 5. 多账号并行

| 项 | 值 |
|----|---|
| 默认并发 | `<MAX_WORKERS>`（如 10） |
| 登录限速 | `<MAX_CONCURRENT_LOGINS>` + interval + jitter |
| 单账号 | 年度串行、课程串行 |
| Tick | 同 A 型 orchestrator 或 Flask 2s dispatcher（实现选型） |

---

## 6. HTTP API 能力（B 型）

| 域 | 端点/函数 | 必选 |
|----|-----------|------|
| 登录 | Phase 1 | 是 |
| 历年包 | `get_yearly_learning(parent_id=<公需ID>)` | 是 |
| 年课表 | `get_year_courses(year)` | 是 |
| 学习上报 | `study_course` / `study_lesson` | 是 |
| 考试 | `take_exam` 等 | 站点有则必选 |
| 证书 | `get_certificate_records` | 是 |
| 编排 | `run_year_task` | 是 |
| 学科列表 | — | **跳过** |
| 申请学分 | — | **跳过** |

---

## 7. Web 控制台

- 添加区：**账号+密码**（`split` 分两栏 / `combined` 一栏 `textarea` 自动识别，见 `web-ui-spec.md` §6.5）、**备注、近 5 年年度 pill（多选，默认当前年）、任务模式（标准/快速）**。
- 列表：**姓名**（登录后自动获取）、账号、备注、目标年度摘要、进度条或按年百分比。
- 展开/抽屉：按 **`year_status`** 分年展示（要求学时、已获得、总进度、**课程与课节列表**）；运行中 **`learning_progress`** 高亮当前课节；**无** 学科·学分 pill 行。
- 操作：重学 / 编辑重学 / 删除（同 A 型 §12.1）；**无** 申请队列 Tab。

详见 `web-ui-spec.md` §14。

---

## 8. Excel

见 `excel-spec.md` §2B：`账号 | 密码 | 备注 | 目标年度 | 任务模式`（`combined` 时首列插入「账号密码」）+ 导出追加列。

---

## 9. 复现检查清单

- [ ] `docs/API_REQUIREMENTS.md` 标明 `site_profile: B`
- [ ] 无 `apply_queue` / `waiting_apply` / 学科映射缓存
- [ ] 添加账号与导入均支持 `target_years`，Web 有近 5 年 pill
- [ ] 单账号按 `target_years` 顺序调用 `run_year_task`，年内串行学习+考试
- [ ] **无**单日学习/申请上限（无 `MAX_LEARN_PER_DAY`、无因日配额推迟到明日）
- [ ] 完成判据为证书学时达标，非申请态
- [ ] `get_year_courses` 替代学科列表拉取
- [ ] 中文 UI + Excel + 复制日志 + 单实例启动

---

*填空：`<PLATFORM>` / `<SITE_URL>` / `<公需 parent_id>` / `<REPORT_STEP>` / `<REPORT_INTERVAL_NORMAL>` / `<REPORT_INTERVAL_FAST>` / `<FAST_REPORT_SUPPORTED yes|no>` / `<NOT_PURCHASED_POLICY>` / `<MAX_WORKERS>` / `<RUN_YEAR_TASK>` / `<CERTIFICATE_API>`*
