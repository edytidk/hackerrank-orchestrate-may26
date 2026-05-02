from __future__ import annotations

import re

import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

from .models import Chunk, RetrievalResult, Ticket


class Retriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks: list[Chunk] = chunks
        self.texts: list[str] = [chunk.search_text for chunk in chunks]
        self.lexical_vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_features=80000,
        )
        self.lexical_matrix = self.lexical_vectorizer.fit_transform(self.texts)
        self.char_vectorizer = TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            max_features=50000,
        )
        self.char_matrix = self.char_vectorizer.fit_transform(self.texts)
        self.embedding_projection: TruncatedSVD | None = None
        self.embedding_matrix: np.ndarray | None = self._build_local_embedding_matrix()

    def search(
        self, ticket: Ticket, top_k: int = 6, pool_size: int = 160
    ) -> list[RetrievalResult]:
        query = ticket.query
        lexical_scores = self._lexical_scores(query)
        vector_scores = self._vector_scores(query)
        grep_scores = self._grep_scores(ticket)
        scores = (0.45 * lexical_scores) + (0.20 * vector_scores) + (0.35 * grep_scores)

        if ticket.company:
            company_mask = np.array(
                [chunk.company == ticket.company for chunk in self.chunks]
            )
            same_company_max = (
                float(scores[company_mask].max()) if company_mask.any() else 0.0
            )
            if same_company_max >= 0.08:
                scores = np.where(company_mask, scores, scores * 0.25)

        candidate_indexes = np.argsort(scores)[::-1][:pool_size]
        results: list[RetrievalResult] = []
        for index in candidate_indexes:
            chunk = self.chunks[int(index)]
            combined_score = float(scores[int(index)])
            if combined_score <= 0:
                continue
            boost, reasons = _metadata_boost(ticket, chunk)
            final_score = combined_score + boost
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    lexical_score=float(lexical_scores[int(index)]),
                    vector_score=float(vector_scores[int(index)]),
                    grep_score=float(grep_scores[int(index)]),
                    metadata_boost=boost,
                    final_score=final_score,
                    reason=", ".join(reasons) if reasons else "lexical match",
                )
            )

        return sorted(results, key=lambda item: item.final_score, reverse=True)[:top_k]

    def _lexical_scores(self, query: str) -> np.ndarray:
        query_vector = self.lexical_vectorizer.transform([query])
        return cosine_similarity(self.lexical_matrix, query_vector).ravel()

    def _vector_scores(self, query: str) -> np.ndarray:
        if self.embedding_matrix is None or self.embedding_projection is None:
            query_vector = self.char_vectorizer.transform([query])
            return cosine_similarity(self.char_matrix, query_vector).ravel()
        sparse_query = sparse.hstack(
            [
                self.lexical_vectorizer.transform([query]),
                self.char_vectorizer.transform([query]),
            ],
            format="csr",
        )
        query_embedding = normalize(self.embedding_projection.transform(sparse_query))
        return cosine_similarity(self.embedding_matrix, query_embedding).ravel()

    def _grep_scores(self, ticket: Ticket) -> np.ndarray:
        query_terms = _expanded_terms(ticket.query)
        query_phrases = _important_phrases(ticket.query)
        if not query_terms and not query_phrases:
            return np.zeros(len(self.chunks))

        scores = np.zeros(len(self.chunks))
        for index, chunk in enumerate(self.chunks):
            haystack = chunk.search_text.lower()
            title = chunk.title.lower()
            heading = " ".join(chunk.heading_path).lower()

            term_hits = sum(1 for term in query_terms if term in haystack)
            phrase_hits = sum(1 for phrase in query_phrases if phrase in haystack)
            title_hits = sum(1 for term in query_terms if term in title)
            heading_hits = sum(1 for term in query_terms if term in heading)

            denominator = max(4, len(query_terms) + (2 * len(query_phrases)))
            scores[index] = min(
                1.0,
                (term_hits + (2 * phrase_hits) + title_hits + heading_hits)
                / denominator,
            )
        return scores

    def _build_local_embedding_matrix(self) -> np.ndarray | None:
        feature_matrix = sparse.hstack(
            [self.lexical_matrix, self.char_matrix],
            format="csr",
        )
        components = min(256, max(2, min(feature_matrix.shape) - 1))
        if components < 2:
            self.embedding_projection = None
            return None
        self.embedding_projection = TruncatedSVD(n_components=components, random_state=42)
        embeddings = self.embedding_projection.fit_transform(feature_matrix)
        return normalize(embeddings)


def _metadata_boost(ticket: Ticket, chunk: Chunk) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []
    query = ticket.query.lower()
    query_terms = set(_expanded_terms(query))

    if ticket.company and ticket.company == chunk.company:
        boost += 0.08
        reasons.append("company match")

    title_terms = set(re.findall(r"[a-z0-9]+", chunk.title.lower()))
    if query_terms & title_terms:
        boost += min(0.10, 0.02 * len(query_terms & title_terms))
        reasons.append("title overlap")

    product_terms = set(chunk.product_area.replace("_", " ").split())
    if query_terms & product_terms:
        boost += 0.04
        reasons.append("product area overlap")

    heading_terms = set(re.findall(r"[a-z0-9]+", " ".join(chunk.heading_path).lower()))
    if query_terms & heading_terms:
        boost += min(0.08, 0.02 * len(query_terms & heading_terms))
        reasons.append("heading overlap")

    action_terms = query_terms & {
        "add",
        "block",
        "cancel",
        "change",
        "delete",
        "disable",
        "dispute",
        "download",
        "enable",
        "pause",
        "remove",
        "report",
        "reschedule",
        "update",
    }
    chunk_terms = set(_important_terms(chunk.search_text))
    if action_terms and action_terms & chunk_terms:
        boost += min(0.08, 0.025 * len(action_terms & chunk_terms))
        reasons.append("action overlap")

    concept_overlap = _concept_overlap(query, chunk.search_text)
    if concept_overlap:
        boost += min(0.18, 0.045 * len(concept_overlap))
        reasons.append("concept overlap")
        normalized_title = chunk.title.lower()
        if "user_management" in concept_overlap and (
            "manage users" in normalized_title
            or "deactivating a user" in chunk.search_text.lower()
            or "deactivate user" in chunk.search_text.lower()
        ):
            boost += 0.12
            reasons.append("user management article")
        if "integration" in normalized_title and "integration" not in query:
            boost -= 0.06
            reasons.append("integration mismatch")

    return boost, reasons


CONCEPT_LEXICON: dict[str, dict[str, set[str]]] = {
    "test_lifecycle": {
        "query": {"active", "expire", "expiration", "stay", "assigned", "invited"},
        "evidence": {"start", "end", "date", "time", "expire", "expiration", "invite"},
    },
    "bedrock_support": {
        "query": {"bedrock", "failing", "failed", "requests", "issues"},
        "evidence": {"bedrock", "support", "aws", "account", "manager", "inquiries"},
    },
    "user_management": {
        "query": {"employee", "left", "remove", "interviewer", "user", "account"},
        "evidence": {"user", "management", "deactivate", "deactivating", "admin", "panel"},
    },
    "certificate_name": {
        "query": {"certificate", "name", "incorrect", "update"},
        "evidence": {"certificate", "name", "regenerate", "full", "update"},
    },
    "crawler_control": {
        "query": {"crawl", "crawler", "website", "stop"},
        "evidence": {"crawl", "crawler", "claudebot", "robots", "disallow"},
    },
    "cash_withdrawal": {
        "query": {"cash", "urgent", "visa", "card"},
        "evidence": {"cash", "atm", "withdraw", "withdrawal", "locator"},
    },
    "zoom_compatibility": {
        "query": {"zoom", "connectivity", "compatible", "compatibility", "criterias", "test"},
        "evidence": {"zoom", "domains", "blocked", "compatibility", "browser", "interviews"},
    },
    "interview_inactivity": {
        "query": {"inactivity", "screen", "share", "lobby", "candidate", "interviewer"},
        "evidence": {"candidate", "lobby", "interviewer", "interview", "inactivity"},
    },
    "charge_dispute": {
        "query": {"dispute", "charge", "transaction"},
        "evidence": {"dispute", "charge", "issuer", "bank", "transaction"},
    },
    "vulnerability_reporting": {
        "query": {"security", "vulnerability", "report", "next", "steps"},
        "evidence": {"security", "vulnerability", "responsible", "disclosure", "report"},
    },
}


def _expanded_terms(text: str) -> list[str]:
    terms = _important_terms(text)
    term_set = set(terms)
    for concept in CONCEPT_LEXICON.values():
        if term_set & concept["query"]:
            terms.extend(sorted(concept["evidence"]))
    return list(dict.fromkeys(terms))


def _concept_overlap(query: str, chunk_text: str) -> set[str]:
    query_terms = set(_important_terms(query))
    chunk_terms = set(_important_terms(chunk_text))
    matched = set()
    for name, concept in CONCEPT_LEXICON.items():
        query_overlap = query_terms & concept["query"]
        evidence_overlap = chunk_terms & concept["evidence"]
        if len(query_overlap) >= 2 and len(evidence_overlap) >= 2:
            matched.add(name)
    return matched


def _important_terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "been",
        "being",
        "between",
        "but",
        "can",
        "cannot",
        "could",
        "doing",
        "for",
        "from",
        "have",
        "help",
        "how",
        "into",
        "need",
        "please",
        "should",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "this",
        "through",
        "using",
        "want",
        "what",
        "when",
        "where",
        "with",
        "would",
        "you",
        "your",
    }
    terms = re.findall(r"[a-z0-9]+", text.lower())
    return [term for term in terms if len(term) > 2 and term not in stopwords]


def _important_phrases(text: str) -> list[str]:
    normalized = " ".join(_important_terms(text))
    terms = normalized.split()
    phrases = []
    for size in (2, 3):
        phrases.extend(
            " ".join(terms[index : index + size])
            for index in range(len(terms) - size + 1)
        )
    return phrases[:30]
