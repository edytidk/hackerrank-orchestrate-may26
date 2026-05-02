from __future__ import annotations

import csv
import re
from pathlib import Path

from .classifier import classify_intent
from .corpus import load_corpus
from .decision import make_decision
from .generator import generate_response
from .models import AgentOutput, PipelineTrace, Ticket
from .retriever import Retriever
from .risk import assess_risk
from .validator import validate_output


OUTPUT_FIELDS = [
    "issue",
    "subject",
    "company",
    "response",
    "product_area",
    "status",
    "request_type",
    "justification",
]


class SupportAgent:
    def __init__(self, data_dir: Path, use_llm: bool = True) -> None:
        self.chunks = load_corpus(data_dir)
        self.retriever = Retriever(self.chunks)
        self.use_llm = use_llm

    def answer(self, ticket: Ticket) -> AgentOutput:
        return self.trace(ticket).output

    def trace(self, ticket: Ticket) -> PipelineTrace:
        intent = classify_intent(ticket)
        risk = assess_risk(ticket)
        evidence = self.retriever.search(ticket)
        decision = make_decision(ticket, intent, risk, evidence)
        response = generate_response(ticket, decision, use_llm=self.use_llm)
        output = validate_output(
            AgentOutput(
                issue=ticket.issue,
                subject=ticket.subject,
                company=ticket.company or "None",
                response=response,
                product_area=decision.product_area,
                status=decision.status,
                request_type=decision.request_type,
                justification=decision.justification,
            )
        )
        return PipelineTrace(
            ticket=ticket,
            intent=intent,
            risk=risk,
            evidence=tuple(evidence),
            decision=decision,
            output=output,
        )


def read_tickets(path: Path) -> list[Ticket]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    tickets: list[Ticket] = []
    for row_id, row in enumerate(rows, 1):
        issue = _clean(row.get("Issue") or row.get("issue") or "")
        subject = _clean(row.get("Subject") or row.get("subject") or "")
        company = _normalize_company(row.get("Company") or row.get("company") or "")
        query_parts = [issue]
        if subject:
            query_parts.append(subject)
        if issue and subject and issue.lower() != subject.lower():
            query_parts.append(issue)
        query = _clean("\n".join(query_parts))
        tickets.append(
            Ticket(
                row_id=row_id,
                issue=issue,
                subject=subject,
                company=company,
                query=query,
            )
        )
    return tickets


def write_outputs(path: Path, outputs: list[AgentOutput]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for output in outputs:
            writer.writerow(
                {
                    "issue": output.issue,
                    "subject": output.subject,
                    "company": output.company,
                    "response": output.response,
                    "product_area": output.product_area,
                    "status": output.status,
                    "request_type": output.request_type,
                    "justification": output.justification,
                }
            )


def run_pipeline(
    input_path: Path, output_path: Path, data_dir: Path, use_llm: bool = True
) -> list[AgentOutput]:
    agent = SupportAgent(data_dir=data_dir, use_llm=use_llm)
    tickets = read_tickets(input_path)
    outputs = [agent.answer(ticket) for ticket in tickets]
    write_outputs(output_path, outputs)
    return outputs


def _normalize_company(value: str) -> str | None:
    value = value.strip()
    if not value or value.lower() == "none":
        return None
    lowered = value.lower()
    if "hackerrank" in lowered:
        return "HackerRank"
    if "claude" in lowered:
        return "Claude"
    if "visa" in lowered:
        return "Visa"
    return value


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
