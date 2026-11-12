import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select

from backend.models import Ticket
from backend.schemas import DuplicateMatch

# These common platform words alone do not identify the same incident.
GENERIC = set(ENGLISH_STOP_WORDS) | {
    "wi",
    "fi",
    "wifi",
    "windows",
    "laptop",
    "computer",
    "device",
    "issue",
    "problem",
    "help",
    "working",
    "work",
    "network",
    "internet",
    "connect",
    "cannot",
    "error",
}


def distinctive_terms(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - GENERIC


def find_duplicates(session, issue, threshold=0.78, limit=5):
    tickets = list(
        session.scalars(
            select(Ticket).where(Ticket.status != "Resolved").order_by(Ticket.created_at, Ticket.id)
        )
    )
    if not tickets:
        return []
    query = f"{issue.title} {issue.description}"
    documents = [f"{t.title} {t.description}" for t in tickets]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    try:
        matrix = vectorizer.fit_transform(documents + [query])
    except ValueError:  # No vocabulary: nothing meaningful to compare.
        return []
    scores = cosine_similarity(matrix[-1], matrix[:-1])[0]
    query_terms = distinctive_terms(query)
    matches = []
    for ticket, document, score in zip(tickets, documents, scores):
        shared = sorted(query_terms & distinctive_terms(document))
        # A high score plus at least two specific shared terms is only a candidate, not a verdict.
        if score >= threshold and len(shared) >= 2:
            matches.append(
                DuplicateMatch(
                    ticket_id=ticket.id,
                    title=ticket.title,
                    status=ticket.status,
                    similarity=round(float(score), 4),
                    shared_terms=shared[:12],
                )
            )
    return sorted(matches, key=lambda match: (-match.similarity, match.ticket_id))[:limit]
