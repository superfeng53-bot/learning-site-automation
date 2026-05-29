# learning-site-automation

面向 Cursor Agent 的技能包：从「学习/继教网站 URL + 测试账号」出发，按六阶段脚手架搭建纯 HTTP 登录、跑课/考试、多账号常驻调度与 Web 控制台（流程提炼自双卫网等项目，站点无关）。

## 目录结构

| 路径 | 说明 |
|------|------|
| `SKILL.md` | 技能入口、Cursor 编排（`cursor-agent-playbook.md`）、六阶段总览 |
| `cursor-agent-playbook.md` | 内置浏览器优先（§1.1）、handoff、验收/缺口闭环（§8）、子 agent、解析用 skill 组合（§5） |
| `web-ui-spec.md` | Phase 5 Web 控制台规格（**简体中文**、复制日志、无 HTML 模板） |
| `excel-spec.md` | Excel 导入/导出规格：**文件名、Sheet 名、表头字段名全部中文**；导出列与导入模板对齐 |
| `phase1-login-recon.md` … `phase6-packaging.md` | 各阶段操作细则与验收清单 |
| `scripts/` | `init_project.py`、`captcha_probe.py` |
| `templates/` | API 需求范围模板、通用需求模板、账号 JSON、项目骨架；`agents/api-recon.md` → `.cursor/agents/` |

## 安装

将本仓库放到 Cursor 技能目录之一即可：

```bash
# 克隆
git clone https://github.com/<你的用户名>/learning-site-automation.git ~/.cursor/skills/learning-site-automation

# 或符号链接到已有克隆
ln -sf /path/to/learning-site-automation ~/.cursor/skills/learning-site-automation
```

也可放在用户级技能目录 `~/.agents/skills/`（若你的 Cursor 配置使用该路径），与官方文档保持一致即可。

## 在 Cursor 中触发

在对话中提供 **站点登录 URL**、**可用的测试用户名/密码**，并说明目标（例如：做自动化、跑课、刷课、持续学习服务）。Agent 会匹配 `SKILL.md` 中的描述并进入六阶段流程；每阶段结束会写 `docs/verification/PHASE<N>_REPORT.md` 并请你确认后再进入下一阶段（有阻塞项时记录在 `docs/gaps/`）。

无需单独命令：确保技能目录已被 Cursor 加载（重启或新开 Agent 会话后通常自动发现）。

## 运营侧中文要求（固定）

生成项目的 Web 控制台与 Excel 导入/导出面向运营人员，以下 surface **必须使用简体中文**：

| 场景 | 要求 | 详细规格 |
|------|------|----------|
| Web 控制台 | 按钮、表头、提示等全部中文 | `web-ui-spec.md` |
| Excel 模板下载 | 文件名 `{平台}账号模板.xlsx`；Sheet `账号列表` / `填写说明` | `excel-spec.md` §2 |
| Excel 导入 | 只认中文表头：姓名、账号、密码、学科1、学分1、学科2、学分2、卡号、卡号密码、备注 | `excel-spec.md` §2 |
| Excel 导出 | A–J 列与模板完全一致；K 起追加：状态、说明、重试次数、创建时间、更新时间、最近运行结果、错误日志 | `excel-spec.md` §3 |

禁止英文或拼音列名（如 `username`、`xingming`）。后端 API / 数据库字段可保持英文，但**用户可见的表格列名、Sheet 名、文件名必须为中文**。

## 许可与注意

- 技能为脚手架，具体站点的验证码、接口形态需写在目标项目代码中。
- 请勿将真实账号、Cookie、`data/` 等敏感内容提交到业务仓库；阶段 1 会指导配置 `.gitignore`。
