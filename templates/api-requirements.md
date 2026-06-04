# API Requirements

> Phase 2 开始前由父 agent 根据用户确认结果生成。后续 `API_REFERENCE.md`、`CourseRunner`、常驻服务、Web UI、Excel 导入导出都必须以本文件为范围来源。

**画像分支（不要混用模板）**：

| 画像 | 复制来源 |
|------|----------|
| **A — 学科规划型** | 本文件 + 用户多选结果填 Optional 段 |
| **B — 公需年度型** | **`templates/api-requirements-b.md`**（预填跳过项与 Domain Plan；见 `site-profiles.md` §B 型快速路径） |

## Site profile

- **A — 学科规划型** | **B — 公需年度型**（见 `site-profiles.md`）

## Mandatory

- Login / session continuity
- Account / profile info
- Course list
- Course detail and status
- Course progress reporting
- Course exam, if present
- Credit application, if present

## Optional Selected

- <学科列表 / 分类列表 | 注册 | 购卡 / 充值 | 其他：...>

## Optional Not Selected

- <...>

## Site-Specific Notes

- <用户补充的站点特定需求、账号字段、业务限制>

## Phase 2 Domain Plan

- member
- course
- study
- exam (discover and implement only if present)
- credit (discover and implement only if present)
- <selected optional domains>

## Explicit Skips

| Capability | Reason | User confirmed |
|------------|--------|----------------|
| <capability> | <not selected / site has no flow / blocked> | <yes/no> |
