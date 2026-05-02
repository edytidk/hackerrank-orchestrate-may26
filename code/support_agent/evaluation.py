from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .agent import SupportAgent, read_tickets
from .models import AgentOutput, PipelineTrace


LOW_SIGNAL_RESPONSE_TERMS = (
    "Last updated",
    "Related Articles",
    "embedded media",
    ".gif",
    ".png",
    "mceclip",
)


@dataclass(frozen=True)
class AuditResult:
    rows: int
    status_counts: dict[str, int]
    request_type_counts: dict[str, int]
    product_area_counts: dict[str, int]
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.issues


def audit_input(input_path: Path, data_dir: Path, use_llm: bool = False) -> AuditResult:
    agent = SupportAgent(data_dir=data_dir, use_llm=use_llm)
    traces = [agent.trace(ticket) for ticket in read_tickets(input_path)]
    return audit_traces(traces)


def audit_traces(traces: list[PipelineTrace]) -> AuditResult:
    status_counts: dict[str, int] = {}
    request_type_counts: dict[str, int] = {}
    product_area_counts: dict[str, int] = {}
    issues: list[str] = []

    for trace in traces:
        output = trace.output
        row_label = f"row {trace.ticket.row_id}"
        status_counts[output.status] = status_counts.get(output.status, 0) + 1
        request_type_counts[output.request_type] = (
            request_type_counts.get(output.request_type, 0) + 1
        )
        product_area = output.product_area or "<blank>"
        product_area_counts[product_area] = product_area_counts.get(product_area, 0) + 1
        issues.extend(_output_issues(row_label, output))
        issues.extend(_trace_issues(row_label, trace))

    return AuditResult(
        rows=len(traces),
        status_counts=dict(sorted(status_counts.items())),
        request_type_counts=dict(sorted(request_type_counts.items())),
        product_area_counts=dict(sorted(product_area_counts.items())),
        issues=tuple(issues),
    )


def compare_sample_labels(sample_path: Path, data_dir: Path) -> dict[str, int]:
    agent = SupportAgent(data_dir=data_dir, use_llm=False)
    tickets = read_tickets(sample_path)
    expected_rows = _read_sample_expectations(sample_path)
    totals = {"rows": len(tickets), "status": 0, "request_type": 0, "product_area": 0}

    for ticket, expected in zip(tickets, expected_rows, strict=True):
        output = agent.answer(ticket)
        if output.status == expected.get("Status", "").strip().lower():
            totals["status"] += 1
        if output.request_type == expected.get("Request Type", "").strip().lower():
            totals["request_type"] += 1
        if output.product_area == expected.get("Product Area", "").strip():
            totals["product_area"] += 1

    return totals


def _read_sample_expectations(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _output_issues(row_label: str, output: AgentOutput) -> list[str]:
    issues: list[str] = []
    if output.status not in {"replied", "escalated"}:
        issues.append(f"{row_label}: invalid status {output.status!r}")
    if output.request_type not in {"product_issue", "feature_request", "bug", "invalid"}:
        issues.append(f"{row_label}: invalid request_type {output.request_type!r}")
    if not output.response.strip():
        issues.append(f"{row_label}: blank response")
    if not output.justification.strip():
        issues.append(f"{row_label}: blank justification")
    if output.status == "escalated" and output.response != "Escalate to a human":
        issues.append(f"{row_label}: escalation response must be exactly fixed")
    if output.status == "replied":
        for term in LOW_SIGNAL_RESPONSE_TERMS:
            if term.lower() in output.response.lower():
                issues.append(f"{row_label}: low-signal response text contains {term!r}")
        if len(output.response.split()) < 6:
            issues.append(f"{row_label}: reply is too thin")
    return issues


def _trace_issues(row_label: str, trace: PipelineTrace) -> list[str]:
    if trace.output.status == "escalated":
        return []
    if not trace.evidence:
        return [f"{row_label}: replied without retrieval evidence"]
    best = trace.evidence[0]
    issues: list[str] = []
    if best.final_score < 0.18:
        issues.append(f"{row_label}: reply evidence score below threshold")
    if trace.ticket.company and best.chunk.company != trace.ticket.company:
        issues.append(
            f"{row_label}: top evidence company {best.chunk.company!r} does not match ticket company {trace.ticket.company!r}"
        )
    return issues
