from __future__ import annotations

import csv
import sys
from importlib import import_module
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

support_agent_module = import_module("support_agent.agent")
models_module = import_module("support_agent.models")
evaluation_module = import_module("support_agent.evaluation")

SupportAgent = support_agent_module.SupportAgent
read_tickets = support_agent_module.read_tickets
write_outputs = support_agent_module.write_outputs
AgentOutput = models_module.AgentOutput
audit_traces = evaluation_module.audit_traces
compare_sample_labels = evaluation_module.compare_sample_labels


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


def test_real_ticket_regressions_for_sensitive_payment_cases() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")

    mock_interview_refund = agent.answer(tickets[3])
    assert mock_interview_refund.status == "escalated"
    assert mock_interview_refund.response == "Escalate to a human"

    generic_payment_issue = agent.answer(tickets[4])
    assert generic_payment_issue.status == "escalated"
    assert generic_payment_issue.response == "Escalate to a human"


def test_real_ticket_regressions_for_response_quality() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")

    website_crawl = agent.answer(tickets[20])
    assert "Last updated" not in website_crawl.response
    assert "robots.txt" in website_crawl.response
    assert "ClaudeBot" in website_crawl.response

    urgent_cash = agent.answer(tickets[21])
    assert "lost or stolen" not in urgent_cash.response.lower()
    assert (
        "atm" in urgent_cash.response.lower()
        or "cash withdrawal" in urgent_cash.response.lower()
    )

    bedrock_failures = agent.answer(tickets[25])
    assert "Related Articles" not in bedrock_failures.response
    assert (
        "AWS Support" in bedrock_failures.response
        or "AWS account manager" in bedrock_failures.response
    )


def test_real_ticket_regressions_for_vague_and_user_management_cases() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")

    vague_none_ticket = agent.answer(tickets[11])
    assert vague_none_ticket.status == "escalated"

    resume_builder_down = agent.answer(tickets[16])
    assert resume_builder_down.status == "escalated"

    employee_removal = agent.answer(tickets[26])
    assert employee_removal.status == "replied"
    assert "Deactivate User" in employee_removal.response


def test_real_ticket_regressions_for_authority_and_invalid_cases() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")

    mixed_hackerrank_issue = agent.answer(tickets[6])
    assert mixed_hackerrank_issue.status == "escalated"

    assessment_reschedule = agent.answer(tickets[9])
    assert assessment_reschedule.status == "escalated"

    destructive_request = agent.answer(tickets[23])
    assert destructive_request.request_type == "invalid"

    score_dispute = agent.answer(tickets[1])
    assert score_dispute.status == "escalated"
    assert score_dispute.product_area == ""


def test_safe_guidance_questions_are_answered_from_corpus() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")

    charge_dispute = agent.answer(tickets[18])
    assert charge_dispute.status == "replied"
    assert charge_dispute.product_area == "general_support"
    assert "issuer or bank" in charge_dispute.response

    vulnerability = agent.answer(tickets[19])
    assert vulnerability.status == "replied"
    assert vulnerability.product_area == "safeguards"
    assert "Responsible Disclosure" in vulnerability.response


def test_final_output_quality_invariants() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")
    outputs = [agent.answer(ticket) for ticket in tickets]

    assert len(outputs) == 29
    for output in outputs:
        assert output.status in {"replied", "escalated"}
        assert output.request_type in {
            "product_issue",
            "feature_request",
            "bug",
            "invalid",
        }
        assert output.response
        assert output.justification
        if output.status == "escalated":
            assert output.response == "Escalate to a human"
        else:
            assert "Last updated" not in output.response
            assert "Related Articles" not in output.response
            assert ".gif" not in output.response
            assert ".png" not in output.response


def test_pipeline_trace_exposes_retrieval_components() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")
    trace = agent.trace(tickets[20])

    assert trace.intent.candidates
    assert trace.risk.level
    assert trace.evidence
    best = trace.evidence[0]
    assert best.final_score > 0
    assert best.lexical_score >= 0
    assert best.vector_score >= 0
    assert best.grep_score >= 0
    assert trace.output.response


def test_release_audit_and_sample_calibration_are_clean() -> None:
    agent = SupportAgent(REPO_ROOT / "data", use_llm=False)
    tickets = read_tickets(REPO_ROOT / "support_tickets" / "support_tickets.csv")
    result = audit_traces([agent.trace(ticket) for ticket in tickets])

    assert result.passed, result.issues
    assert result.rows == 29
    assert result.status_counts == {"escalated": 15, "replied": 14}

    sample = compare_sample_labels(
        REPO_ROOT / "support_tickets" / "sample_support_tickets.csv",
        REPO_ROOT / "data",
    )
    assert sample == {"rows": 10, "status": 10, "request_type": 10, "product_area": 10}
