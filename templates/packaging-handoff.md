# Packaging Handoff — <站点中文名>

Goal 模式在 **Phase 5** 结束。打包不在本会话、不在本 Cursor Goal 里做。

## 下一动作（任意编码 Agent，在目标 OS 上）

把本仓库放到要出包的机器（Windows 出 `.exe`，macOS 出 Mac 二进制）。对 Agent 说：

> 按 `docs/packaging/AGENT.md` 打包。规格是 `docs/packaging/SPEC.md`。

不要开 New Chat 来「继续 Phase 6」——那是旧编排。本文件 + `docs/packaging/` 就是全部输入。

## 关键路径

- 项目根：`<PROJECT_ROOT>`
- `<pkg>`：`<pkg>`
- `<svc>`：`<svc>`
- 平台中文名（二进制前缀）：`<平台>`
- Phase 5 报告：`docs/verification/PHASE5_REPORT.md`
- 开发态入口（**不能**代替打包 smoke）：`python run_service.py`

## 站点决策（不可丢）

- `site_profile`：A | B | B_prime
- captcha 族：…
- `credential_input_mode`：split | combined

## 验收权威

`scripts/smoke_frozen.py` exit 0（见 SPEC.md）。venv / `./start.sh` 通过不算打包完成。
