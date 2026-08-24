# learning-site-automation

面向编码 Agent 的技能包：从「学习/继教网站 URL + 测试账号」出发，用 **Goal 模式** 在 **同一会话** 里跑完 Phase 1–5（纯 HTTP 登录、跑课/考试、多账号常驻调度、中文 Web 控制台）。父 agent 只做管理（`CreateGoal`、闸门、`AskQuestion`）；每一阶段派 **一个** 子 agent。

**打包不在本 Goal。** PyInstaller / 一键启动脚本由目标 OS 上的通用 packaging agent 执行（Cursor / Claude Code / Codex 均可），入口是项目内 `docs/packaging/AGENT.md`。

流程提炼自双卫网等项目，站点无关。

## 目录结构

| 路径 | 说明 |
|------|------|
| `SKILL.md` | Goal 管理器入口（Phase 1–5） |
| `cursor-agent-playbook.md` | 父 agent 编排：一会话、一阶段一 Task、禁止 New Chat |
| `templates/agents/phase-worker.md` | Phase 1–5 工人契约 |
| `templates/agents/packaging.md` | **宿主无关**打包工人（复制到 `docs/packaging/AGENT.md`） |
| `phase6-packaging.md` | 打包规格（复制到 `docs/packaging/SPEC.md`） |
| `web-ui-spec.md` / `excel-spec.md` / `progress-sync.md` | Phase 5 规格 |
| `phase1-login-recon.md` … `phase5-service.md` | 各阶段 DoD |
| `scripts/` | `init_project.py`、`captcha_probe.py` |
| `templates/code/` | 通用代码，工人复制后对接 API |

## 安装

```bash
git clone https://github.com/<你的用户名>/learning-site-automation.git ~/.cursor/skills/learning-site-automation

ln -sf /path/to/learning-site-automation ~/.cursor/skills/learning-site-automation
```

也可放在 `~/.agents/skills/`。

## 在 Cursor 中触发（Goal 模式）

提供 **站点登录 URL**、**测试用户名/密码**、项目路径和一句话目标。父 agent 会：

1. `CreateGoal`（范围到 Phase 5）
2. 每阶段一个子 agent；阶段结束写 `docs/verification/PHASE<N>_REPORT.md`，请你确认后再派下一阶段
3. Phase 5 通过后写入 `docs/packaging/`，`UpdateGoal` complete
4. **不会**要求你开 New Chat

## 在其他 Agent / 其他机器上打包

把业务仓库拷到目标 OS，对任意编码 Agent 说：

> 按 `docs/packaging/AGENT.md` 打包。规格是 `docs/packaging/SPEC.md`。

权威闸门仍是 `scripts/smoke_frozen.py` exit 0。开发态 `python run_service.py` 通过不能代替。

## 运营侧中文要求（固定）

| 场景 | 要求 | 详细规格 |
|------|------|----------|
| Web 控制台 | 按钮、表头、提示等全部中文 | `web-ui-spec.md` |
| Excel 模板下载 | 文件名 `{平台}账号模板.xlsx`；Sheet `账号列表` / `填写说明` | `excel-spec.md` §2 |
| Excel 导入 | 只认中文表头：姓名、账号、密码、学科1、学分1、学科2、学分2、卡号、卡号密码、备注 | `excel-spec.md` §2 |
| Excel 导出 | A–J 列与模板完全一致；K 起追加：状态、说明、重试次数、创建时间、更新时间、最近运行结果、错误日志 | `excel-spec.md` §3 |

禁止英文或拼音列名（如 `username`、`xingming`）。后端字段可英文，**用户可见的表格列名、Sheet 名、文件名必须为中文**。

## 许可与注意

- 技能为脚手架；验证码与接口形态写在目标项目代码中。
- 请勿将真实账号、Cookie、`data/` 提交到业务仓库；Phase 1 会配置 `.gitignore`。
