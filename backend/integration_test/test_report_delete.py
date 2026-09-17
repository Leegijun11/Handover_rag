# -*- coding: utf-8 -*-
"""DELETE /report/{report_id} — 신설 엔드포인트(조장 승인 9/17)의 권한과 동작 검증.

리포트 생성은 OpenAI를 부르므로 여기서는 부르지 않는다. 검증하려는 건 "리포트가 잘
만들어지는가"가 아니라 "지울 수 있는 사람만 지우는가"라서, 리포트 행은 DB에 직접 넣는다.
"""

from datetime import datetime, timedelta, timezone

from helpers import auth_headers, create_document_directly, register_and_login

from core.database import SessionLocal
from models.report import AdaptationReportORM, ReportSectionORM


def _now() -> datetime:
    """서버가 DB에 쓰는 형태 — tz 정보 없는 UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assign(client, mentor, newcomer, document_id):
    resp = client.post(
        "/assignment",
        json={"mentor_id": mentor["user_id"], "newcomer_id": newcomer["user_id"], "document_id": document_id},
        headers=auth_headers(mentor["token"]),
    )
    assert resp.status_code == 201, resp.text


def _insert_report(newcomer_id: str) -> str:
    db = SessionLocal()
    try:
        report = AdaptationReportORM(
            newcomer_id=newcomer_id,
            period_start=_now() - timedelta(days=7),
            period_end=_now(),
        )
        db.add(report)
        db.flush()
        db.add(
            ReportSectionORM(
                report_id=report.report_id,
                signal_type="growth_curve",
                summary="테스트용 요약",
                data={"counts": {}, "total": 0},
            )
        )
        db.commit()
        return report.report_id
    finally:
        db.close()


def _report_exists(report_id: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(AdaptationReportORM).filter_by(report_id=report_id).first() is not None
    finally:
        db.close()


def test_mentor_can_delete_own_newcomers_report(client):
    mentor = register_and_login(client, "사수삭제", "mentor")
    newcomer = register_and_login(client, "신입삭제", "newcomer")
    _assign(client, mentor, newcomer, create_document_directly(mentor["user_id"]))
    report_id = _insert_report(newcomer["user_id"])

    resp = client.delete(f"/report/{report_id}", headers=auth_headers(mentor["token"]))

    assert resp.status_code == 204, resp.text
    assert not _report_exists(report_id)


def test_other_mentor_cannot_delete_report(client):
    mentor_a = register_and_login(client, "사수삭제A", "mentor")
    mentor_b = register_and_login(client, "사수삭제B", "mentor")
    newcomer = register_and_login(client, "신입삭제B", "newcomer")
    _assign(client, mentor_a, newcomer, create_document_directly(mentor_a["user_id"]))
    report_id = _insert_report(newcomer["user_id"])

    resp = client.delete(f"/report/{report_id}", headers=auth_headers(mentor_b["token"]))

    assert resp.status_code == 403
    assert _report_exists(report_id), "권한 없는 요청인데 실제로 지워졌다"


def test_newcomer_cannot_delete_report(client):
    mentor = register_and_login(client, "사수삭제C", "mentor")
    newcomer = register_and_login(client, "신입삭제C", "newcomer")
    _assign(client, mentor, newcomer, create_document_directly(mentor["user_id"]))
    report_id = _insert_report(newcomer["user_id"])

    resp = client.delete(f"/report/{report_id}", headers=auth_headers(newcomer["token"]))

    assert resp.status_code == 403
    assert _report_exists(report_id)


def test_deleting_missing_report_returns_404(client):
    mentor = register_and_login(client, "사수삭제D", "mentor")

    resp = client.delete("/report/없는-리포트-id", headers=auth_headers(mentor["token"]))

    assert resp.status_code == 404
