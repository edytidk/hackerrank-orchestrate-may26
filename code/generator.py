from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from models import Decision, Ticket


def generate_response(ticket: Ticket, decision: Decision, use_llm: bool = True) -> str:
    if decision.status == "escalated":
        return "Escalate to a human"
    if decision.request_type == "invalid":
        return _invalid_response(ticket)
    if use_llm:
        llm_response = _try_llm_response(ticket, decision)
        if llm_response:
            return llm_response
    return _template_response(decision)


def _invalid_response(ticket: Ticket) -> str:
    text = ticket.query.lower()
    if "thank" in text:
        return "Happy to help."
    return "I am sorry, this is out of scope from my capabilities."


def _try_llm_response(ticket: Ticket, decision: Decision) -> str | None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI

        client = OpenAI()
        evidence = "\n\n".join(
            f"[{i}] {result.chunk.title}\n{result.chunk.text[:1800]}"
            for i, result in enumerate(decision.evidence[:4], 1)
        )
        prompt = f"""
You are writing a concise support response. Use only the evidence below.
Do not invent policies, links, phone numbers, or guarantees.

Ticket subject: {ticket.subject}
Ticket issue: {ticket.issue}
Decision: {decision.status}
Product area: {decision.product_area}
Request type: {decision.request_type}

Evidence:
{evidence}

Return JSON with one key, "response". The response should be helpful, direct, and grounded.
"""
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        response = str(parsed.get("response", "")).strip()
        return response if response else None
    except Exception:
        return None


def _template_response(decision: Decision) -> str:
    evidence_text = " ".join(result.chunk.text for result in decision.evidence[:3])
    sentences = _sentences(evidence_text)
    selected: list[str] = []
    for sentence in sentences:
        if 40 <= len(sentence) <= 320 and sentence not in selected:
            selected.append(sentence)
        if len(selected) >= 5:
            break
    if not selected and decision.evidence:
        selected.append(decision.evidence[0].chunk.text[:500].strip())
    return " ".join(selected).strip() or "Escalate to a human"


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
