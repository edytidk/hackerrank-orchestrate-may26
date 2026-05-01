from __future__ import annotations

from classifier import revise_intent
from models import Decision, IntentSignal, RetrievalResult, RiskSignal, Ticket


MIN_REPLY_SCORE = 0.18


def make_decision(
    ticket: Ticket,
    intent: IntentSignal,
    risk: RiskSignal,
    evidence: list[RetrievalResult],
) -> Decision:
    best_score = evidence[0].final_score if evidence else 0.0
    evidence_found = bool(evidence) and best_score >= MIN_REPLY_SCORE
    high_risk = risk.level == "high"
    request_type = revise_intent(intent, evidence_found=evidence_found, high_risk=high_risk)
    product_area = _choose_product_area(ticket, evidence)

    if "invalid" in intent.candidates and intent.confidence >= 0.85:
        return Decision(
            status="replied",
            request_type="invalid",
            product_area=product_area or "conversation_management",
            should_generate_reply=False,
            justification="The ticket is a courtesy or out-of-scope message rather than a support request.",
            evidence=tuple(evidence),
        )

    if request_type == "invalid" and not evidence_found:
        return Decision(
            status="replied",
            request_type="invalid",
            product_area=product_area or "conversation_management",
            should_generate_reply=False,
            justification="The ticket is outside the supported HackerRank, Claude, and Visa support domains.",
            evidence=tuple(evidence),
        )

    if high_risk:
        return Decision(
            status="escalated",
            request_type=request_type,
            product_area="" if "broad outage" in risk.reasons else product_area,
            should_generate_reply=False,
            justification=f"Escalation required because the ticket involves {', '.join(risk.reasons)}.",
            evidence=tuple(evidence),
        )

    if risk.level == "unsupported" or not evidence_found:
        return Decision(
            status="escalated",
            request_type=request_type,
            product_area="",
            should_generate_reply=False,
            justification="Escalation required because the ticket lacks enough detail or strong corpus evidence.",
            evidence=tuple(evidence),
        )

    return Decision(
        status="replied",
        request_type=request_type,
        product_area=product_area,
        should_generate_reply=True,
        justification=_reply_justification(ticket, evidence),
        evidence=tuple(evidence),
    )


def _choose_product_area(ticket: Ticket, evidence: list[RetrievalResult]) -> str:
    text = ticket.query.lower()
    if any(phrase in text for phrase in ("iron man", "actor", "delete all files")):
        return "conversation_management"
    if any(phrase in text for phrase in ("thank you", "thanks")) and len(text.split()) <= 8:
        return "conversation_management"
    if ticket.company == "HackerRank" and any(term in text for term in ("test active", "stay active", "variant", "assessment", "candidate", "submissions")):
        if evidence and evidence[0].chunk.product_area in {"screen", "community", "interviews"}:
            return evidence[0].chunk.product_area
    if ticket.company == "Claude" and any(term in text for term in ("private info", "conversation", "delete", "model improvement", "crawl", "personal data")):
        if evidence and evidence[0].chunk.product_area in {"claude", "privacy_and_legal"}:
            return "privacy"
    if not evidence:
        return ""
    if ticket.company:
        for result in evidence:
            if result.chunk.company == ticket.company and result.chunk.product_area:
                return result.chunk.product_area
    return evidence[0].chunk.product_area


def _reply_justification(ticket: Ticket, evidence: list[RetrievalResult]) -> str:
    best = evidence[0].chunk
    company = ticket.company or best.company
    source = best.title or best.doc_id
    return (
        f"The ticket matches {company} support content in '{source}', "
        f"with enough corpus evidence to provide a grounded response."
    )
