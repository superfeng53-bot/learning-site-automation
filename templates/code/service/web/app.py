"""
FastAPI Web 控制台。
复制到 <svc>/web/app.py，替换：
  <SVC>      包名（如 sww_service）
  <PLATFORM> 平台中文名（如 双卫网）
  store / orchestrator / excel_io 均从外部注入（由 run_service.py 传入）。

mount 方式：在 run_service.py 的 lifespan 中初始化 store/orchestrator，
然后 app.state.store = store; app.state.orch = orch。
"""
from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

PLATFORM = "<PLATFORM>"   # TODO：替换为实际平台中文名
LOGO_LETTER = "<L>"        # TODO：1-2 个汉字/字母

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app = FastAPI(title=f"{PLATFORM} 自动化服务")


# ── 依赖注入快捷方式 ──────────────────────────────────────────────────────────

def get_store(request: Request):
    return request.app.state.store


def get_orch(request: Request):
    return request.app.state.orch


def get_excel(request: Request):
    return request.app.state.excel_io


def _safe_account(d: dict) -> dict:
    """从账号 dict 剥掉敏感字段（密码、cookies、卡号密码）。"""
    safe = dict(d)
    safe.pop("password", None)
    extra = json.loads(safe.get("extra_json") or "{}")
    extra.pop("cookies", None)
    extra.pop("card_password", None)
    safe["extra_json"] = json.dumps(extra, ensure_ascii=False)

    # 组装 error_log_text（供 UI 复制日志按钮）
    err_log = extra.get("error_log_text") or ""
    if not err_log and safe.get("status_msg"):
        err_log = f"状态：{safe['status']}\n说明：{safe['status_msg']}"
    safe["error_log_text"] = err_log
    return safe


# ── 页面 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "PLATFORM": PLATFORM, "LOGO_LETTER": LOGO_LETTER},
    )


# ── 健康检查 ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"ok": True, "platform": PLATFORM, "ts": time.time()}


# ── 账号列表 ──────────────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts(
    request: Request,
    status: str = "", search: str = "",
    limit: int = 200, offset: int = 0,
    date_from: float = 0, date_to: float = 0,
):
    store = get_store(request)
    orch = get_orch(request)
    items = store.list_accounts(status=status, search=search, limit=limit, offset=offset)
    safe_items = [_safe_account(a) for a in items]
    counts = store.count_by_status()
    return {
        "items": safe_items,
        "total": counts.get("total", 0),
        "counts": counts,
        "active_workers": orch.active_workers,
        "paused": store.is_paused(),
        "concurrency_limit": store.get_concurrency_limit(),
    }


# ── 创建账号 ──────────────────────────────────────────────────────────────────

class CreateAccountBody(BaseModel):
    display_name: str = ""
    username: str
    password: str
    requirements: list[dict] = []   # A 型
    target_years: list[str] = []    # B 型
    report_mode: str = "normal"     # B 型
    extra: dict = {}


@app.post("/api/accounts", status_code=201)
async def create_account(body: CreateAccountBody, request: Request):
    store = get_store(request)
    if store.get_account_by_username(body.username):
        raise HTTPException(400, detail=f"账号 {body.username} 已存在")
    extra = dict(body.extra)
    if body.report_mode and body.report_mode != "normal":
        extra["report_mode"] = body.report_mode
    acc_id = store.create_account(
        display_name=body.display_name or body.username,
        username=body.username,
        password=body.password,
        requirements_json=json.dumps(body.requirements, ensure_ascii=False),
        target_years_json=json.dumps(body.target_years, ensure_ascii=False),
        extra_json=json.dumps(extra, ensure_ascii=False),
    )
    return {"id": acc_id}


# ── 导入 Excel ────────────────────────────────────────────────────────────────

@app.post("/api/accounts/upload")
async def upload_accounts(request: Request, file: UploadFile = File(...)):
    store = get_store(request)
    excel_io = get_excel(request)
    data = await file.read()

    # 通过 site_profile 判断 A/B 型（从 store 读取或在 app.state 上配置）
    site_profile = getattr(request.app.state, "site_profile", "A")
    result = excel_io.parse_import_xlsx(data, site_profile=site_profile)

    added = skipped = failed = 0
    errors = list(result.errors)
    for row in result.rows:
        if store.get_account_by_username(row.username):
            skipped += 1
            continue
        try:
            store.create_account(
                display_name=row.display_name,
                username=row.username,
                password=row.password,
                requirements_json=json.dumps(row.requirements, ensure_ascii=False),
                target_years_json=json.dumps(row.target_years, ensure_ascii=False),
                extra_json=json.dumps(row.extra, ensure_ascii=False),
            )
            added += 1
        except Exception as exc:
            failed += 1
            errors.append(f"账号 {row.username} 导入失败：{exc}")

    return {"added": added, "skipped": skipped, "failed": failed,
            "errors": errors if errors else None}


# ── 账号详情 ──────────────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int, request: Request):
    store = get_store(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    safe = _safe_account(acc)
    safe["runs"] = store.get_runs(account_id, limit=30)
    # [OPTIONAL:申请学分]
    # safe["apply_tasks"] = store.list_apply_tasks(account_id)
    # [END OPTIONAL:申请学分]
    return safe


# ── 编辑账号（含编辑重学）────────────────────────────────────────────────────

class PatchAccountBody(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None
    requirements: Optional[list[dict]] = None
    target_years: Optional[list[str]] = None
    report_mode: Optional[str] = None
    extra: Optional[dict] = None
    requeue: bool = False


@app.patch("/api/accounts/{account_id}")
async def patch_account(account_id: int, body: PatchAccountBody, request: Request):
    store = get_store(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")

    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.password:
        updates["password"] = body.password
    if body.requirements is not None:
        updates["requirements_json"] = json.dumps(body.requirements, ensure_ascii=False)
    if body.target_years is not None:
        updates["target_years_json"] = json.dumps(body.target_years, ensure_ascii=False)

    # 合并 extra
    if body.extra or body.report_mode:
        cur_extra = json.loads(acc.get("extra_json") or "{}")
        if body.extra:
            cur_extra.update(body.extra)
        if body.report_mode is not None:
            cur_extra["report_mode"] = body.report_mode
        updates["extra_json"] = json.dumps(cur_extra, ensure_ascii=False)

    if updates:
        store.update_account(account_id, **updates)

    if body.requeue:
        store.requeue_account(account_id)

    return {"ok": True}


# ── 删除账号 ──────────────────────────────────────────────────────────────────

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int, request: Request):
    store = get_store(request)
    if not store.get_account(account_id):
        raise HTTPException(404, detail="账号不存在")
    store.delete_account(account_id)
    return {"ok": True}


# ── 重学 ──────────────────────────────────────────────────────────────────────

@app.post("/api/accounts/{account_id}/requeue")
async def requeue_account(account_id: int, request: Request):
    store = get_store(request)
    if not store.get_account(account_id):
        raise HTTPException(404, detail="账号不存在")
    store.requeue_account(account_id)
    return {"ok": True}


# ── 调度器控制 ────────────────────────────────────────────────────────────────

class LimitBody(BaseModel):
    limit: int


@app.post("/api/scheduler/limit")
async def set_limit(body: LimitBody, request: Request):
    store = get_store(request)
    store.set_concurrency_limit(body.limit)
    return {"ok": True, "limit": store.get_concurrency_limit()}


@app.post("/api/scheduler/pause")
async def pause_scheduler(request: Request):
    get_store(request).set_paused(True)
    return {"ok": True, "paused": True}


@app.post("/api/scheduler/resume")
async def resume_scheduler(request: Request):
    get_store(request).set_paused(False)
    return {"ok": True, "paused": False}


# ── Excel 下载 ────────────────────────────────────────────────────────────────

@app.get("/api/template")
async def download_template(request: Request):
    excel_io = get_excel(request)
    site_profile = getattr(request.app.state, "site_profile", "A")
    data = excel_io.build_template_xlsx()
    filename = f"{PLATFORM}账号模板.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_encode(filename)}"},
    )


@app.get("/api/export")
async def export_accounts(request: Request):
    store = get_store(request)
    excel_io = get_excel(request)
    site_profile = getattr(request.app.state, "site_profile", "A")
    accounts = store.list_accounts(limit=10000)
    # 加入最近运行结果
    for acc in accounts:
        runs = store.get_runs(acc["id"], limit=1)
        acc["last_run_result"] = runs[0]["result"] if runs else ""
        extra = json.loads(acc.get("extra_json") or "{}")
        acc["error_log_text"] = extra.get("error_log_text", "")
    data = excel_io.build_export_xlsx(accounts, site_profile=site_profile)
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{PLATFORM}账号导出_{now_str}.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_encode(filename)}"},
    )


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
