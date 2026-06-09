# 通用组件库（components/）

本目录是 learning-site-automation 的**通用引擎**：状态机、调度、worker 流程、SQLite 存储、FastAPI 路由、Excel 导入导出、Web UI 模板等**与站点无关**的代码，全部写成可直接复制的现成组件。

> 设计原则：**通用引擎 + 站点适配器**。
> 引擎只依赖一个接缝——`SiteAdapter`（见 `adapter.py`）。
> 接一个新站点 = 实现这个 adapter（对接站点自己的登录/课程/考试等 API）+ 设置几个能力开关 + 填几个 config 值。
> 用不到的能力（如申请学分、学科规划）直接关掉开关并删对应文件；要补的临时加。

---

## 目录与落点

`scripts/init_project.py` 会把本目录复制进新项目：

| 组件源 | 复制到项目 | 性质 |
|--------|-----------|------|
| `core/*.py` | `<pkg>/`（HTTP 工具核心） | **通用，直接用** |
| `engine/*.py` | `<svc>/`（常驻服务引擎） | **通用，直接用** |
| `engine/web/app.py`、`excel_io.py` | `<svc>/web/` | **通用，直接用** |
| `web/index.html` | `<svc>/web/templates/index.html` | **通用模板**，仅替换 `{{PLATFORM}}`/`{{LOGO_LETTER}}` |
| `adapter.py` | `<svc>/adapter.py` | **通用协议**（接口定义，不要改） |
| `templates/code/pkg/site_adapter_template.py` | `<pkg>/site_adapter.py` | **站点实现**（`build_plan` 已接 `account_pipeline`） |
| `config_template.py` | `<svc>/config.py` | **站点覆盖**（填 BASE_URL、配额、能力开关、profile） |

站点**自己写**的只有这些（“对接 API”的部分）：

| 文件 | 内容 | 阶段 |
|------|------|------|
| `<pkg>/captcha.py` | 站点验证码识别（族别见 SKILL.md 决策树） | phase 1 |
| `<pkg>/login.py` | `LoginService.login()` 返回 `LoginResult` | phase 1 |
| `<pkg>/member.py` `course.py` `study.py` `exam.py`(有则) `credit.py`(有则) | 业务 API Service 类 | phase 2 |
| `<pkg>/site_adapter.py` | 把上面的 Service 接到引擎（实现 `SiteAdapter`） | phase 4–5 |
| `<svc>/config.py` | 能力开关 + 站点常量 | phase 2/5 |
| `<pkg>/responses.py` 的 hint 字典 | 站点失败码 → 中文提示 | phase 2 |

---

## SiteAdapter 接缝（核心）

引擎里**所有站点差异**都通过 `adapter.py` 的 `SiteAdapter` 协议表达。引擎（worker、orchestrator、store、app）**不 import 任何站点 Service**，只调用 adapter 方法。

能力开关（`Capabilities`，放在 adapter 上）：

```python
profile     : "A" | "B"     # A 学科规划型 / B 公需年度型
has_exam    : bool          # 站点是否有考试流程
has_credit  : bool          # 站点是否有申请学分流程（决定 apply_queue / waiting_apply / ApplyWorker）
has_recharge: bool          # 是否有购卡/充值
has_subjects: bool          # 是否需要学科/分类列表（A 型选课用）
credential_input_mode: "split" | "combined"  # Web 添加账号：两栏 vs 一栏自动识别
```

引擎按开关自动裁剪：

- `has_credit=False` → 不建 `apply_queue`/`credit_applications` 表，不起 `ApplyWorker`，`waiting_apply` 不可达。
- `profile="B"` → 不跑 `course_planner`，worker 走 `for year in target_years: run_year(...)`；不实现单日配额。
- `has_subjects=False` → `requirements` 简化，UI/Excel 隐藏学科列。

详见各组件文件头注释与 `adapter.py` 的 docstring。

---

## 接一个新站点的最短路径

1. `python scripts/init_project.py ...` —— 复制本组件库 + 生成站点 stub。
2. phase 1：写 `captcha.py` + `login.py`（引擎的 `SessionManager` 已现成）。
3. phase 2：写各业务 `*Service`；在 `config.py` 设能力开关与站点常量。
4. phase 4：实现 `site_adapter.py`（把 Service 接到引擎的 hook）。
5. phase 5：直接起 `run_service.py`——状态机/调度/store/FastAPI/Excel/Web UI 全是现成组件，无需重写。
6. 用不到的能力：在 `config.py` 关开关，删掉对应站点文件（如 `credit.py`、`apply_worker` 相关）。
7. 要补的能力：在 adapter 上加方法 + 在对应引擎 hook 处调用（临时扩展，不动通用骨架）。

---

## 与旧"规格"文档的关系

`web-ui-spec.md` / `excel-spec.md` / `phaseN-*.md` 仍是**权威规格与验收清单**；本目录是这些规格的**参考实现**。
当组件已满足规格时，phase 文档只需指出"组件已现成在 `<svc>/X.py`，你只实现 adapter 的 Y 方法"。
站点确实需要偏离组件时，按 phase gate 在 `docs/gaps/` 记录后再改。
