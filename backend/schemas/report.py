from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReportSection(BaseModel):
    signal_type: Literal["growth_curve", "chapter_heatmap", "gap_task", "silence_risk"]
    summary: str
    data: dict


class AdaptationReport(BaseModel):
    report_id: str
    newcomer_id: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    sections: list[ReportSection]
