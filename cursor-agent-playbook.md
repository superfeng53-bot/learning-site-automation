# Cursor Agent Playbook（本 skill 专用）

本文件教 Cursor Agent **如何在本 skill 的各阶段管理上下文、何时开新对话、何时派子 agent、何时调用其他 skill/MCP**。  
主入口 `SKILL.md` 在 phase gate 处引用本文件；进入 phase 1/2/5 前**先读对应小节**。

---

## 1. Cursor 工具体系（按阶段选用）

| 阶段 | 首选工具 | 用途 |
|------|----------|------|
| Phase 1 登录侦察 | **`cursor-ide-browser` MCP** | 打开登录页、抓 Network、读 cookie/localStorage |
| Phase 1 登录侦察 | **`Task` + `subagent_type=explore`** | 只读梳理页面结构、已有代码、失败码草稿 |
| Phase 1 实现 | **`Task` + `subagent_type=generalPurpose`** | 独立实现 `captcha.py` / `login.py`（输入：侦察摘要文件） |
| Phase 2 API 发现 | **`cursor-ide-browser` MCP** | 手动走一遍业务流，抓每个 domain 的请求 |
| Phase 2 API 发现 | **`Task` + `explore`**（并行） | 每个业务域一份 `docs/api-discovery/<domain>.md` 草稿 |
| Phase 2 实现 | **`Task` + `generalPurpose`**（并行） | 每个 domain 一个 `*Service` + `cli_*.py` |
| Phase 5 Excel | **`spreadsheet` skill**（`~/.agents/skills/spreadsheet/SKILL.md`） | 生成/校验中文模板 xlsx、导出列顺序 |
| Phase 5 Web UI | **`Task` + `generalPurpose`** | 按 `web-ui-spec.md` 生成 `index.html` |
| 任意阶段边界 | **`rename_chat`** MCP | 把对话标题改成 `Phase N · <站点名> · <状态>`，方便用户找 handoff 点 |

**不要**在 runtime 代码里用 browser MCP；它只用于 phase 1–2 侦察。

---

## 2. 上下文压缩 vs 新开对话（固定策略）

Cursor **没有**「一键清空上下文」工具。等效做法是：**把知识写进项目文件 + 用短 handoff 开新对话**。

### 2.1 必须写 handoff 文件的时机

在每个 **phase 结束**、以及下列 **phase 内检查点** 结束时，写入：

```
docs/handoffs/PHASE<N>_<slug>.md
```

`<slug>` 示例：`login-recon-done` / `api-course-exam-done` / `web-ui-done`

Handoff 模板（固定 8 段，每段 1–5 行，**禁止粘贴大段代码**）：

```markdown
# Phase N Handoff — <站点中文名>

## 已完成
- …

## 关键路径（绝对路径）
- …

## 站点决策（不可丢）
- captcha 族：…
- `<pkg>` / `<svc>`：…
- 每日配额：…

## 已验证命令
- …

## 未完成 / 下步第一件事
- …

## 新对话启动语（复制给 Agent）
请继续 learning-site-automation skill，从 Phase X 开始。先 Read：
- docs/handoffs/PHASE…md
- phaseX-….md
项目根：<绝对路径>
```

写完后在聊天里**明确告诉用户**：

> 建议 **New Chat（新对话）**，把上面「新对话启动语」整段粘贴进去再继续。  
> 若继续当前对话，我会只依赖 handoff 文件，不再引用本对话早期的 browser 抓包细节。

### 2.2 何时强烈建议新开对话

| 时机 | 原因 |
|------|------|
| Phase 1 → Phase 2 | browser 抓包 + 验证码试错占满上下文 |
| Phase 2 每完成 **2 个** business domain | 每个 domain 的 request/response 样本很大 |
| Phase 2 → Phase 3 | API 细节应已在 `API_REFERENCE.md`，聊天可丢弃 |
| Phase 5 的「后端 store/worker」→「Web UI」| UI spec 与调度逻辑不应混在同一上下文 |
| 任何阶段内已读 **>8 个文件** 或编辑 **>15 次** | 见 `SKILL.md` Context Budget |

### 2.3 当前对话内压缩（不新开 chat 时）

1. **停止**再读 phase 文件全文；只 `Read` handoff + 当前要改的文件  
2. 浏览器/MCP 原始输出：**不要**留在聊天里复述；写入 `docs/LOGIN_FLOW.md` 或 `docs/api-discovery/*.md`  
3. 子 agent 只回传：**结论 + 文件路径 + 一条验证命令**  
4. 用 `rename_chat` 标记：`Phase 2 · 双卫网 · course+study 完成`

---

## 3. Phase 1–2 推荐编排（子 agent + MCP）

### Phase 1 三步走

```
[父 Agent] init_project.py + 读 phase1-login-recon.md
    ↓
[子 explore 或 父+ browser MCP] Step 2 侦察
    → 产出 docs/LOGIN_FLOW.draft.md（endpoint、captcha、cookie、失败码表）
    ↓
[父 Agent] 审阅 draft → 定 captcha 族 → AskQuestion（若 ambiguous）
    ↓
[子 generalPurpose] 实现 captcha.py + login.py + cli_login.py
    → 输入：draft 路径 + data/account.json
    ↓
[父 Agent] 跑通登录 → 定稿 docs/LOGIN_FLOW.md → PHASE1_handoff
```

**Phase 1 侦察子 agent 提示词骨架**（复制改写）：

```
你是 learning-site-automation Phase 1 侦察子任务。
项目根：<abs_path>
登录 URL：<url>
测试账号：见 data/account.json（勿在回复里复述密码）

用 cursor-ide-browser MCP 完成 phase1-login-recon.md Step 2。
把结论写入 docs/LOGIN_FLOW.draft.md，结构同 LOGIN_FLOW.md 七章。
不要写 login.py。回复只给：draft 路径 + captcha 族判断 + 阻塞项。
```

### Phase 2 按 domain 并行

对每个 relevant domain（course / study / exam / credit / …）：

1. **侦察**：browser MCP 或 `Task explore` → `docs/api-discovery/<domain>.md`  
2. **实现**：`Task generalPurpose` → `<pkg>/<domain>.py` + `cli_<domain>.py`  
3. **父 Agent 合并**：更新 `API_REFERENCE.md` 一节  

**每完成 2 个 domain** → 写 `docs/handoffs/PHASE2_<domains>_done.md`，建议用户新开会话。

Phase 2 侦察子 agent **不要**一次包「全部 6 个 domain」；一次最多 **1–2 个 domain**。

---

## 4. Phase 5 子任务拆分（与上下文）

| 顺序 | 子任务 | 建议执行方式 | handoff 后是否新 chat |
|------|--------|--------------|------------------------|
| 5a | schema + store + recovery | 父 agent 或 1 个子 agent | 可选 |
| 5b | worker + apply_worker + orchestrator | 父 agent | 建议新 chat 再做 5c |
| 5c | FastAPI `/api/*` | 子 generalPurpose | — |
| 5d | Web UI `index.html` | 子 generalPurpose + `web-ui-spec.md` | — |
| 5e | Excel 模板/导入/导出 | 读 **`spreadsheet` skill** + `excel-spec.md` | — |

5c 与 5d 可并行两个子 agent；父 agent 只做集成与 DoD 验收。

---

## 5. 与其他 skill 的协作方式

调用方式：**先 `Read` 对应 `SKILL.md`，再执行**；不要把 spreadsheet 的流程写进本仓库代码注释里。

| 外部 skill | 何时 Read | 本 skill 中的用途 |
|------------|-----------|-------------------|
| `spreadsheet` | Phase 5 做 xlsx 模板/导出 | 中文表头、列宽、说明 sheet |
| `xlsx-manipulation` | 仅需 openpyxl 细粒度改 cell 时 | 可选，spreadsheet 优先 |

MCP **`cursor-ide-browser`**：phase 1–2 专用；调用前 Read `mcps/cursor-ide-browser` 工具 schema（项目内 MCP 描述目录）。

---

## 6. 父 agent vs 子 agent 分工（修订版）

| 必须父 agent | 可子 agent |
|--------------|------------|
| `AskQuestion` | browser 抓包 → draft md |
| `<pkg>`/`<svc>` 命名 | captcha.py / login.py |
| phase gate 与用户确认 | 单个 `*Service` 模块 |
| 合并 API_REFERENCE | 整页 `index.html` |
| 跑通端到端 smoke test | PyInstaller 打包脚本 |
| 写 handoff 文件 | openpyxl 模板生成（在 spreadsheet skill 指导下） |

**修订**：Phase 1 Step 2 **可以**派子 agent 做 browser 侦察，但 captcha 族最终判定与 AskQuestion 仍由父 agent 负责。

---

## 7. Anti-patterns（Cursor 特有）

- ❌ 在同一对话里从 Phase 1 扫到 Phase 5  
- ❌ 子 agent 返回整页 HTML/JSON 样本到聊天（应写文件）  
- ❌ 未写 handoff 就让用户「自己记得」  
- ❌ Phase 5 未读 `web-ui-spec.md` / `excel-spec.md` 就开始写 UI 或 xlsx  
- ❌ 用英文 UI 文案「先跑通再说」  
- ❌ 导出 Excel 重排导入列顺序  
