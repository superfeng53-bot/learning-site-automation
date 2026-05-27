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

### 2.2 技术栈

```
Python 3.9+ / FastAPI / Uvicorn / Pydantic / SQLite WAL
<pkg>（登录/<DOMAIN_LIST>）
zoneinfo / openpyxl / ddddocr / pycryptodome
（可选）<LLM_VENDOR>，用于 <CLASSIFICATION_TASK>
```

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

辅助字段：`daily_learn_date`（学完当天日期，用于每日配额判断）、`queue_rank`（全局排队序号）。

### 3.3 申请队列任务（apply_queue）

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
| `waiting_apply` | 学习完成，申请 Worker 接管 |
| `retrying` | 可重试 |
| `completed` | 全部成功 |
| `failed` | 终态失败 |
| `paused` | 人工暂停 |

**关键约束**：`waiting_apply` 不占学习并发槽位。

### 4.2 运行阶段（extra.phase）

| 阶段 | 含义 |
|------|------|
| `login` | 登录 / 会话校验 |
| `assigning` | 资源映射 + 计划生成 |
| `learning` | 主流程执行 |
| `waiting_apply` | 等待异步申请 |
| `idle` | 已全部完成 |

---

## 5. 单账号运行逻辑

### 5.1 会话恢复（Token 复用）

1. 若 `extra["cookies"]` 非空 → 装载并 `is_logged_in()` 探活
2. 调用一个**业务级 probe**（如 `<LIGHT_BUSINESS_GET>`）验证会话能办事
3. 探活成功 → 跳过登录与重新分配
4. 探活失败 → 清 Session + 全新登录
5. 全新登录后持久化 `cookies` 与 `user_profile`

### 5.2 分配阶段（全新登录或无计划时）

1. 从 `requirements` 构建需求列表
2. 调用 `<ASSIGNMENT_PIPELINE>`：
   - 拉平台资源列表
   - 可选 LLM 分类（`<LLM_MODEL>`，`temperature=0`）
   - 候选生成 + 凑量算法（DP / 贪心）
3. 写入 `extra["<DOMAIN>_results"]`，初始化 `state=""`，分配 `queue_rank`
4. 分配完成 → `queued`

### 5.3 日切闸门

- 早于 **<DAILY_START_HOUR>:00**（Asia/Shanghai）→ 推迟 `queued_at` 到今日 <DAILY_START_HOUR>:00

### 5.4 学习前闸门

按顺序：
1. 有 `state == "learned"` 的单元 → `waiting_apply`
2. 今日已学完 <MAX_LEARN_PER_DAY> 门 → 推迟到明日 <DAILY_START_HOUR>:00
3. 选 `queue_rank` 最小的待学单元

### 5.5 学习循环

调用 phase-4 的 `<DOMAIN>Runner.run(project_id)` 执行单元的完整流程。

### 5.6 结果处理

| 结果 | 调度器动作 |
|------|-----------|
| 成功 | `state=learned`，写 `apply_queue`（`next_attempt_at=次日 <DAILY_START_HOUR>:00`），账号 `waiting_apply` |
| 可重试失败 | `retrying`，`retry_count+1`，60s 后重试；达上限 → `failed` |
| 不可重试 | `failed` |
| 全部完成 | `completed` |

---

## 6. 申请侧（ApplyWorker）

每次 tick 调用 `ApplyWorker.process_one()`：

1. 今日成功数 ≥ <MAX_APPLY_PER_DAY> → 整账号推迟到明日 <DAILY_START_HOUR>:00
2. 复用 `cookies` 加载会话
3. `<APPLY_API_CALL>`
4. 成功 → `apply_queue.status=succeeded`，写流水，单元 `state=applied`
5. 限频 → `next_attempt_at += <APPLY_RATE_BACKOFF_SEC>`
6. 业务失败 → `attempts+1`；达上限（<MAX_APPLY_ATTEMPTS>）→ `dead`，单元 `state=failed`

**申请不受学习暂停影响。**

---

## 7. 日切与日配额

| 规则 | 值 |
|------|---|
| 日窗口起点 | <DAILY_START_HOUR>:00 Asia/Shanghai |
| 每日学习上限 | <MAX_LEARN_PER_DAY> 门/账号 |
| 学完当日不申请 | 申请 `next_attempt_at = 次日 <DAILY_START_HOUR>:00` |
| 每日申请成功上限 | <MAX_APPLY_PER_DAY> 门/账号 |
| 申请优先于新学 | 有 `learned` 时不开新学 |

---

## 8. 多账号并行

| 项 | 值 |
|----|---|
| 并发上限 | 手动设置，范围 `[1, <CONCURRENCY_MAX>]` |
| 错峰间隔 | <STAGGER_SEC>s（每个 tick 最多启动 1 个） |
| Tick 周期 | <TICK_SEC>s |
| 申请侧 | 独立通道，不占学习并发 |

---

## 9. HTTP API 能力清单

见 phase5-service.md 中「FastAPI Endpoints」节。

---

## 10. 持久化表结构

见 phase5-service.md 中「Schema」节。

---

## 11. AI 分类（可选）

仅当需求 → 平台分类需要语义映射时启用。配置：`<LLM_MODEL>`、`temperature=0`、账号级缓存（`extra["ai_<TASK>_map"]`）。规则匹配的快速路径要优先于 LLM。

---

## 12. Web 控制台

- 单文件 HTML，内联 CSS + 原生 JS，无第三方 UI 库
- 5s 轮询 `/api/stats` 与 `/api/accounts`
- 展开行单独 GET `/api/accounts/{id}`
- 导入模板：`<PLATFORM>账号模板.xlsx`，中文表头固定顺序

---

## 13. 复现检查清单

- [ ] 账号主状态机（7 种）与学习/申请阶段分离
- [ ] 学习队列与申请队列分通道，`waiting_apply` 不占学习并发
- [ ] 单账号管线：Token 复用 → 分配 → 日闸门 → 学习 → 结果归并
- [ ] 课程 `state` 与 `queue_rank` 全局排序
- [ ] 日切 <DAILY_START_HOUR>:00 固定，每日 <MAX_LEARN_PER_DAY> 学，每日 <MAX_APPLY_PER_DAY> 申
- [ ] 申请优先：有 `learned` 时不开新学
- [ ] 并发可调、可暂停、活跃计数准确（finally 释放）
- [ ] 崩溃恢复不打死账号
- [ ] Web：总览、列表、筛选、展开详情、操作、定时刷新
- [ ] 导入去重、导出、模板下载

---

*用前填空：`<PLATFORM> / <SITE_URL> / <DOMAIN> / <DAILY_START_HOUR> / <MAX_LEARN_PER_DAY> / <MAX_APPLY_PER_DAY> / <CONCURRENCY_MAX> / <STAGGER_SEC> / <TICK_SEC> / <APPLY_RATE_BACKOFF_SEC> / <MAX_APPLY_ATTEMPTS> / <LLM_MODEL> / <ASSIGNMENT_PIPELINE> / <APPLY_API_CALL> / <LIGHT_BUSINESS_GET> / <EXTRA_FIELDS>`*
