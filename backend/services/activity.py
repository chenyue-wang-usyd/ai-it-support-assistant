from sqlalchemy import select

from backend.models import Ticket, TicketEvent, utc_now


def add_event(session, ticket_id, event_type, *, previous=None, new=None, note=None, at=None):
    event = TicketEvent(
        ticket_id=ticket_id,
        event_type=event_type,
        previous_value=previous,
        new_value=new,
        note=note,
        timestamp=at or utc_now(),
    )
    session.add(event)
    return event


def backfill_legacy_events(session):
    """Record the migration fact, never invent unavailable pre-V2 activity."""
    missing = select(Ticket).where(
        ~select(TicketEvent.id).where(TicketEvent.ticket_id == Ticket.id).exists()
    )
    for ticket in session.scalars(missing):
        add_event(
            session,
            ticket.id,
            "Legacy Ticket Imported",
            new=ticket.status,
            note="Existing ticket preserved during V2 upgrade. Earlier activity was not recorded.",
        )
    session.commit()
