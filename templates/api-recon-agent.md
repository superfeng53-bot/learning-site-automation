# api-recon 子 Agent 安装说明

嵌套在 Goal 模式的 **Phase 1–2 工人**之内：登录/API 侦察，只写 `docs/`，不写业务代码。不要单独开 New Chat 去跑它。

Agent 正文：**`templates/agents/api-recon.md`**

## 安装到项目（推荐）

```bash
mkdir -p <project_root>/.cursor/agents
cp ~/.cursor/skills/learning-site-automation/templates/agents/api-recon.md \
   <project_root>/.cursor/agents/api-recon.md
```

## 安装到用户级（所有项目）

```bash
mkdir -p ~/.cursor/agents
cp ~/.cursor/skills/learning-site-automation/templates/agents/api-recon.md \
   ~/.cursor/agents/api-recon.md
```

## 使用

由 **Phase 1 或 Phase 2 工人** `Task` 嵌套调用，prompt 写明「遵守 `templates/agents/api-recon.md`（或项目 `.cursor/agents/api-recon.md`）」。父 Goal 管理器不要直接派 api-recon 当一个「阶段」。

编排与梯子见 `cursor-agent-playbook.md` §4、§6。
