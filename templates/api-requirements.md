# API Requirements

> Phase 2 开始前由父 agent 根据用户确认结果生成。后续 `API_REFERENCE.md`、`CourseRunner`、常驻服务、Web UI、Excel 导入导出都必须以本文件为范围来源。

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
