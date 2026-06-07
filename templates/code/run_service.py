"""
服务启动入口。复制到项目根目录 run_service.py。
替换 <SVC> 为服务包名（如 sww_service）；<PKG> 为工具包名（如 shuangwei）。
"""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser
import uvicorn
from pathlib import Path

from <SVC>.runtime import (
    SingleInstanceLock, find_available_port, project_root,
    open_existing_ui, write_endpoint_meta, clear_endpoint_meta,
)
from <SVC>.persistence.store import Store
from <SVC>.orchestrator import Orchestrator
from <SVC>.worker import AccountWorker          # 继承自 worker_base.AccountWorkerBase
from <SVC>.web.app import app
from <SVC>.web import excel_io

# [OPTIONAL:申请学分]
# from <SVC>.apply_worker import ApplyWorker
# [END OPTIONAL:申请学分]

DEFAULT_PORT = 17865
SITE_PROFILE = "A"   # TODO: "A" 或 "B"
HAS_CREDIT_APPLY = False  # TODO: 站点有申请学分流程时 True
HAS_RECHARGE = False      # TODO: 站点有购卡/充值时 True


def main():
    p = argparse.ArgumentParser(description="启动自动化服务")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    root = project_root()
    svc_dir = root / ".run" / "service"
    svc_dir.mkdir(parents=True, exist_ok=True)
    lock_path     = svc_dir / "service.lock"
    endpoint_path = svc_dir / "endpoint.json"

    # ── 单实例检查 ──────────────────────────────────────────────────────────
    lock = SingleInstanceLock(lock_path)
    if not lock.try_acquire():
        open_existing_ui(endpoint_path, no_browser=args.no_browser)
        return 0

    # ── 初始化 store / orchestrator ─────────────────────────────────────────
    db_path = root / "data" / "service.db"
    store   = Store(db_path)
    store.ensure_scheduler_defaults()
    store.startup_recovery()

    # [OPTIONAL:申请学分]
    # apply_worker = ApplyWorker(store, session_manager=None)  # TODO: 传入 session_manager
    apply_worker = None
    # [END OPTIONAL:申请学分]

    def worker_factory(account, cancel_event=None):
        return AccountWorker(
            account,
            store=store,
            session_manager=None,  # TODO: 传入真实 sm
            site_profile=SITE_PROFILE,
            cancel_event=cancel_event,
            has_credit_apply=HAS_CREDIT_APPLY,
        )

    orch = Orchestrator(store, worker_factory=worker_factory, apply_worker=apply_worker)
    orch.start()

    # ── 注入到 FastAPI app.state ─────────────────────────────────────────────
    app.state.store            = store
    app.state.orch             = orch
    app.state.excel_io         = excel_io
    app.state.site_profile     = SITE_PROFILE
    app.state.has_credit_apply = HAS_CREDIT_APPLY
    app.state.has_recharge     = HAS_RECHARGE
    app.state.recharge_handler = None  # TODO: callable(acc_dict, card_no, card_pwd) -> dict

    # ── 端口 & 元数据 ─────────────────────────────────────────────────────────
    port = find_available_port(args.host, args.port)
    url  = f"http://{args.host}:{port}"
    write_endpoint_meta(endpoint_path, args.host, port)

    try:
        if not args.no_browser:
            def _open():
                time.sleep(1.5)
                webbrowser.open(url)
            threading.Thread(target=_open, daemon=True).start()
        uvicorn.run(app, host=args.host, port=port, log_level="info")
    finally:
        orch.stop()
        clear_endpoint_meta(endpoint_path)
        lock.release()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import sys
        import traceback
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("启动失败，按 Enter 退出…")
        raise
