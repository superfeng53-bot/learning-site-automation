# 站点架构画像（Site Profiles）

本 skill 支持三类常见继教/公需平台自动化形态。Phase 2 开始前由父 agent 与用户确认 **`site_profile`**，写入 `docs/API_REQUIREMENTS.md` 顶部，后续 phase 4/5、Web UI、Excel、需求文档均按对应画像执行。

参考实现：

| 画像 | 参考项目 | 典型站点 |
|------|----------|----------|
| **A — 学科规划型** | `shuangwei`（双卫网） | 需按学科/学分选课、可选异步申请学分 |
| **B — 公需年度型** | `liangshangongxu`（凉山公需） | 公需科目仅选年份，按年串行学完+考试，无学科匹配、无申请 |
| **B′ — 项目驱动型** | `医学24`（`/Users/fengsuper/Desktop/医学24`） | 已报名项目列表驱动，按 `N_ZXF` 学分上限规划，不必学完项目下全部课程 |

---

## 选型决策（AskQuestion 建议）

Phase 2 **先定画像、再定可选能力**——但 **A / B / B′ 三条路径不对称**：

| 画像 | Phase 2 要问什么 |
|------|------------------|
| **A** | ① 画像单选（若用户目标未写明）→ ② **必选**可选能力多选（学科列表、注册、购卡等） |
| **B** | ① 画像单选（若未推断）→ ② **默认不写多选**；套用 §B 型快速路径；购卡/注册仅触发时追加一问 |
| **B′** | ① 画像单选（若未推断）→ ② **默认不写多选**；套用 §B′ 型快速路径；购卡/注册仅触发时追加一问 |

**可从用户输入/侦察推断、免画像单选**：

| 推断为 | 条件 |
|--------|------|
| **B** | 目标含「公需 / 按年 / 年度学时」；有 `yearly_learning` 或按年选课 API |
| **B′** | 有「已报名项目列表」API；项目带 `N_ZXF` 需求总分；课表挂在项目下；**无** `yearly_learning` |
| **A** | 学科规划 / 双卫式选课 / 申请学分 |

画像单选文案（仅三者不明时）：

```text
该站点属于哪种自动化画像？
- A 学科规划型：账号带学科/学分需求，分配时做学科匹配与课表规划，可有申请学分队列
- B 公需年度型：仅选目标年度（近 5 年），按年拉课表并串行学习+考试，无学科匹配、无申请学分
- B′ 项目驱动型：跑账号下已报名项目，按项目需求学分规划课程，不必学完项目下全部课
```

---

## B 型快速路径（Phase 2–5 默认，少问多写）

选定 **B — 公需年度型** 后，父 agent **立即**从 `templates/api-requirements-b.md` 生成 `docs/API_REQUIREMENTS.md`（替换 `<PLATFORM>` 等占位），并按下表执行；**不要**再跑 A 型那套「五项可选能力全量多选」。

### B 型默认纳入（Mandatory + Phase 2 domains）

| 项 | 默认 |
|----|------|
| 登录 / 会话、账号信息 | yes |
| 按年课包 `yearly_learning`、指定年课表、证书/年度达标 | yes（`course` + `task`/`year_runner`） |
| 学习进度上报、课内考试（侦察到则有） | yes |
| 学科列表 / 分类列表 | **skip**（Explicit Skips） |
| 申请学分 `credit` | **skip**（证书达标即可） |
| `course_planner` / `apply_queue` / `scheduling` 日配额 | **不实现** |
| 需求文档 | `templates/requirements-year-driven.md` → `docs/通用需求说明.md` |
| Web / Excel | `web-ui-spec.md` §14 + `excel-spec.md` §2B |

### 仅在这些情况下追加 AskQuestion（单选或多选其一即可）

| 触发 | 追问内容 |
|------|----------|
| 用户目标含购卡、充值、未购课 | 是否实现「购卡 / 充值」可选域 |
| 用户目标含注册、开户 | 是否实现「注册」可选域 |
| 侦察到除公需外的专业课入口 | 停止默认 B：写 `docs/gaps/PHASE2_mixed_profile.md`，请用户选拆项目或改 A |
| 其他非标流程 | 「其他」+ 一句说明 |

未触发上表 → **零追加提问**，侦察阶段再判定 exam 是否存在（与 A 相同，不提前让用户勾选）。

### B 型 Phase 2 Domain Plan（固定顺序）

```text
member → course（yearly + year_courses + certificate）→ study → exam（if present）→ task|year_runner
```

**不要**侦察或实现：`credit`（申请）、`/subject/list`（除非 gap 已接受）。

---

## 对照总表

| 维度 | A — 学科规划型 | B — 公需年度型 | B′ — 项目驱动型 |
|------|----------------|----------------|-----------------|
| `site_profile` 值 | `A` | `B` | `B_prime` |
| 账号需求 | `requirements_json` | `target_years: string[]` | **无年度**；跑已报名项目 |
| 可选字段 | 学科1/2、学分、卡号、姓名 | 任务模式 `report_mode` | 任务模式 `report_mode` |
| 资源发现 | 学科列表/分类 + 课程目录 | `yearly_learning` → 按年取课 | `list_enrolled_projects` → 项目下课表 |
| 分配/规划 | `course_planner` + DP/贪心 | **无**；年内全部 pending 课 | **`course_plan.py`**：按 `N_ZXF` 学分上限选课 |
| 学科匹配 / LLM | 规则 + 可选 `ai_subject_cache` | **无** | **无** |
| 申请学分 | 可选 `apply_queue` | **无** | **无** |
| 单日限制 | `MAX_LEARN_PER_DAY` 等 | **默认无** | **默认无** |
| 单账号主循环 | 分配 → 日闸门 → `CourseRunner` | `for year: run_year_task` | `for project: ProjectTaskRunner` |
| 考试 | `CourseRunner` 内 | 年度流水线内置 | 每门计划课学完即考 |
| Web 添加区 | 学科/学分… | 年度 pill 多选 | 账号、密码、备注、任务模式（**无年度**） |
| Excel 导入列 | `excel-spec.md` §2 | §2B | §2B′ |
| Phase 4 Runner | `CourseRunner` | `YearTaskRunner` | `ProjectTaskRunner` |
| Phase 5 `extra` | 学科进度 | `year_status` | `project_status` |

---

## A — 学科规划型（当前默认）

权威说明：`templates/requirements.md`、`web-ui-spec.md`、`excel-spec.md`、`phase5-service.md`。

要点：

1. **分配阶段**从 `requirements` 构建需求，拉平台资源列表，标注 `progress_tier` / `subject_tier`，排序后选课表。
2. **学习闸门**按 `queue_rank` 选下一门；有 `learned` 且存在申请流程时转 `waiting_apply`。
3. **Web/Excel** 以学科·学分为核心运营字段。

---

## B — 公需年度型（liangshangongxu 模式）

权威说明：`templates/requirements-year-driven.md`、`web-ui-spec.md` §14、`excel-spec.md` §2B、`phase4-end-to-end.md`（年度 Runner）、`phase5-service.md`（年度 Worker 节）。

### B.1 账号与年度顺序

- DB/API 字段：`target_years`（JSON 数组），入库前规范化：
  - **当前自然年优先**，其余按数字**降序**（与 `liangshangongxu/webui/app.py` `_order_target_years` 一致）。
- 未配置年度时：默认仅跑 **`datetime.now().year`**。
- **无** `requirements_json`、无 `matched_requirement_key`、无 `subject_tier`。

### B.2 API 域（替代学科列表）

| 能力 | 典型实现 | 备注 |
|------|----------|------|
| 历年课程包 | `get_yearly_learning(client, parent_id=1)` | 公需固定 `parent_id`（站点配置） |
| 指定年课表 | `get_year_courses(year)` → `cat_id` 从 yearly 解析 | **不是** `POST /subject/list` |
| 年度达标 | `get_certificate_records` / `is_year_completed` | 获得学时 ≥ 考核学时 |
| 单年流水线 | `run_year_task(year, report_mode, not_purchased_policy)` | 购课校验 → 串行 `study_course` → 每课 `take_exam` → 复检 |

Phase 2 `AskQuestion` 中 **不要** 勾选「学科列表 / 分类列表」除非站点另有非公需专题（超出 B 型首版范围）。

### B.3 单账号执行顺序

```
登录 / 会话复用
  → for year in target_years:          # 数组顺序 = 入库排序结果
       run_year_task(year)
         → 证书/购课校验
         → get_year_courses
         → 过滤未完成 / 待考试
         → 串行学习每门课
         → 每门课后考试（若 exam_id 存在）
         → 年度 completed 则跳过后续课或整年 skip
  → 全部目标年完成 → account completed
```

- **多账号**：线程池并行；**单账号内年度与课程均串行**。
- **无** `ApplyWorker`、`waiting_apply`、**无单日学习/申请配额**（不实现 `MAX_LEARN_PER_DAY`、不因「今日已满」推迟到明日）；多账号仅用 orchestrator 并发 + tick/登录限速；闸门以「年度/证书/购课」为准（见 `requirements-year-driven.md` §4.3）。

### B.4 Web UI — 近 5 年选择

见 `web-ui-spec.md` §14。要点：

- `recent_five_years()` = `[str(now.year - i) for i in range(5)]`。
- UI：**segmented / pill 多选 checkbox**，`name="target_years"`，**默认勾选当前年**。
- 列表展示：`extra.year_status[year]`（已购、要求学时、已获得、完成百分比、当前课程名等）。
- 详情 Tab：**按目标年度分组**课程进度，而非按学科标签。

### B.5 Excel

见 `excel-spec.md` §2B。导入列：`账号 | 密码 | 备注 | 目标年度 | 任务模式`；年度分隔符 `,，;` 或空白；模式别名 `快速/fast` → `report_mode=fast`。

### B.6 Phase 5 数据模型差异

在通用 `accounts` 表上：

- 用 `target_years_json`（或 `requirements_json` 存 `{"profile":"year","years":[...]}` — **推荐独立列** 以免与 A 型混淆）替代学科槽位。
- `extra_json` 必含：`year_status`（按年对象）、`current_year`、`target_years_done`、`report_mode`、`phase`（`auth` / `catalog` / `video_play` / `exam_run` / …）。
- **省略**表：`apply_queue`、`credit_applications`、`ai_subject_cache`（除非用户明确要求 B+C 混合，需单独 gap 文档）。

Worker：`AccountWorker.run_once` 调用 `YearTaskRunner.run(account)`，内部循环 `target_years`，而非 `course_planner.assign()` + `CourseRunner.run(project_id)`。

### B.7 与 A 型共用的部分

仍使用：Phase 1 登录侦察、Phase 3 会话/重试、`HttpClient`、FastAPI 单页控制台骨架、单实例启动、中文 UI、复制日志、`error_log_text`、Excel 导出追加列（状态、说明、错误日志等）。

---

## 文档落点清单

| 画像 | `docs/通用需求说明.md` | `docs/API_REQUIREMENTS.md` |
|------|------------------------|----------------------------|
| A | `templates/requirements.md` | `templates/api-requirements.md` + 用户多选 |
| B | `templates/requirements-year-driven.md` | **`templates/api-requirements-b.md`** |
| B′ | `templates/requirements-project-driven.md` | **`templates/api-requirements-b-prime.md`** |

B 型 **不要**手写精简版 `API_REQUIREMENTS`；从 B 模板复制后只改侦察得到的站点参数（`parent_id`、购课策略、是否保留购卡域等）。

---

## B′ — 项目驱动型（医学24 模式）

权威说明：`templates/requirements-project-driven.md`、`web-ui-spec.md` §15、`excel-spec.md` §2B′、`phase4-end-to-end.md`（ProjectTaskRunner）、`phase5-service.md`（project_sync 节）。

参考实现：`/Users/fengsuper/Desktop/医学24`（`yixue24_api/course_plan.py`、`yixue24_service/project_sync.py`）。

### B′.1 与标准 B 的核心差异

| 维度 | 标准 B（年度） | B′（项目驱动） |
|------|-------------|----------------|
| 课表来源 | `yearly_learning` + `get_year_courses` | `list_enrolled_projects` + `get_project_snapshot` |
| 账号字段 | `target_years_json` | **无年度**；跑全部已报名 pending 项目 |
| 规划逻辑 | 年内全部 pending 课 | `course_plan.py`：按 `N_ZXF` 学分上限选课，**不必学完项目下全部课** |
| Runner | `YearTaskRunner` | `ProjectTaskRunner` |
| Web `extra` | `year_status` | `project_status`（需求总分/已获/计划课程/进度条） |
| 同步 API | 无 | `POST /api/accounts/{id}/sync-projects` |

### B′.2 学分规划（`course_plan.py`）— 必读

复制 `templates/code/api/course_plan.py`，对接站点字段名后实现：

1. **需求总分**：`N_ZXF`（非 `N_KKSJS` 考试门数）
2. **已获学分**：`max(N_JGS, 计划内已通过考试课程学分之和)`
3. **选课优先级**：已考完 → 已学完待考 → 在学（进度 ≥ 5%）→ 未开始
4. **计划课程**：按优先级累加学分至需求上限即停；已通过考试保留在计划列表、runner 跳过重学
5. **项目进度**：已获学分 + 计划内未通过课程的学时/考试折算学分（如 99% 学时的 2.5 分课 → 约 0.5 分进度）
6. **Runner**：`list_pending_courses` 只跑 `actionable_courses`（计划内待执行）

### B′.3 B′ 型快速路径（Phase 2–5）

选定 **B′** 后：

1. 复制 **`templates/api-requirements-b-prime.md`** → `docs/API_REQUIREMENTS.md`
2. 复制 **`templates/requirements-project-driven.md`** → `docs/通用需求说明.md`
3. **不要**实现 `yearly_learning`、`target_years`、`YearTaskRunner`、`course_planner`（A 型）
4. **要**实现：`course_plan.py`、`project_task.py`（`ProjectTaskRunner`）、`project_sync.py`（Phase 5）
5. Web / Excel 按 `web-ui-spec.md` §15、`excel-spec.md` §2B′

Phase 2 Domain Plan：

```text
member → course（enrolled_projects + project_courses + course_plan）→ study → exam（if present）→ project_task
```

### B′.4 Phase 5 数据模型

- `accounts`：**无** `target_years_json`；`requirements_json` 为空 `[]`
- `extra_json` 必含：`project_status`（按项目 ID 索引）、`current_project_id`、`current_course_title`、`report_mode`、`phase`
- Worker：`AccountWorker.run_once` → `ProjectTaskRunner.run_account()`，遍历 pending 项目
- 省略：`apply_queue`、`ai_subject_cache`、`scheduling.py`（同 B）

### B′.5 已知陷阱（医学24 验证）

| 陷阱 | 正确做法 |
|------|----------|
| 默认学完项目下全部课程 | 用 `course_plan.py` 按 `N_ZXF` 规划 |
| 考试答案只读 `C_ZQDA` | 同时解析 `TMXX[].C_SFZQDA=1` 的 `N_XXBH` |
| 学习上报 `RemoteDisconnected` | `HttpClient.ajax_post_safe` 指数退避重试 |
| 「进行中」阈值过低 | 学时比例 ≥ 5% 才纳入计划（避免 1 分钟误纳入） |
| WebUI 表格+卡片双渲染 | `matchMedia` 互斥显示，见 `web-ui-spec.md` §7.4 |
| 抽屉被遮罩盖住 | `#drawerMount` 独立 stacking context，见 §15.6 |
| 复制日志截断 | 用 `addEventListener` 绑定，勿 `onclick` 内嵌 `JSON.stringify` |

---

## 禁止混用（除非用户书面接受 gap）

- B 型 UI 展示学科1/学分1 必填，但后端按年跑课。
- B′ 型误用 `YearTaskRunner` 或年度 pill。
- A 型 `course_planner` + B/B′ Runner 双轨并行且无统一 `extra` schema。
- B/B′ 型保留 `waiting_apply` 状态但无 `apply_queue` 表。

若站点同时有「公需按年」与「专业课按学科」，应拆为两个 `site_profile` 或两个子域 Runner，并在 `docs/gaps/` 记录，不得默认合并进单账号一条管线。
