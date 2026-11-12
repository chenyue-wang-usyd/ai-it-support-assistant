from datetime import timedelta, timezone

from sqlalchemy import case, func, select

from backend.models import Ticket, TicketSLA
from backend.schemas import SLARead

SLA_HOURS = {"High": 4, "Medium": 24, "Low": 72}


def as_utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def start_sla(session, ticket, *, legacy=False):
    row = TicketSLA(
        ticket_id=ticket.id,
        due_at=as_utc(ticket.created_at) + timedelta(hours=SLA_HOURS[ticket.priority]),
        resolved_at=ticket.updated_at if legacy and ticket.status == "Resolved" else None,
        resolution_estimated=legacy and ticket.status == "Resolved",
    )
    session.add(row)
    return row


def sla_snapshot(ticket, row, now, warning_hours=2):
    now = as_utc(now)
    stopped = as_utc(row.resolved_at) if row.resolved_at else now
    due = as_utc(row.due_at)
    remaining = (due - stopped).total_seconds()
    state = (
        "Resolved"
        if row.resolved_at
        else (
            "Breached"
            if remaining < 0
            else ("Due Soon" if remaining <= warning_hours * 3600 else "On Track")
        )
    )
    return SLARead(
        ticket_id=ticket.id,
        due_at=due,
        resolved_at=as_utc(row.resolved_at) if row.resolved_at else None,
        resolution_estimated=row.resolution_estimated,
        state=state,
        breached=remaining < 0,
        remaining_seconds=remaining,
        elapsed_hours=max(0, (stopped - as_utc(ticket.created_at)).total_seconds() / 3600),
        as_of=now,
    )


def sla_statistics(session, now, warning_hours):
    # SQLite stores naive UTC; comparisons and aggregation stay inside the database.
    current = as_utc(now).replace(tzinfo=None)
    warning_end = current + timedelta(hours=warning_hours)
    active = TicketSLA.resolved_at.is_(None)
    measured = TicketSLA.resolved_at.is_not(None) & ~TicketSLA.resolution_estimated
    estimated = TicketSLA.resolved_at.is_not(None) & TicketSLA.resolution_estimated
    statement = select(
        func.sum(case((active & (TicketSLA.due_at < current), 1), else_=0)),
        func.sum(
            case(
                (active & (TicketSLA.due_at >= current) & (TicketSLA.due_at <= warning_end), 1),
                else_=0,
            )
        ),
        func.sum(case((TicketSLA.resolved_at > TicketSLA.due_at, 1), else_=0)),
        func.avg(
            case(
                (
                    measured,
                    (func.julianday(TicketSLA.resolved_at) - func.julianday(Ticket.created_at))
                    * 24,
                )
            )
        ),
        func.sum(case((measured, 1), else_=0)),
        func.sum(case((estimated, 1), else_=0)),
    ).join(Ticket, Ticket.id == TicketSLA.ticket_id)
    breaches, soon, resolved_breaches, average, count, estimates = session.execute(statement).one()
    return dict(
        sla_breaches=breaches or 0,
        sla_due_soon=soon or 0,
        resolved_sla_breaches=resolved_breaches or 0,
        average_resolution_hours=round(average, 4) if average is not None else None,
        measured_resolutions=count or 0,
        estimated_resolutions=estimates or 0,
    )
