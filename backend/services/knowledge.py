import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select

from backend.config import ROOT
from backend.models import KnowledgeBaseArticle
from backend.schemas import Article


def seed_knowledge_base(session):
    """Insert missing IDs only, preserving any existing local article edits."""
    records = json.loads((ROOT / "knowledge_base/seed_data.json").read_text(encoding="utf-8"))
    for record in records:
        article = Article.model_validate(record)
        if session.get(KnowledgeBaseArticle, article.id) is None:
            session.add(KnowledgeBaseArticle(**article.model_dump(mode="json")))
    session.commit()


def search_articles(session, query: str, limit: int = 3):
    articles = list(session.scalars(select(KnowledgeBaseArticle).order_by(KnowledgeBaseArticle.id)))
    if not articles or not query.strip():
        return []
    documents = [
        f"{a.title} {a.category} {a.symptoms} {' '.join(a.solution_steps)}" for a in articles
    ]
    # Fit on trusted KB text only. Unknown query words do not alter the corpus weights.
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(documents)
    scores = cosine_similarity(vectorizer.transform([query]), matrix)[0]
    ranked = sorted(range(len(articles)), key=lambda i: (-scores[i], articles[i].id))
    return [articles[i] for i in ranked[:limit] if scores[i] >= 0.04]
