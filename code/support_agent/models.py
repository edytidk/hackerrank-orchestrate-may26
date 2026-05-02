from __future__ import annotations

from dataclasses import dataclass, field


VALID_STATUSES = {"replied", "escalated"}
VALID_REQUEST_TYPES = {"product_issue", "feature_request", "bug", "invalid"}


@dataclass(frozen=True)
class Ticket:
    row_id: int
    issue: str
    subject: str
    company: str | None
    query: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    company: str
    product_area: str
    title: str
    breadcrumbs: tuple[str, ...]
    source_url: str
    file_path: str
    heading_path: tuple[str, ...]
    chunk_index: int
    text: str
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None

    @property
    def search_text(self) -> str:
        metadata = " ".join(
            [
                self.company,
                self.product_area,
                self.title,
                " ".join(self.breadcrumbs),
                " ".join(self.heading_path),
            ]
        )
        return f"{metadata}\n{self.text}"


@dataclass(frozen=True)
class RetrievalResult:
    chunk: Chunk
    lexical_score: float
    vector_score: float
    grep_score: float
    metadata_boost: float
    final_score: float
    reason: str


@dataclass(frozen=True)
class IntentSignal:
    candidates: tuple[str, ...]
    confidence: float
    reason: str


@dataclass(frozen=True)
class RiskSignal:
    level: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Decision:
    status: str
    request_type: str
    product_area: str
    should_generate_reply: bool
    justification: str
    evidence: tuple[RetrievalResult, ...]


@dataclass(frozen=True)
class AgentOutput:
    issue: str
    subject: str
    company: str
    response: str
    product_area: str
    status: str
    request_type: str
    justification: str


@dataclass(frozen=True)
class PipelineTrace:
    ticket: Ticket
    intent: IntentSignal
    risk: RiskSignal
    evidence: tuple[RetrievalResult, ...]
    decision: Decision
    output: AgentOutput
