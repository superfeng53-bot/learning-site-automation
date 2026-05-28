# api-recon 子 Agent 安装说明

用于 **learning-site-automation** Phase 1–2：在 Cursor 内用内置浏览器做登录/API 侦察，只写 `docs/`，不写业务代码。

Agent 正文（可直接复制）：**`templates/agents/api-recon.md`**

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

- 新对话中 **@api-recon** 并给出项目根、Phase 1 登录 URL 或 Phase 2 domain 名；或
- 父 agent 用 **`Task`** 派生子任务，prompt 中写明「遵守 `.cursor/agents/api-recon.md`」。

子 agent 定制见：`~/.cursor/skills-cursor/create-subagent/SKILL.md`  
编排与内置浏览器规则见：`cursor-agent-playbook.md` §1.1、§3、§5。
