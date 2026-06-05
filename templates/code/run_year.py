"""
单账号年度任务运行入口（B 型）。复制到项目根目录 run_year.py。
替换 <PKG> 为工具包名。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from <PKG> import get_session_manager


def _default_years(raw: str | None) -> list[str]:
    if raw:
        return [y.strip() for y in raw.replace("，", ",").split(",") if y.strip()]
    return [str(datetime.now(tz=ZoneInfo("Asia/Shanghai")).year)]


def main() -> int:
    p = argparse.ArgumentParser(description="单账号公需年度任务运行（B 型）")
    p.add_argument("--cookies", help="已登录 cookies JSON 文件")
    p.add_argument("--account", help="账号 JSON（含 username/password）")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--years", help="目标年度，逗号分隔；默认当前自然年")
    p.add_argument("--report-mode", choices=("normal", "fast"), default="normal")
    p.add_argument("--user-id", default="default")
    p.add_argument("--output-cookies", default="data/cookies.json")
    args = p.parse_args()

    years = _default_years(args.years)
    mgr = get_session_manager()
    username = password = ""

    if args.cookies:
        cookies = json.loads(Path(args.cookies).read_text(encoding="utf-8"))
        mgr.get_client(args.user_id).load_cookies(cookies)
    elif args.account:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]
        if not args.years and cfg.get("target_years"):
            years = list(cfg["target_years"])
    elif args.username and args.password:
        username, password = args.username, args.password
    else:
        print("需要 --cookies / --account / -u+-p 之一", file=sys.stderr)
        return 2

    if username:
        client = mgr.get_client(args.user_id)
        cookies = client.export_cookies() if client.export_cookies() else None
        probe = None
        try:
            probe = lambda: mgr.get_member_service(args.user_id).get_profile()  # noqa: E731
        except Exception:
            pass
        _, cookies, _, err = mgr.ensure_session(
            args.user_id, username, password, cookies=cookies, probe=probe,
        )
        if err:
            print(f"登录失败：{err}", file=sys.stderr)
            return 1
        out = Path(args.output_cookies)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    runner = mgr.get_year_runner(args.user_id)
    results = []
    ok_all = True
    for year in years:
        r = runner.run_year(year, report_mode=args.report_mode)
        results.append({
            "year": r.year,
            "success": r.success,
            "earned_hours": r.earned_hours,
            "required_hours": r.required_hours,
            "summary": r.summary,
            "error": r.error,
            "logs": [log.__dict__ for log in r.logs],
        })
        if not r.success:
            ok_all = False

    print(json.dumps({"years": years, "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
