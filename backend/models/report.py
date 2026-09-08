"""AdaptationReport/ReportSection 테이블 (담당: 조장) — schemas/report.py와 1:1 (guidelines 5-3-1)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AdaptationReportORM(Base):
    __tablename__ = "adaptation_reports"

    report_id = Column(String(36), primary_key=True, default=_uuid)
    newcomer_id = Column(String(36), index=True, nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    generated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    sections = relationship(
        "ReportSectionORM", back_populates="report", cascade="all, delete-orphan"
    )


class ReportSectionORM(Base):
    __tablename__ = "report_sections"

    section_id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("adaptation_reports.report_id"), nullable=False)
    signal_type = Column(String(30), nullable=False)  # growth_curve/chapter_heatmap/gap_task/silence_risk
    summary = Column(String(2000), nullable=False)
    data = Column(JSON, nullable=False)

    report = relationship("AdaptationReportORM", back_populates="sections")
