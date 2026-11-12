from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import (
    DiagnosisRun,
    KnowledgeBaseArticle,
    Ticket,
    TicketEvent,
    TicketSLA,
    TroubleshootingFeedback,
    utc_now,
)
from backend.schemas import (
    ApplyDiagnosis,
    Article,
    Category,
    DiagnoseRequest,
    Diagnosis,
    DiagnosisPreview,
    DuplicateMatch,
    EventRead,
    FeedbackCreate,
    FeedbackRead,
    FollowupRequest,
    Priority,
    SLARead,
    SLATicket,
    Stats,
    Status,
    SupportNote,
    TicketCreate,
    TicketRead,
    TicketUpdate,
)
from backend.services.activity import add_event
from backend.services.diagnosis import diagnose
from backend.services.duplicates import find_duplicates
from backend.services.knowledge import search_articles
from backend.services.sla import sla_snapshot, sla_statistics, start_sla

router = APIRouter()
DB = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health(request: Request, db: DB):
    db.execute(select(1))
    return {
        "status": "ok",
        "ai_configured": bool(request.app.state.settings.openai_api_key.get_secret_value().strip()),
    }


@router.post("/diagnose", response_model=DiagnosisPreview)
def preview(payload: DiagnoseRequest, request: Request, db: DB):
    result = diagnose(db, request.app.state.settings, payload)
    run = DiagnosisRun(
        request_data=payload.model_dump(mode="json"), result=result.model_dump(mode="json")
    )
    db.add(run)
    db.commit()
    return {**result.model_dump(), "diagnosis_id": run.id}


@router.post("/tickets", response_model=TicketRead, status_code=201)
def create_ticket(payload: TicketCreate, request: Request, response: Response, db: DB):
    issue = DiagnoseRequest(**payload.model_dump(exclude={"diagnosis_id"}))
    if payload.diagnosis_id:
        run = db.get(DiagnosisRun, str(payload.diagnosis_id))
        if run is None:
            raise HTTPException(404, "Diagnosis not found. Analyze the issue again.")
        if run.request_data != issue.model_dump(mode="json"):
            raise HTTPException(409, "Issue changed since analysis. Analyze it again.")
        result = Diagnosis.model_validate(run.result)
    else:
        result = diagnose(db, request.app.state.settings, issue)
    matches = find_duplicates(db, issue, request.app.state.settings.duplicate_similarity_threshold)
    response.headers["X-Possible-Duplicate-Count"] = str(len(matches))
    now = request.app.state.clock()
    ticket = Ticket(
        title=issue.title,
        description=issue.description,
        category=result.analysis.category.value,
        priority=result.analysis.priority.value,
        diagnosis=result.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    start_sla(db, ticket)
    add_event(db, ticket.id, "Ticket Created", new="Open", at=now)
    add_event(
        db,
        ticket.id,
        "AI Diagnosis Generated"
        if result.mode == "AI-Powered Analysis"
        else "Rule-based Diagnosis Generated",
        new=result.mode,
        at=run.created_at if payload.diagnosis_id else now,
    )
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/tickets/duplicates", response_model=list[DuplicateMatch])
def duplicate_candidates(payload: DiagnoseRequest, request: Request, db: DB):
    return find_duplicates(db, payload, request.app.state.settings.duplicate_similarity_threshold)


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(
    db: DB,
    status: Status | None = None,
    category: Category | None = None,
    priority: Priority | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    statement = select(Ticket)
    for column, value in (
        (Ticket.status, status),
        (Ticket.category, category),
        (Ticket.priority, priority),
    ):
        if value is not None:
            statement = statement.where(column == value.value)
    return list(
        db.scalars(
            statement.order_by(Ticket.created_at.desc(), Ticket.id).offset(offset).limit(limit)
        )
    )


def find_ticket(db, ticket_id):
    ticket = db.get(Ticket, str(ticket_id))
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    return ticket


@router.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: UUID, db: DB):
    return find_ticket(db, ticket_id)


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket_id: UUID, payload: TicketUpdate, request: Request, db: DB):
    ticket = find_ticket(db, ticket_id)
    previous = ticket.status
    if previous == payload.status.value:
        return ticket
    ticket.status = payload.status.value
    ticket.updated_at = request.app.state.clock()
    sla = db.get(TicketSLA, ticket.id)
    sla.resolved_at = ticket.updated_at if ticket.status == "Resolved" else None
    sla.resolution_estimated = False
    event_type = "Status Changed"
    if ticket.status == "Resolved":
        event_type = "Ticket Resolved"
    elif previous == "Resolved":
        event_type = "Ticket Reopened"
    add_event(db, ticket.id, event_type, previous=previous, new=ticket.status, at=ticket.updated_at)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/tickets/{ticket_id}/sla", response_model=SLARead)
def ticket_sla(ticket_id: UUID, request: Request, db: DB):
    ticket = find_ticket(db, ticket_id)
    return sla_snapshot(
        ticket,
        db.get(TicketSLA, ticket.id),
        request.app.state.clock(),
        request.app.state.settings.sla_warning_hours,
    )


@router.get("/sla/tickets", response_model=list[SLATicket])
def sla_tickets(
    request: Request,
    db: DB,
    state: str = Query("All", pattern="^(All|On Track|Due Soon|Breached|Resolved)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    now = request.app.state.clock()
    warning = request.app.state.settings.sla_warning_hours
    statement = select(Ticket, TicketSLA).join(TicketSLA).order_by(TicketSLA.due_at, Ticket.id)
    rows = []
    for ticket, sla in db.execute(statement):
        snapshot = sla_snapshot(ticket, sla, now, warning)
        if state == "All" or snapshot.state == state:
            rows.append(
                SLATicket(
                    **snapshot.model_dump(),
                    title=ticket.title,
                    priority=ticket.priority,
                    status=ticket.status,
                )
            )
    return rows[offset : offset + limit]


@router.get("/tickets/{ticket_id}/events", response_model=list[EventRead])
def ticket_events(ticket_id: UUID, db: DB):
    find_ticket(db, ticket_id)
    return list(
        db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == str(ticket_id))
            .order_by(TicketEvent.timestamp, TicketEvent.id)
        )
    )


@router.post("/tickets/{ticket_id}/notes", response_model=EventRead, status_code=201)
def support_note(ticket_id: UUID, payload: SupportNote, request: Request, db: DB):
    ticket = find_ticket(db, ticket_id)
    now = request.app.state.clock()
    event = add_event(db, ticket.id, "Support Note Added", note=payload.note, at=now)
    ticket.updated_at = now
    db.commit()
    db.refresh(event)
    return event


def find_diagnosis(db, diagnosis_id):
    run = db.get(DiagnosisRun, str(diagnosis_id))
    if run is None:
        raise HTTPException(404, "Diagnosis not found.")
    return run


@router.post("/diagnose/{diagnosis_id}/feedback", response_model=FeedbackRead, status_code=201)
def feedback(diagnosis_id: UUID, payload: FeedbackCreate, db: DB):
    find_diagnosis(db, diagnosis_id)
    if payload.ticket_id:
        find_ticket(db, payload.ticket_id)
        add_event(
            db,
            str(payload.ticket_id),
            "Troubleshooting Feedback",
            new=payload.outcome,
            note=payload.note,
        )
    item = TroubleshootingFeedback(
        diagnosis_id=str(diagnosis_id),
        outcome=payload.outcome,
        note=payload.note,
        ticket_id=str(payload.ticket_id) if payload.ticket_id else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/diagnose/{diagnosis_id}/feedback", response_model=list[FeedbackRead])
def feedback_history(diagnosis_id: UUID, db: DB):
    find_diagnosis(db, diagnosis_id)
    return list(
        db.scalars(
            select(TroubleshootingFeedback)
            .where(TroubleshootingFeedback.diagnosis_id == str(diagnosis_id))
            .order_by(TroubleshootingFeedback.created_at, TroubleshootingFeedback.id)
        )
    )


@router.post("/diagnose/{diagnosis_id}/follow-up", response_model=DiagnosisPreview)
def follow_up(diagnosis_id: UUID, payload: FollowupRequest, request: Request, db: DB):
    original = find_diagnosis(db, diagnosis_id)
    if payload.ticket_id:
        find_ticket(db, payload.ticket_id)
    description = (
        original.request_data["description"] + "\n\nAdditional details: " + payload.details
    )
    if len(description) > 6000:
        raise HTTPException(422, "Combined issue exceeds 6,000 characters. Start a new analysis.")
    issue = DiagnoseRequest(**{**original.request_data, "description": description})
    result = diagnose(db, request.app.state.settings, issue)
    run = DiagnosisRun(
        request_data=issue.model_dump(mode="json"), result=result.model_dump(mode="json")
    )
    db.add(run)
    db.flush()
    db.add(
        TroubleshootingFeedback(
            diagnosis_id=str(diagnosis_id),
            outcome="still_having_issues",
            note=payload.details,
            ticket_id=str(payload.ticket_id) if payload.ticket_id else None,
            followup_diagnosis_id=run.id,
        )
    )
    db.commit()
    return {**result.model_dump(), "diagnosis_id": run.id}


@router.post("/tickets/{ticket_id}/diagnosis", response_model=TicketRead)
def apply_diagnosis(ticket_id: UUID, payload: ApplyDiagnosis, db: DB):
    ticket = find_ticket(db, ticket_id)
    run = find_diagnosis(db, payload.diagnosis_id)
    if run.request_data["title"] != ticket.title:
        raise HTTPException(409, "Diagnosis title must match the selected ticket.")
    result = Diagnosis.model_validate(run.result)
    add_event(
        db,
        ticket.id,
        "Diagnosis Applied",
        previous=ticket.diagnosis["mode"],
        new=result.mode,
        note=f"User applied diagnosis {run.id}.",
    )
    ticket.diagnosis = result.model_dump(mode="json")
    ticket.updated_at = utc_now()
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/knowledge-base", response_model=list[Article])
def knowledge_base(db: DB, q: str = Query("", max_length=1000), category: Category | None = None):
    if q.strip():
        articles = search_articles(db, q, limit=50)
        return [a for a in articles if category is None or a.category == category.value]
    statement = select(KnowledgeBaseArticle).order_by(KnowledgeBaseArticle.id)
    if category:
        statement = statement.where(KnowledgeBaseArticle.category == category.value)
    return list(db.scalars(statement))


@router.get("/stats", response_model=Stats)
def stats(request: Request, db: DB):
    def counts(column, values):
        grouped = dict(db.execute(select(column, func.count()).group_by(column)).all())
        return {value.value: grouped.get(value.value, 0) for value in values}

    return Stats(
        total_tickets=db.scalar(select(func.count()).select_from(Ticket)),
        by_status=counts(Ticket.status, Status),
        by_category=counts(Ticket.category, Category),
        by_priority=counts(Ticket.priority, Priority),
        **sla_statistics(
            db, request.app.state.clock(), request.app.state.settings.sla_warning_hours
        ),
    )
