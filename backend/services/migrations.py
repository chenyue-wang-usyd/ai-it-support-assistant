"""Additive V2 upgrade. Existing V1 table columns and row values are never rewritten."""

from sqlalchemy import select

from backend.database import Base
from backend.models import Ticket, TicketSLA
from backend.services.activity import backfill_legacy_events
from backend.services.sla import start_sla


def upgrade_database(engine, sessions):
    Base.metadata.create_all(engine)
    with sessions() as session:
        missing = select(Ticket).where(
            ~select(TicketSLA.ticket_id).where(TicketSLA.ticket_id == Ticket.id).exists()
        )
        for ticket in session.scalars(missing):
            start_sla(session, ticket, legacy=True)
        backfill_legacy_events(session)
