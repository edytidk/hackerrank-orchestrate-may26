from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from models import Chunk, RetrievalResult, Ticket


class Retriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_features=80000,
        )
        self.matrix = self.vectorizer.fit_transform(chunk.search_text for chunk in chunks)

    def search(self, ticket: Ticket, top_k: int = 6, pool_size: int = 40) -> list[RetrievalResult]:
        query = _expand_query(ticket.query)
        query_vector = self.vectorizer.transform([query])
        scores = (self.matrix @ query_vector.T).toarray().ravel()

        if ticket.company:
            company_mask = np.array([chunk.company == ticket.company for chunk in self.chunks])
            same_company_max = float(scores[company_mask].max()) if company_mask.any() else 0.0
            if same_company_max >= 0.08:
                scores = np.where(company_mask, scores, scores * 0.25)

        candidate_indexes = np.argsort(scores)[::-1][:pool_size]
        results: list[RetrievalResult] = []
        for index in candidate_indexes:
            chunk = self.chunks[int(index)]
            lexical_score = float(scores[int(index)])
            if lexical_score <= 0:
                continue
            boost, reasons = _metadata_boost(ticket, chunk)
            final_score = lexical_score + boost
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    lexical_score=lexical_score,
                    metadata_boost=boost,
                    final_score=final_score,
                    reason=", ".join(reasons) if reasons else "lexical match",
                )
            )

        return sorted(results, key=lambda item: item.final_score, reverse=True)[:top_k]


def _expand_query(query: str) -> str:
    expansions = {
        "extra time": "time accommodation extended time assessment duration",
        "refund": "payment billing subscription refund charge dispute",
        "order id": "payment billing invoice subscription charge refund",
        "money": "payment billing subscription refund charge",
        "score": "test result report candidate assessment score",
        "recruiter": "candidate test assessment report recruiter",
        "infosec": "security questionnaire compliance trust data security",
        "forms": "security questionnaire compliance trust data security",
        "identity theft": "fraud stolen card security identity theft",
        "cash": "emergency cash card lost stolen assistance",
        "crawler": "crawl data privacy robots.txt",
        "use my data": "sensitive data model improvement privacy settings training conversations",
        "improve the models": "sensitive data model improvement privacy settings training conversations",
        "bedrock": "amazon bedrock api requests failing",
        "lti": "education lti learning management system",
        "minimum spend": "merchant surcharge minimum transaction visa rules",
        "screen share": "interview inactivity lobby screen share timeout",
        "rescheduling": "reschedule interview assessment candidate schedule",
        "reschedule": "reschedule interview assessment candidate schedule",
        "certificate": "certificate name update certification profile",
        "test active": "test active expire expiration start date end date invite candidate screen",
        "stay active": "test active expire expiration start date end date invite candidate screen",
        "variants": "test variants create variant default versions role screen",
        "variant": "test variants create variant default versions role screen",
        "apply tab": "jobs apply tab search apply quickapply application",
        "remove them": "remove user admin account team user management",
        "remove an interviewer": "remove user interviewer team admin user management",
    }
    lowered = query.lower()
    extra = [value for key, value in expansions.items() if key in lowered]
    return " ".join([query, *extra])


def _metadata_boost(ticket: Ticket, chunk: Chunk) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []
    query = ticket.query.lower()
    query_terms = set(re.findall(r"[a-z0-9]+", query))

    if ticket.company and ticket.company == chunk.company:
        boost += 0.08
        reasons.append("company match")

    title_terms = set(re.findall(r"[a-z0-9]+", chunk.title.lower()))
    if query_terms & title_terms:
        boost += min(0.08, 0.015 * len(query_terms & title_terms))
        reasons.append("title overlap")

    product_terms = set(chunk.product_area.replace("_", " ").split())
    if query_terms & product_terms:
        boost += 0.04
        reasons.append("product area overlap")

    if any(term in query for term in ("delete", "remove")) and any(
        term in chunk.search_text.lower() for term in ("delete", "remove")
    ):
        boost += 0.04
        reasons.append("action overlap")

    normalized_title = chunk.title.lower()
    if "reschedul" in query and "reschedul" in normalized_title:
        boost += 0.18
        reasons.append("reschedule title match")
    if "certificate" in query and "certificate" in normalized_title:
        boost += 0.12
        reasons.append("certificate title match")
    if "certificate" in query and any(term in query for term in ("name", "incorrect", "update")):
        chunk_text = chunk.search_text.lower()
        if "update the name" in chunk_text or "full name" in chunk_text or "regenerate certificate" in chunk_text:
            boost += 0.22
            reasons.append("certificate name update evidence")
    if any(term in query for term in ("model improvement", "improve the models", "use my data")):
        chunk_text = chunk.search_text.lower()
        if "model improvement" in chunk_text or "privacy settings" in chunk_text or "used solely to make claude better" in chunk_text:
            boost += 0.2
            reasons.append("model improvement privacy evidence")
    if any(term in query for term in ("remove them", "employee has left", "remove an interviewer", "remove a user")):
        chunk_text = chunk.search_text.lower()
        if "user management" in chunk_text or "remove users" in chunk_text or "remove access" in chunk_text:
            boost += 0.14
            reasons.append("user removal evidence")
    if "billing" in normalized_title or "payment" in normalized_title or "subscription" in normalized_title:
        if any(term in query for term in ("payment", "refund", "money", "order id", "subscription")):
            boost += 0.12
            reasons.append("billing title match")
    if "compatibility" in query and "compatibility" in normalized_title:
        boost += 0.12
        reasons.append("compatibility title match")
    if "crawl" in query and "crawl" in normalized_title:
        boost += 0.18
        reasons.append("crawler title match")
    if any(term in query for term in ("test active", "stay active", "received new tests", "how long do the tests")):
        chunk_text = chunk.search_text.lower()
        if chunk.product_area == "screen" and any(term in chunk_text for term in ("start date", "end date", "expire", "expiration", "invite")):
            boost += 0.2
            reasons.append("test lifecycle evidence")
    if "variant" in query and "variant" in normalized_title:
        boost += 0.2
        reasons.append("test variant title match")

    return boost, reasons
