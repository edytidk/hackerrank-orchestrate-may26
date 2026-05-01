from __future__ import annotations

import csv
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from agent import SupportAgent, read_tickets, write_outputs  # noqa: E402
from models import AgentOutput  # noqa: E402


def test_read_tickets_preserves_final_ticket_count() -> None:
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")
    assert len(tickets) == 29
    assert tickets[0].company == "Claude"
    assert "workspace" in tickets[0].query.lower()


def test_writer_emits_required_schema(tmp_path: Path) -> None:
    output = AgentOutput(
        issue="issue",
        subject="subject",
        company="None",
        response="Escalate to a human",
        product_area="",
        status="escalated",
        request_type="bug",
        justification="test",
    )
    path = tmp_path / "output.csv"
    write_outputs(path, [output])

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0].keys()) == [
        "issue",
        "subject",
        "company",
        "response",
        "product_area",
        "status",
        "request_type",
        "justification",
    ]
    assert rows[0]["status"] == "escalated"


def test_sample_labels_for_core_cases() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "sample_support_tickets.csv")

    test_active = agent.answer(tickets[0])
    assert test_active.status == "replied"
    assert test_active.request_type == "product_issue"
    assert test_active.product_area == "screen"

    outage = agent.answer(tickets[1])
    assert outage.status == "escalated"
    assert outage.request_type == "bug"

    out_of_scope = agent.answer(tickets[6])
    assert out_of_scope.status == "replied"
    assert out_of_scope.request_type == "invalid"
    assert out_of_scope.product_area == "conversation_management"
