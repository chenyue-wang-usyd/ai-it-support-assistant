from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('Open', 'In Progress', 'Resolved')"),
        CheckConstraint("priority IN ('Low', 'Medium', 'High')"),
        CheckConstraint(
            "category IN ('Network / Wi-Fi','Software','Hardware',"
            "'Account / Login','Email','Other')"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), index=True)
    priority: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20), default="Open", index=True)
    diagnosis: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class KnowledgeBaseArticle(Base):
    __tablename__ = "knowledge_base_articles"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(30), index=True)
    symptoms: Mapped[str] = mapped_column(Text)
    solution_steps: Mapped[list[str]] = mapped_column(JSON)


class DiagnosisRun(Base):
    __tablename__ = "diagnosis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_data: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)


class TroubleshootingFeedback(Base):
    __tablename__ = "troubleshooting_feedback"
    __table_args__ = (CheckConstraint("outcome IN ('solved', 'still_having_issues')"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    diagnosis_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    followup_diagnosis_id: Mapped[str | None] = mapped_column(ForeignKey("diagnosis_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TicketSLA(Base):
    __tablename__ = "ticket_slas"

    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
