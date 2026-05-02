from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from .models import Decision, IntentSignal, RetrievalResult, RiskSignal, Ticket


def generate_justification(
    ticket: Ticket,
    intent: IntentSignal,
    risk: RiskSignal,
    evidence: tuple[RetrievalResult, ...],
    decision: Decision,
    use_llm: bool,
) -> str:
    base = _deterministic_justification(ticket, intent, risk, evidence, decision)
    if not use_llm:
        return base
    llm_result = _try_llm_justification(
        ticket=ticket,
        intent=intent,
        risk=risk,
        evidence=evidence,
        decision=decision,
        base=base,
    )
    return llm_result or base


def _deterministic_justification(
    ticket: Ticket,
    intent: IntentSignal,
    risk: RiskSignal,
    evidence: tuple[RetrievalResult, ...],
    decision: Decision,
) -> str:
    reason = _normalize_reason(decision.justification)
    evidence_summary = _evidence_summary(ticket, evidence)
    risk_summary = _risk_summary(risk)

    if decision.status == "escalated":
        parts = [
            f"Escalated because {reason}",
            risk_summary,
            evidence_summary,
            "A human should review the request before any user-facing resolution is given because the agent cannot safely complete this action from the available support corpus alone.",
        ]
        return " ".join(part for part in parts if part)

    if decision.request_type == "invalid":
        return (
            f"Replied as invalid because {reason} "
            "The ticket does not require product troubleshooting, and the response avoids claiming unsupported product guidance."
        )

    parts = [
        f"Replied because {reason}",
        evidence_summary,
        "The response is limited to the retrieved support content and does not add policies or account-specific actions beyond that evidence.",
    ]
    return " ".join(part for part in parts if part)


def _normalize_reason(reason: str) -> str:
    cleaned = reason.strip()
    cleaned = re.sub(r"^Escalation required because\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^The ticket\s+", "the ticket ", cleaned)
    cleaned = cleaned[0].lower() + cleaned[1:] if cleaned else "the ticket needs review"
    return cleaned.rstrip(".") + "."


def _risk_summary(risk: RiskSignal) -> str:
    if risk.level == "low" and not risk.reasons:
        return ""
    reasons = ", ".join(risk.reasons) if risk.reasons else "insufficient support coverage"
    return f"Risk level is {risk.level} due to {reasons}."


def _evidence_summary(
    ticket: Ticket, evidence: tuple[RetrievalResult, ...]
) -> str:
    if not evidence:
        return "No strong matching support article was retrieved for a grounded self-serve answer."

    best = evidence[0]
    chunk = best.chunk
    score_line = (
        f"Top evidence was '{chunk.title}' "
        f"({chunk.company}, {chunk.product_area or 'uncategorized'}) "
        f"with final retrieval score {best.final_score:.3f}."
    )
    if ticket.company and chunk.company != ticket.company:
        return (
            f"{score_line} Because the top evidence belongs to {chunk.company} rather "
            f"than {ticket.company}, the match is not strong enough for a direct answer."
        )
    if best.final_score < 0.18:
        return f"{score_line} That score is below the reply threshold, so the evidence is too weak."
    return score_line


def _try_llm_justification(
    ticket: Ticket,
    intent: IntentSignal,
    risk: RiskSignal,
    evidence: tuple[RetrievalResult, ...],
    decision: Decision,
    base: str,
) -> str | None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI

        evidence_text = "\n".join(
            (
                f"[{index}] title={result.chunk.title}; "
                f"company={result.chunk.company}; "
                f"product_area={result.chunk.product_area}; "
                f"score={result.final_score:.3f}; "
                f"reason={result.reason}"
            )
            for index, result in enumerate(evidence[:3], 1)
        )
        prompt = f"""
Write one concise CSV-safe justification for this support-ticket routing decision.
Do not invent policies, links, phone numbers, or hidden facts.
If status is escalated, explicitly say why human escalation is needed.
Keep it to 2-3 sentences.

Ticket company: {ticket.company or "None"}
Ticket subject: {ticket.subject}
Ticket issue: {ticket.issue}
Intent candidates: {", ".join(intent.candidates)}
Intent reason: {intent.reason}
Risk level: {risk.level}
Risk reasons: {", ".join(risk.reasons) or "none"}
Decision status: {decision.status}
Decision request_type: {decision.request_type}
Decision product_area: {decision.product_area or "blank"}
Base justification: {base}

Evidence:
{evidence_text or "No retrieval evidence."}

Return JSON with one key, "justification".
"""
        completion = OpenAI().chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        justification = str(parsed.get("justification", "")).strip()
        if not justification:
            return None
        if decision.status == "escalated" and "escalat" not in justification.lower():
            return None
        return justification.replace("\n", " ")
    except Exception:
        return None
