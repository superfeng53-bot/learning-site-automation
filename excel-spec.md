# Excel 导入/导出规格（固定，中文）

Phase 5 的账号批量导入、模板下载、全量导出**必须**遵守本规格。  
实现前 Read 本文件；生成或修改 xlsx 时同时 Read **`spreadsheet` skill**（`~/.agents/skills/spreadsheet/SKILL.md`）。

同时 Read `docs/API_REQUIREMENTS.md`：列名和顺序保持本规格的兼容形状，但字段是否参与业务逻辑由用户确认的能力范围决定。

---

## 1. 语言与命名（全部中文）

| 项 | 规则 | 示例 |
|----|------|------|
| 模板文件名 | `{平台中文名}账号模板.xlsx` | `双卫网账号模板.xlsx` |
| 导出文件名 | `{平台中文名}账号导出_{YYYYMMDD}_{HHmm}.xlsx` | `双卫网账号导出_20260527_1430.xlsx` |
| Sheet 1 名 | `账号列表` | 固定 |
| Sheet 2 名 | `填写说明` | 固定，中文说明 |
| 表头 | **全部中文**，与下表完全一致 | 见 §2 |
| 单元格说明/错误 | 中文 | 如「账号不能为空」 |

**禁止**：英文 sheet 名、英文列名（如 `username`）、拼音列名。

---

## 2. 导入列定义（`账号列表` Sheet 1）

列顺序**固定**，不可调序。导入解析**只认中文表头**（trim 空格后精确匹配）。

| 列序 | 表头 | 必填 | 类型 | 说明 |
|------|------|------|------|------|
| A | 姓名 | 否 | 文本 | 展示名 |
| B | 账号 | **是** | 文本 | 唯一键 |
| C | 密码 | **是** | 文本 | 导入后存 DB，导出时**留空或掩码** |
| D | 学科1 | 否* | 文本 | 与学分1成对 |
| E | 学分1 | 否* | 数字 | step 0.5 |
| F | 学科2 | 否 | 文本 | 可选第二需求 |
| G | 学分2 | 否 | 数字 | step 0.5 |
| H | 卡号 | 否 | 文本 | 站点支持充值卡时填写 |
| I | 卡号密码 | 否 | 文本 | 敏感，导出掩码 |
| J | 备注 | 否 | 文本 | 运营备注，不参与业务逻辑 |

\* 至少一组「学科+学分」完整，否则该行导入失败并在结果里中文说明。

若 `docs/API_REQUIREMENTS.md` 未选择学科/学分相关需求，可将 D–G 视为可空备注型需求字段，不得因为缺少学科/学分而导入失败。若未选择 `购卡 / 充值`，H/I 必须可空且不触发充值逻辑。

### 填写说明 Sheet 2（固定段落）

至少包含：

1. 表头不可改字、不可调列顺序  
2. 账号、密码必填  
3. 学科/学分成对填写；学分支持 0.5（若本项目未启用学科需求，则可留空）
4. 示例一行（虚构数据）  

---

## 3. 导出列定义（列对齐规则）

**核心规则**：导出文件的前 N 列 = 导入模板的前 N 列，**表头文字、顺序、列数与 §2 完全一致**。  
系统字段**只能追加在后面**，不得插入中间、不得改导入列名。

### 导出列顺序（完整）

**前半 — 与导入一致（A–J）**

`姓名 | 账号 | 密码 | 学科1 | 学分1 | 学科2 | 学分2 | 卡号 | 卡号密码 | 备注`

**后半 — 仅导出（K 起，固定顺序）**

| 列序 | 表头 | 来源 |
|------|------|------|
| K | 状态 | `account.status` → 中文标签（排队/进行中/…） |
| L | 说明 | `account.status_msg` |
| M | 重试次数 | `account.retry_count` |
| N | 创建时间 | 本地时区 `YYYY-MM-DD HH:mm:ss` |
| O | 更新时间 | 同上 |
| P | 最近运行结果 | 最近一条 `runs.result` 中文摘要 |
| Q | 错误日志 | 见 §4，供 UI「复制日志」同内容 |

若站点无卡号字段，导入模板仍保留 H/I 列（可空），导出也保留，保证** round-trip：导出 → 改备注 → 再导入** 时列不错位。

### 密码/敏感列导出策略

- **默认导出**：密码、卡号密码列**留空**（不要明文导出到 Excel）  
- 若用户强需求明文（仅本地运维）：在 `docs/通用需求说明.md` 显式记录后再开放，默认仍禁止  

---

## 4. 错误日志字段（与 Web UI 复制按钮对齐）

后端为每个账号维护可复制的 **`error_log_text`**（UTF-8 纯文本，中文行）。建议格式：

```
【账号】张三 / 13800138000
【状态】失败
【说明】登录失败：验证码过于频繁
【阶段】login
【时间】2026-05-27 14:30:05
【最近运行】run#42 result=failed
--- 明细 ---
1. [login] 验证码重试5次仍失败
2. [runner] ...
```

来源优先级：

1. 最近一次 `runs` 的 `logs_json` 展开  
2. `status_msg`  
3. `extra.phase` + optional async queue error such as `apply_queue.last_error` when credit application is in scope per `docs/API_REQUIREMENTS.md`

列表 API `GET /api/accounts` 的每项在 `status ∈ {failed, retrying}` 时附带 `error_log_text`（其他状态可省略或空字符串）。  
详情 API `GET /api/accounts/{id}` 始终附带 `error_log_text`。

---

## 5. API 与代码约定

| 端点 | 行为 |
|------|------|
| `GET /api/template` | 返回 §2 两 sheet 的 xlsx，`Content-Disposition` 文件名 UTF-8 中文 |
| `GET /api/export` | 返回 §3 完整列 xlsx |
| `POST /api/accounts/upload` | 只解析 §2 中文表头；返回 `{ added, skipped, failed, errors:[{row, reason}] }`，`reason` 中文 |

代码位置建议：

- `<svc>/web/excel_io.py` — `TEMPLATE_COLUMNS` / `EXPORT_EXTRA_COLUMNS` 两个常量列表（中文 str）  
- 导入：`header_map = {cell.value: idx}`，按 `TEMPLATE_COLUMNS` 顺序取列  
- 导出：先写 `TEMPLATE_COLUMNS`，再写 `EXPORT_EXTRA_COLUMNS`  

**验收**：用模板导入 1 行 → 导出 → 用 Excel 肉眼看 A–J 列头与模板 bitwise 一致。

---

## 6. 验收清单

- [ ] 模板下载文件名、sheet 名、表头均为中文  
- [ ] 导入只认中文表头；英文表头行报错中文提示  
- [ ] 导出 A–J 与模板完全一致（顺序、列名）  
- [ ] 导出 K–Q 为追加列，未插入中间  
- [ ] 导出密码列为空（默认策略）  
- [ ] `error_log_text` 与 Web UI「复制日志」内容一致  
- [ ] 导出文件可再次被导入（忽略 K–Q 列或导入逻辑只读 A–J）  
