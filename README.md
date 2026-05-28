# learning-site-automation

面向 Cursor Agent 的技能包：从「学习/继教网站 URL + 测试账号」出发，按六阶段脚手架搭建纯 HTTP 登录、跑课/考试、多账号常驻调度与 Web 控制台（流程提炼自双卫网等项目，站点无关）。

## 目录结构

| 路径 | 说明 |
|------|------|
| `SKILL.md` | 技能入口、Cursor 编排（`cursor-agent-playbook.md`）、六阶段总览 |
| `cursor-agent-playbook.md` | 内置浏览器优先（§1.1）、handoff、子 agent、解析用 skill 组合（§5） |
| `web-ui-spec.md` | Phase 5 Web 控制台规格（**简体中文**、复制日志、无 HTML 模板） |
| `excel-spec.md` | 中文 Excel 模板/导出列对齐、`error_log_text` |
| `phase1-login-recon.md` … `phase6-packaging.md` | 各阶段操作细则与验收清单 |
| `scripts/` | `init_project.py`、`captcha_probe.py` |
| `templates/` | 需求模板、账号 JSON、项目骨架；`agents/api-recon.md` → `.cursor/agents/` |

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

在对话中提供 **站点登录 URL**、**可用的测试用户名/密码**，并说明目标（例如：做自动化、跑课、刷课、持续学习服务）。Agent 会匹配 `SKILL.md` 中的描述并进入六阶段流程；每阶段结束会请你确认后再进入下一阶段。

无需单独命令：确保技能目录已被 Cursor 加载（重启或新开 Agent 会话后通常自动发现）。

## 许可与注意

- 技能为脚手架，具体站点的验证码、接口形态需写在目标项目代码中。
- 请勿将真实账号、Cookie、`data/` 等敏感内容提交到业务仓库；阶段 1 会指导配置 `.gitignore`。
