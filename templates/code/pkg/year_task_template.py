"""B 型单年度公需任务流水线。

复制到 <pkg>/year_task.py，按站点调整公需课过滤字段、购课逻辑。
关键：_resolve_year_completion — publicNum 滞后时结合证书 auditStatus 判定完成（见 progress-sync.md §年度完成判定）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .certificate import CertificateService
from .course import CourseService
from .exam import ExamService
from .study import StudyService

PhaseCallback = Callable[[str, str], None]
HourStartCallback = Callable[[str, str, dict[str, str]], None]
HourCompleteCallback = Callable[[str, str, dict[str, str], Any], None]
ProgressTickCallback = Callable[[str, str, dict[str, str], int], None]


@dataclass
class YearTaskResult:
    ok: bool
    year: str
    message: str
    phase: str = "done"
    skipped: bool = False
    certificate: dict[str, Any] | None = None
    study_results: list[Any] = field(default_factory=list)
    exam_results: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "year": self.year,
            "message": self.message,
            "phase": self.phase,
            "skipped": self.skipped,
            "certificate": self.certificate,
            "study_results": [getattr(x, "__dict__", x) for x in self.study_results],
            "exam_results": self.exam_results,
        }


def _emit(cb: PhaseCallback | None, phase: str, msg: str) -> None:
    if cb:
        cb(phase, msg)


def probe_year_progress(
    course_svc: CourseService,
    study_svc: StudyService,
    year: str | int,
    *,
    probe_seconds: int = 60,
    min_delta: float = 1,
    report_mode: str = "normal",
):
    """年度任务进度门禁：对当年第一门未完成课程做 ~60s 增量探测。"""
    from .study import ProgressProbeResult

    year_str = str(year)
  # TODO: filter public courses per site (natureType / natureTypeName)
    enrolled = course_svc.list_year_enrolled(year_str)
    for row in enrolled:
        if course_svc.course_is_finished(row):
            continue
        course_id = str(row["id"])
        probe = study_svc.probe_progress(
            course_id,
            probe_seconds=probe_seconds,
            min_delta=min_delta,
            report_mode=report_mode,
        )
        probe.logs.append({
            "stage": "year_probe",
            "ok": probe.ok,
            "message": f"{year_str} 年首门待学课 {row.get('courseName', course_id)}",
        })
        return probe
    empty = ProgressProbeResult(ok=True, course_id="", probe_seconds=probe_seconds)
    empty.logs.append({
        "stage": "year_probe",
        "ok": True,
        "message": f"{year_str} 年无待学课程",
    })
    return empty


def _audit_status(cert_row: dict[str, Any] | None) -> int:
    if not cert_row:
        return -1
    try:
        return int(cert_row.get("auditStatus") or -1)  # TODO: site audit field
    except (TypeError, ValueError):
        return -1


def _all_enrolled_finished(enrolled: list[dict[str, Any]], course_svc: CourseService) -> bool:
    return bool(enrolled) and all(course_svc.course_is_finished(row) for row in enrolled)


def _resolve_year_completion(
    course_svc: CourseService,
    cert_svc: CertificateService,
    year_str: str,
    enrolled: list[dict[str, Any]],
    *,
    target_public_hours: int,
    cert_row: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None, int]:
    """
    年度是否算完成。勿仅依赖 annual_completion.publicNum — 部分站点滞后为 0。
    返回 (ok, message, cert_row, public_num)。
    """
    if cert_row is None:
        cert_row = cert_svc.get_year_certificate(year_str)

    audit = _audit_status(cert_row)
    if audit == 1:
        return True, f"{year_str} 年证书已通过", cert_row, target_public_hours

    if cert_row and audit >= 0 and _all_enrolled_finished(enrolled, course_svc):
        label = cert_svc.audit_status_label(audit)
        return True, f"{year_str} 年课程已完成，证书{label}", cert_row, target_public_hours

    if cert_svc.is_year_public_completed(year_str, target_public_hours):
        return True, f"{year_str} 年公需学时已达标", cert_row, target_public_hours

    annual = course_svc.annual_completion(year_str)  # TODO: earned hours field name
    public_num = int(annual.get("publicNum") or 0)
    if public_num >= target_public_hours:
        return True, "年度任务完成", cert_row, public_num

    return False, f"公需学时未达标（publicNum={public_num}）", cert_row, public_num


def run_year_task(
    course_svc: CourseService,
    study_svc: StudyService,
    cert_svc: CertificateService,
    exam_svc: ExamService | None,
    year: str | int,
    *,
    report_mode: str = "normal",
    ensure_cart: bool = True,
    target_public_hours: int = 30,
    on_phase: PhaseCallback | None = None,
    on_hour_start: HourStartCallback | None = None,
    on_hour_complete: HourCompleteCallback | None = None,
    on_progress_tick: ProgressTickCallback | None = None,
) -> YearTaskResult:
    year_str = str(year)
    _emit(on_phase, "cert_check", f"检查 {year_str} 年证书状态")
    cert_row = cert_svc.get_year_certificate(year_str)

    enrolled_all = course_svc.list_year_enrolled(year_str)
    enrolled = enrolled_all  # TODO: filter 公需课 if needed
    unfinished = [row for row in enrolled if not course_svc.course_is_finished(row)]

    if not unfinished:
        ok, msg, cert_row, _ = _resolve_year_completion(
            course_svc, cert_svc, year_str, enrolled,
            target_public_hours=target_public_hours, cert_row=cert_row,
        )
        if ok:
            return YearTaskResult(
                ok=True, year=year_str, message=msg, phase="done",
                skipped=True, certificate=cert_row,
            )

    if ensure_cart:
        _emit(on_phase, "purchase_check", f"规划 {year_str} 年公需科目购物车")
        try:
            course_svc.ensure_public_courses_in_cart(year_str, target_hours=target_public_hours)
        except RuntimeError as exc:
            return YearTaskResult(ok=False, year=year_str, message=str(exc), phase="purchase_check")

    _emit(on_phase, "catalog", f"加载 {year_str} 年已购课程")
    enrolled = course_svc.list_year_enrolled(year_str)

    study_results: list[Any] = []
    for idx, row in enumerate(enrolled, start=1):
        course_id = str(row["id"])
        title = str(row.get("courseName") or course_id)
        if course_svc.course_is_finished(row):
            _emit(on_phase, "video_play", f"跳过已完成：{title}")
            continue
        _emit(on_phase, "video_play", f"学习 {idx}/{len(enrolled)}：{title}")
        results = study_svc.study_course(
            course_id, course_title=title, report_mode=report_mode,
            on_hour_start=on_hour_start, on_hour_complete=on_hour_complete,
            on_progress_tick=on_progress_tick,
        )
        study_results.extend(results)
        if results and not results[-1].ok:
            return YearTaskResult(
                ok=False, year=year_str, message=results[-1].message,
                phase="video_play", certificate=cert_row, study_results=study_results,
            )

    exam_results: list[Any] = []
    if exam_svc is not None:
        for row in enrolled:
            if not course_svc.needs_exam(row):
                continue
            exam_id = str(row.get("examId") or "")
            course_id = str(row["id"])
            if not exam_id:
                continue
            _emit(on_phase, "exam_run", f"考试 {row.get('courseName')} exam_id={exam_id}")
            try:
                gate = exam_svc.check_eligibility(exam_id, course_id)
                if not gate.get("isEligible", True):
                    continue
                exam_results.append(exam_svc.start_examination(exam_id, course_id))
            except RuntimeError as exc:
                return YearTaskResult(
                    ok=False, year=year_str, message=str(exc), phase="exam_run",
                    certificate=cert_row, study_results=study_results, exam_results=exam_results,
                )

    ok, msg, cert_row, _ = _resolve_year_completion(
        course_svc, cert_svc, year_str, enrolled,
        target_public_hours=target_public_hours, cert_row=cert_row,
    )
    if not ok:
        still_unfinished = [r for r in enrolled if not course_svc.course_is_finished(r)]
        phase = "catalog" if not study_results and not still_unfinished else "video_play"
        detail = f"{year_str} 年无可学课程，{msg}" if phase == "catalog" else msg
        return YearTaskResult(
            ok=False, year=year_str, message=detail, phase=phase,
            certificate=cert_row, study_results=study_results, exam_results=exam_results,
        )

    if _audit_status(cert_row) >= 0:
        return YearTaskResult(
            ok=True, year=year_str, message=msg, phase="done",
            skipped=_audit_status(cert_row) == 1, certificate=cert_row,
            study_results=study_results, exam_results=exam_results,
        )

    _emit(on_phase, "cert_apply", f"申请 {year_str} 年公需证书")
    cert_row = cert_svc.get_year_certificate(year_str)
    if cert_row:
        course_ids = ",".join(str(r["id"]) for r in enrolled)
        apply_resp = cert_svc.apply(str(cert_row["id"]), course_ids)
        if not apply_resp.ok and "申请成功" not in apply_resp.message:
            return YearTaskResult(
                ok=False, year=year_str, message=apply_resp.message, phase="cert_apply",
                certificate=cert_row, study_results=study_results, exam_results=exam_results,
            )
        cert_row = cert_svc.get_year_certificate(year_str) or cert_row

    ok, msg, cert_row, _ = _resolve_year_completion(
        course_svc, cert_svc, year_str, enrolled,
        target_public_hours=target_public_hours, cert_row=cert_row,
    )
    return YearTaskResult(
        ok=ok, year=year_str, message=msg, phase="done",
        certificate=cert_row, study_results=study_results, exam_results=exam_results,
    )
