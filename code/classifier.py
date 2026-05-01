from __future__ import annotations

from models import IntentSignal, Ticket


def classify_intent(ticket: Ticket) -> IntentSignal:
    text = ticket.query.lower()
    candidates: list[str] = []
    reasons: list[str] = []

    if any(phrase in text for phrase in ("thank you", "thanks", "thank u")) and len(text.split()) <= 8:
        return IntentSignal(("invalid",), 0.9, "courtesy message without a support request")

    if any(phrase in text for phrase in ("site is down", "stopped working", "not working", "all requests are failing", "submissions across", "down", "crash", "error", "broken", "bug")):
        candidates.append("bug")
        reasons.append("ticket describes failure or outage")

    if any(phrase in text for phrase in ("can you add", "feature request", "support for", "enhancement", "please add")):
        candidates.append("feature_request")
        reasons.append("ticket asks for product capability")

    if _looks_invalid(text, ticket.company):
        candidates.append("invalid")
        reasons.append("ticket appears outside supported domains")

    if not candidates:
        candidates.append("product_issue")
        reasons.append("default support/product question")
    elif "product_issue" not in candidates and any(
        phrase in text for phrase in ("how", "help", "please", "can you", "i need", "i want")
    ):
        candidates.append("product_issue")

    confidence = 0.75 if len(candidates) == 1 else 0.55
    return IntentSignal(tuple(dict.fromkeys(candidates)), confidence, "; ".join(reasons))


def revise_intent(pre_signal: IntentSignal, evidence_found: bool, high_risk: bool) -> str:
    if high_risk and "bug" in pre_signal.candidates:
        return "bug"
    if not evidence_found and "invalid" in pre_signal.candidates:
        return "invalid"
    if "feature_request" in pre_signal.candidates and evidence_found:
        return "feature_request"
    if "bug" in pre_signal.candidates:
        return "bug"
    if "invalid" in pre_signal.candidates and not evidence_found:
        return "invalid"
    return "product_issue"


def _looks_invalid(text: str, company: str | None) -> bool:
    if company:
        return False
    supported_terms = (
        "hackerrank",
        "claude",
        "visa",
        "assessment",
        "test",
        "card",
        "merchant",
        "candidate",
        "interview",
        "workspace",
    )
    if any(term in text for term in supported_terms):
        return False
    invalid_terms = ("iron man", "actor", "delete all files", "system files")
    return any(term in text for term in invalid_terms)
