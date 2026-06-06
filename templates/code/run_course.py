"""
单账号课程运行入口（A 型）。复制到项目根目录 run_course.py。
替换 <PKG> 为工具包名（如 shuangwei）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from <PKG> import get_session_manager


def main() -> int:
    p = argparse.ArgumentParser(description="单账号课程端到端运行")
    p.add_argument("--cookies", help="已登录 cookies JSON 文件")
    p.add_argument("--account", help="账号 JSON（含 username/password）")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--project-id", required=True, help="课程/项目 ID")
    p.add_argument(
        "--probe-progress", action="store_true",
        help="60 秒进度增量验证（整课跑通前的门禁，不与完整运行同跑）",
    )
    p.add_argument("--probe-seconds", type=int, default=60, help="探针墙钟时长，默认 60")
    p.add_argument("--apply-credit", action="store_true", help="学习完成后申请学分（站点支持时）")
    p.add_argument("--user-id", default="default")
    p.add_argument("--output-cookies", default="data/cookies.json")
    args = p.parse_args()

    mgr = get_session_manager()
    username = password = ""

    if args.cookies:
        cookies_path = Path(args.cookies)
        cookies = json.loads(cookies_path.read_text(encoding="utf-8"))
        mgr.get_client(args.user_id).load_cookies(cookies)
    elif args.account:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]
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
            probe = lambda: mgr.get_course_service(args.user_id).list_subjects()  # noqa: E731
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

    runner = mgr.get_course_runner(args.user_id)
    if args.probe_progress:
        result = runner.probe_progress(args.project_id, probe_seconds=args.probe_seconds)
        payload = {k: (v if k != "logs" else [log.__dict__ for log in v]) for k, v in result.__dict__.items()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if result.ok else 1

    result = runner.run(args.project_id, apply_credit=args.apply_credit)
    payload = {
        "project_id": result.project_id,
        "final_state": result.final_state,
        "joined": result.joined,
        "watched": result.watched,
        "exam_passed": result.exam_passed,
        "credit_applied": result.credit_applied,
        "error": result.error,
        "logs": [log.__dict__ for log in result.logs],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.final_state != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
