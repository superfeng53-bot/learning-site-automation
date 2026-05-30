# 常驻自动任务服务 — 通用需求说明（模板）

> 本模板从「多账号、长驻、Web 管控、学习 + 异步申请」类自动化系统中抽象需求。
> 将所有 `<...>` 占位符替换为目标站点的实际数值后，作为 `docs/通用需求说明.md` 落入项目。
> 文中「平台」指被自动操作的外部业务系统；「服务」指本地常驻的后台程序。

---

## 1. 文档目的

说明以下四块如何协同：

1. **单账号运行逻辑**：一次被调度执行时，从登录到学习/等待申请的完整管线。
2. **状态机制**：账号主状态、运行阶段、课程粒度状态、申请任务状态。
3. **多账号并行逻辑**：学习侧并发、申请侧独立消费、日切推迟、错峰与上限控制。
4. **Web 控制台**：运营人员如何观察、干预、导入导出与调参。

本说明必须先对齐 `docs/API_REQUIREMENTS.md`。通用学习能力固定存在；考试与申请学分遵循「有则必选」——站点存在则必须实现；学科列表、注册、购卡/充值、其他站点特定流程只在用户已选择并确认时写入本说明、数据库、Web UI、Excel 和调度逻辑。

---

## 2. 系统形态

### 2.1 常驻服务

| 特征 | 说明 |
|------|------|
| 进程 | 单进程 + 后台调度线程（`Orchestrator`）+ 线程池 |
| 持久化 | SQLite WAL，崩溃重启可恢复 |
| 启动恢复 | 残留 `running` 账号回退为 `queued`；`in_flight` 申请回退为 `pending` |
| Web | FastAPI + Uvicorn，单页 HTML 内联 CSS/JS |
| 申请侧 | `ApplyWorker` 在每次 tick 中独立消费申请队列 |

### 2.2 部署与启动（固定）

| 项 | 要求 |
|----|------|
| 一键启动 | `start.sh` / `start.bat` 或打包 exe 双击即可，无需手动装依赖 |
| 单实例 | 同目录只允许一个服务进程（`service.lock`） |
| 二次启动 | 服务已运行时再次启动 → **只打开浏览器**到已有控制台，不启第二个进程 |
| 端口 | 默认 `17865`；占用时自动递增避让；实际 URL 写入 `.run/service/endpoint.json` |
| 打包 | PyInstaller **单文件**；`console=True` 保留终端日志；命名 `{平台中文名}_{日}_{月}`，如 `双卫网_27_05.exe` |
| 可移植 | 单文件复制到其他电脑/目录即可运行；`data/`、`.run/` 与 exe 同目录 |

详见 `phase5-service.md`（Service Entry）与 `phase6-packaging.md`。

### 2.3 技术栈

```
Python 3.9+ / FastAPI / Uvicorn / Pydantic / SQLite WAL
<pkg>（登录/<DOMAIN_LIST>）
zoneinfo / openpyxl / ddddocr / pycryptodome
（可选）<LLM_VENDOR>，用于 <CLASSIFICATION_TASK>
```

### 2.4 已确认能力范围

来源：`docs/API_REQUIREMENTS.md`。

| 类别 | 能力 | 处理方式 |
|------|------|----------|
| 必选 | 登录 / 会话保持 | 必须实现 |
| 必选 | 账号信息获取 | 必须实现 |
| 必选 | 课程列表获取 | 必须实现 |
| 必选 | 课程信息和状态获取 | 必须实现 |
| 必选 | 课程进度上报 | 必须实现 |
| 必选（若存在） | 对应课程考试 | 站点存在考试时必须实现；不存在则记录跳过 |
| 必选（若存在） | 申请学分 | 站点存在申请流程时必须实现；不存在则记录跳过 |
| 可选 | 学科列表 / 分类列表 | <selected/skipped> |
| 可选 | 注册 | <selected/skipped> |
| 可选 | 购卡 / 充值 | <selected/skipped> |
| 可选 | 其他 | <selected/skipped + 说明> |

---

## 3. 核心业务对象

### 3.1 账号（Account）

数据库列：`display_name`、`username`、`password`、`requirements_json`、`extra_json`、`status`、`status_msg`、`retry_count`、`queued_at`、`created_at`、`updated_at`

`extra_json` 存储运行期字段：

| 字段 | 说明 |
|------|------|
| `cookies` | 会话 Cookie（登录后持久化，下次复用） |
| `user_profile` | 平台用户信息 |
| `<DOMAIN>_results` | 学习单元结果集 |
| `phase` | 当前运行阶段（实时） |
| `failed_phase` | 最终失败发生的阶段 |
| `<EXTRA_FIELDS>` | 站点特定字段（如卡号、身份证、地区等） |

**需求槽位**：`requirements_json` = `[{<KEY>, <VALUE>}, ...]`，建议固定槽位数（如最多 2 条）以便 UI 表单化。

### 3.2 课程 / 学习单元状态

每个单元含 `state` 字段：

| state | 含义 |
|-------|------|
| `""` | 待处理 |
| `running` | 进行中 |
| `learned` | 学习完成，待申请 |
| `applied` | 申请成功（终态） |
| `failed` | 失败（终态） |
| `skipped` | 跳过（终态） |

辅助字段：

| 字段 | 说明 |
|------|------|
| `daily_learn_date` | 学完当天日期，用于每日配额判断 |
| `progress_tier` | 平台进度档（见 §3.2.1），数值越小越优先 |
| `subject_tier` | 学科档（见 §3.2.1），数值越小越优先 |
| `queue_rank` | 全局排队序号；由 `progress_tier` → `subject_tier` → 稳定次序（如 `project_id`）排序后从 0 递增赋值 |

### 3.2.1 选课优先级（固定，分配与运行时共用）

构建课表（分配阶段）与挑选下一门待学单元（学习闸门）**同一套多键排序**。`course_planner` / `AccountWorker` 不得另写一套规则。

**第一键 — 平台进度档 `progress_tier`（越小越优先）**

| 值 | 档 | 含义（与平台状态对齐后） |
|----|-----|--------------------------|
| `0` | 已申请 | 学分已在平台申请成功（`state=applied` 或平台等价终态） |
| `1` | 学完未申请 | 学习/考试已完成，学分尚未申请（`state=learned` 或平台等价） |
| `2` | 正在学 | 已选课或已有学习进度、未完结（`state=running` 或平台部分进度） |
| `3` | 未开始 | 无平台进度的新候选（`state=""`） |

**第二键 — 学科档 `subject_tier`（越小越优先）**

| 值 | 档 | 含义 |
|----|-----|------|
| `0` | 所属学科 | 课程学科与账号 `requirements_json` 中某一需求槽（学科1/学科2）匹配 |
| `1` | 公共学科 | 平台标记为「公共」类（站点在 `config.py` 维护标签/ID 列表） |
| `2` | 其他学科 | 以上皆不是 |

规则匹配（含可选 LLM 映射）须先于 LLM；映射结果写入单元字段 `matched_requirement_key`（如 `学科1`）供 UI 展示。

**第三键 — 稳定次序**：同档内按 `project_id`（或平台课程 ID）字典序，保证可复现。

**`queue_rank` 赋值**：对纳入课表的全部单元按 `(progress_tier, subject_tier, project_id)` 排序后，依次赋 `0, 1, 2, …`。DP/贪心凑学分在**该顺序下**依次选取候选，已申请/已学完单元须保留在结果集中（计入完成度，不占当日学习配额逻辑由 §5.4 闸门处理）。

**与账号状态的配合**：当站点存在申请学分流程时，`state=learned` 的单元仍触发 §5.4 第 1 条（转 `waiting_apply`，不开新学）；在课表排序中它们位于 `progress_tier=1`，仅影响列表顺序与再分配时的入选优先级，不改变申请 Worker 行为。若站点无申请学分流程，学习/考试完成即可进入完成判定，不引入 `waiting_apply`。

### 3.3 申请队列任务（apply_queue，仅当站点存在申请学分流程时启用）

| status | 含义 |
|--------|------|
| `pending` | 等待执行 |
| `in_flight` | 执行中 |
| `succeeded` | 成功（终态） |
| `dead` | 失败超过上限（终态） |
| `skipped` | 跳过（终态） |

唯一索引：`(account_id, project_id)`。

### 3.4 运行记录（runs）+ 业务流水（<DOMAIN>_applications）

`runs` 用于审计；业务流水用于按日配额统计与展示。

---

## 4. 状态机制

### 4.1 账号主状态

| 状态 | 含义 |
|------|------|
| `queued` | 等待领取 |
| `running` | 学习 Worker 执行中 |
| `waiting_apply` | 学习完成，申请 Worker 接管（仅当站点存在申请学分流程时启用） |
| `retrying` | 可重试 |
| `completed` | 全部成功 |
| `failed` | 终态失败 |
| `paused` | 人工暂停 |

**关键约束**：站点存在申请学分流程时，`waiting_apply` 不占学习并发槽位。

### 4.2 运行阶段（extra.phase）

| 阶段 | 含义 |
|------|------|
| `login` | 登录 / 会话校验 |
| `assigning` | 资源映射 + 计划生成 |
| `learning` | 主流程执行 |
| `waiting_apply` | 等待异步申请（仅当站点存在申请学分流程时启用） |
| `idle` | 已全部完成 |

---

## 5. 单账号运行逻辑

### 5.1 会话恢复（Token 复用）

1. 若 `extra["cookies"]` 非空 → 装载并 `is_logged_in()` 探活
2. 调用一个**业务级 probe**（如 `<LIGHT_BUSINESS_GET>`）验证会话能办事
3. 探活成功 → 跳过登录与重新分配
4. 探活失败 → 清 Session + 全新登录
5. 全新登录后持久化 `cookies` 与 `user_profile`

### 5.1.1 运行中登录失效（自动重登，必须）

与学习 tick 开头的探活不同，**业务调用过程中**若平台返回未登录/会话失效（由 `is_session_expired()` 判定）：

1. 调用 `SessionManager.relogin_user()` **至多 1 次**，持久化新 `cookies` / `user_profile`
2. **重试当前业务步骤 1 次**
3. 仍失败 → 按 phase 3 重试矩阵区分可重试与硬失败（账号密码错误不得重登循环）

Worker / ApplyWorker / phase-4 Runner 内所有 HTTP 业务层须统一走该路径，**不得**要求用户在 Web UI 手动触发重登。

### 5.2 分配阶段（全新登录或无计划时）

1. 从 `requirements` 构建需求列表
2. 调用 `<ASSIGNMENT_PIPELINE>`：
   - 拉平台资源列表，**合并**账号在平台上的已有进度（已申请 / 学完未申请 / 正在学）
   - 为每条候选标注 `progress_tier`、`subject_tier`（规则见 §3.2.1）
   - 可选 LLM 分类（`<LLM_MODEL>`，`temperature=0`）；规则匹配优先；LLM 结果写入**全局**学科映射缓存（见 §11），**不得**写入 `extra`
   - 按 §3.2.1 排序后做候选生成 + 凑量（DP / 贪心）；**高优先级档先入选课表**
3. 写入 `extra["<DOMAIN>_results"]`：保留平台已有 `state`（`applied` / `learned` / `running` 不强行清空），新入选单元 `state=""`，并写入 `queue_rank`
4. 分配完成 → `queued`

### 5.3 日切闸门

- 早于 **8:00**（Asia/Shanghai）→ 推迟 `queued_at` 到今日 8:00

### 5.4 学习前闸门

按顺序：
1. 若站点存在申请学分流程且有 `state == "learned"` 的单元 → `waiting_apply`（申请侧处理，本步不开新学）
2. 今日已学完 <MAX_LEARN_PER_DAY> 门 → 推迟到明日 8:00
3. 在 `state` 为 `""` 或 `running` 的单元中，选 **`queue_rank` 最小** 的一门（排序已在分配时按 §3.2.1 固化；等价于优先续学「正在学」，再按学科档选未开始）
4. 跳过 `state` 为 `applied` / `failed` / `skipped` 的单元（已申请仅保留在课表中展示与完成度统计）

### 5.5 学习循环

调用 phase-4 的 `<DOMAIN>Runner.run(project_id)` 执行单元的完整流程。

### 5.6 结果处理

| 结果 | 调度器动作 |
|------|-----------|
| 成功且站点存在申请学分流程时 | `state=learned`，写 `apply_queue`（`next_attempt_at=次日 8:00`），账号 `waiting_apply` |
| 成功且站点无申请学分流程时 | `state=learned` 或站点等价完成态，继续下一门或账号 `completed` |
| 可重试失败 | `retrying`，`retry_count+1`，60s 后重试；达上限 → `failed` |
| 不可重试 | `failed` |
| 全部完成 | `completed` |

---

## 6. 申请侧（ApplyWorker，仅当站点存在申请学分流程时启用）

每次 tick 调用 `ApplyWorker.process_one()`：

1. 今日成功数 ≥ <MAX_APPLY_PER_DAY> → 整账号推迟到明日 8:00
2. 复用 `cookies` 加载会话
3. `<APPLY_API_CALL>`
4. 成功 → `apply_queue.status=succeeded`，写流水，单元 `state=applied`
5. 限频 → `next_attempt_at += <APPLY_RATE_BACKOFF_SEC>`
6. 业务失败 → `attempts+1`；达上限（<MAX_APPLY_ATTEMPTS>）→ `dead`，单元 `state=failed`

**申请不受学习暂停影响。** 若站点无申请学分流程，本节整体删除或改为「无异步申请队列；学习/考试完成即为终态」。

---

## 7. 日切与日配额

| 规则 | 值 |
|------|---|
| 日窗口起点 | 8:00 Asia/Shanghai |
| 每日学习上限 | <MAX_LEARN_PER_DAY> 门/账号 |
| 学完当日不申请 | 申请 `next_attempt_at = 次日 8:00` |
| 每日申请成功上限 | <MAX_APPLY_PER_DAY> 门/账号 |
| 申请优先于新学 | 有 `learned` 时不开新学 |

---

## 8. 多账号并行

| 项 | 值 |
|----|---|
| 默认同时运行账号数 | **400**（服务启动时的 `concurrency_limit` 默认值） |
| 并发上限 | 手动设置，范围 `[1, 400]` |
| 错峰间隔 | <STAGGER_SEC>s（每个 tick 最多启动 1 个） |
| Tick 周期 | <TICK_SEC>s |
| 申请侧 | 独立通道，不占学习并发 |

---

## 9. HTTP API 能力清单

见 phase5-service.md 中「FastAPI Endpoints」节。

---

## 10. 持久化表结构

见 `phase5-service.md` 中「Schema」节。除 `accounts / runs / kv` 外，启用 AI 学科映射时须包含全局表 `ai_subject_cache`（**非** `accounts.extra_json` 字段）。

---

## 11. AI 分类（可选）

仅当需求 → 平台分类需要语义映射时启用。

### 11.1 配置

| 项 | 值 |
|----|-----|
| 模型 | `<LLM_MODEL>` |
| 温度 | `0`（确定性输出） |
| 凭证 | `.run/ai_config.json`（服务级，非账号级） |

### 11.2 全局映射缓存（必须）

AI 学科匹配缓存为**服务级全局复用**，所有账号共享；**禁止**写入 `accounts.extra_json`（如 ~~`extra["ai_<TASK>_map"]`~~）。

**复用条件**：当次分配所用「需求学科文本集合」与「平台学科/分类列表快照」与某条缓存记录完全一致时，直接复用该记录的映射结果，**不区分账号**。

| 缓存输入 | 规范化规则 |
|----------|------------|
| 需求学科文本 | 从 `requirements_json` 取所有非空学科字段值（如学科1、学科2），去首尾空白；按 Unicode 字典序排序后 JSON 序列化 |
| 平台学科列表 | 当次从平台拉取的学科/分类列表；按平台 ID 字典序排序；每条保留 `id` + `label`（及分类任务需要的其它稳定字段）；JSON 序列化 |

**缓存键**：`cache_key = sha256(需求学科文本规范化 JSON + "|" + 平台学科列表规范化 JSON)`（hex）。

**缓存值**：`mapping_json`，形如 `{ "<需求学科文本>": { "id": "...", "label": "..." }, ... }` —— 按**学科文本**索引，不按「学科1/学科2」槽位索引；应用到账号时再按各槽位的文本查表。

**持久化**：SQLite 表 `ai_subject_cache`（见 `phase5-service.md` Schema）；服务重启后仍有效。

**查找顺序**（`<svc>/subject_mapper.py` 或等价模块）：

1. 规则匹配（字符串包含、同义词表、`config.py` 静态映射）→ 命中则写入单元 `matched_requirement_key`，**不调 LLM、不写缓存**
2. 用上述规范化输入计算 `cache_key` → 表内命中则应用 `mapping_json`
3. 未命中 → 调用 LLM → 写入 `ai_subject_cache` → 再应用

同一 `(需求学科文本, 平台列表)` 组合在全服务生命周期内只应触发 **一次** LLM 调用（除非运营手动清缓存）。

### 11.3 与账号生命周期的关系

| 操作 | 对全局 AI 缓存 |
|------|----------------|
| 重入队 / 编辑后重入队 | **保留**（只清账号运行态，不清全局缓存） |
| 删除账号 | **保留** |
| 手动清缓存（可选 API/运维） | 按 `cache_key` 或整表清除 |

账号侧仅持久化业务结果字段 `matched_requirement_key`（如 `学科1`），不持久化 LLM 原始响应或映射缓存副本。

---

## 12. Web 控制台与 Excel 导入/导出

### 12.1 账户操作（固定三按钮）

与 `web-ui-spec.md` §6.7、§10.1 一致；列表操作列**仅**：

| 按钮 | 含义 |
|------|------|
| 重入队 | 保留 cookies 等登录指纹；清除登录后全部运行数据；下次探活成功则跳过登录，从分配起走完整登录后流程 |
| 编辑后重入队 | 保存表单变更后执行与「重入队」相同的清除与入队 |
| 删除 | 删除该账号及全部关联数据（含 cookies） |

不提供「强制重登」「重置课程」等第四操作。详情抽屉只读；「复制日志」仅在抽屉内。

- 单文件 HTML，内联 CSS + 原生 JS，无第三方 UI 库
- 5s 轮询 `/api/stats` 与 `/api/accounts`
- 展开行单独 GET `/api/accounts/{id}`
- 导入/导出完整规格见 **`excel-spec.md`**（文件名、Sheet 名、表头字段名**全部中文**）
- 导入模板：`<PLATFORM>账号模板.xlsx`，Sheet `账号列表` + `填写说明`
- 导入列（A–J，顺序固定，**表头必须中文**）：姓名 | 账号 | 密码 | 学科1 | 学分1 | 学科2 | 学分2 | 卡号 | 卡号密码 | 备注
- 导出：前 A–J 与模板一致；后追加 状态 | 说明 | 重试次数 | 创建时间 | 更新时间 | 最近运行结果 | 错误日志
- 禁止英文/拼音列名（如 `username`）；导入只认中文表头；导出文件须可再次导入（忽略 K 列及以后）

---

## 13. 复现检查清单

- [ ] 账号主状态机与已确认能力范围一致（站点存在申请学分流程时包含 `waiting_apply`，否则不出现）
- [ ] 站点存在申请学分流程时，学习队列与申请队列分通道，`waiting_apply` 不占学习并发
- [ ] 单账号管线：Token 复用 → 分配 → 日闸门 → 学习 → 结果归并
- [ ] 课程 `progress_tier` / `subject_tier` / `queue_rank` 与 §3.2.1 选课优先级一致
- [ ] 日切 8:00 固定，每日 <MAX_LEARN_PER_DAY> 学；站点存在申请学分流程时每日 <MAX_APPLY_PER_DAY> 申
- [ ] 站点存在申请学分流程时申请优先：有 `learned` 时不开新学
- [ ] 并发可调、可暂停、活跃计数准确（finally 释放）
- [ ] 崩溃恢复不打死账号
- [ ] 运行中登录失效自动重登（§5.1.1），不依赖 Web UI 手动操作
- [ ] Web：总览、列表、筛选、展开详情、操作（固定三按钮 §12.1）、定时刷新
- [ ] Excel 模板/导入/导出：文件名、Sheet 名、表头字段名均为中文（见 `excel-spec.md`）
- [ ] 导入去重、导出列对齐、模板下载
- [ ] 一键启动、单实例、二次启动只开 WebUI、端口避让、打包单文件与 `{平台}_{日}_{月}` 命名

---

*用前填空：`<PLATFORM> / <SITE_URL> / <DOMAIN> / 8 / <MAX_LEARN_PER_DAY> / <MAX_APPLY_PER_DAY> / 400 / <STAGGER_SEC> / <TICK_SEC> / <APPLY_RATE_BACKOFF_SEC> / <MAX_APPLY_ATTEMPTS> / <LLM_MODEL> / <ASSIGNMENT_PIPELINE> / <APPLY_API_CALL> / <LIGHT_BUSINESS_GET> / <EXTRA_FIELDS>`*
