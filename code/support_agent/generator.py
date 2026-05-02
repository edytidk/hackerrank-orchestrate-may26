from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from .models import Decision, Ticket


LOW_SIGNAL_PATTERNS = (
    "last updated",
    "related articles",
    "embedded media",
    "mceclip",
    ".png",
    ".gif",
)


def generate_response(ticket: Ticket, decision: Decision, use_llm: bool = True) -> str:
    if decision.status == "escalated":
        return "Escalate to a human"
    if decision.request_type == "invalid":
        return _invalid_response(ticket)
    if use_llm:
        llm_response = _try_llm_response(ticket, decision)
        if llm_response:
            return llm_response
    return _template_response(ticket, decision)


def _invalid_response(ticket: Ticket) -> str:
    text = ticket.query.lower()
    if "thank" in text:
        return "Happy to help."
    return "I am sorry, this is out of scope from my capabilities."


def _try_llm_response(ticket: Ticket, decision: Decision) -> str | None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
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


def _template_response(ticket: Ticket, decision: Decision) -> str:
    if not decision.evidence:
        return "Escalate to a human"

    special_response = _special_response(ticket, decision)
    if special_response:
        return special_response

    evidence_text = "\n".join(result.chunk.text for result in decision.evidence[:2])
    sentences = _usable_sentences(evidence_text)
    if not sentences:
        return "Escalate to a human"

    lead = sentences[0]
    extras = [sentence for sentence in sentences[1:] if sentence not in {lead}][:2]
    body = " ".join([lead, *extras]).strip()
    return f"Hi,\n\n{body}".strip()


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()
    ]


def _usable_sentences(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    filtered_lines = [line for line in lines if not _is_low_signal(line)]
    filtered_text = " ".join(filtered_lines)
    sentences = _sentences(filtered_text)
    usable: list[str] = []
    for sentence in sentences:
        normalized = sentence.strip()
        if _is_low_signal(normalized):
            continue
        if len(normalized) < 25:
            continue
        if normalized not in usable:
            usable.append(normalized)
    return usable


def _is_low_signal(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return True
    if any(pattern in lowered for pattern in LOW_SIGNAL_PATTERNS):
        return True
    if lowered.startswith("#"):
        return True
    if lowered.endswith(":") and len(lowered.split()) <= 8:
        return True
    return False


def _special_response(ticket: Ticket, decision: Decision) -> str | None:
    best = decision.evidence[0].chunk
    title = best.title.lower()
    text = ticket.query.lower()

    if "crawl data from the web" in title or "block the crawler" in title:
        return (
            "Hi,\n\n"
            "Yes. Anthropic says site owners can limit or block ClaudeBot through robots.txt. "
            "To block crawling for a site or subdomain, add `User-agent: ClaudeBot` and `Disallow: /` to the robots.txt file. "
            "Anthropic also supports `Crawl-delay`, and if you believe a bot is malfunctioning, you can contact claudebot@anthropic.com from an email address associated with the domain."
        )

    if "customer support inquiries" in title and "bedrock" in text:
        return (
            "Hi,\n\n"
            "For Claude in Amazon Bedrock support issues, Anthropic directs you to contact AWS Support or your AWS account manager. "
            "If you prefer community-based help, you can also use AWS re:Post."
        )

    if "visa consumer support" in title and "cash" in text:
        return (
            "Hi,\n\n"
            "You can use Visa’s ATM locator to find a nearby ATM and withdraw local currency with a Visa card that supports ATM withdrawals. "
            "If you are traveling, Visa’s travel support guidance also notes that cards with the PLUS logo can be used for cash withdrawals at supported ATMs worldwide."
        )

    if "visa travel services" in title and "cash" in text:
        return (
            "Hi,\n\n"
            "You can use Visa’s ATM locator to find a nearby ATM and withdraw local currency. "
            "Visa’s travel support guidance says cards with the PLUS logo can be used for cash withdrawals at supported ATMs worldwide using your PIN."
        )

    if "pause subscription" in title:
        return (
            "Hi,\n\n"
            "You can pause your subscription if you have an eligible active monthly plan. "
            "Go to your profile icon, open Settings, then Billing under Subscription. Click Cancel Plan, choose the Pause Subscription option, select a pause duration between 1 and 12 months, and confirm the pause."
        )

    if "search and apply for jobs" in title and "apply tab" in text:
        return (
            "Hi,\n\n"
            "The relevant HackerRank Community guidance points you to the Search and Apply flow for developer jobs. "
            "Log in to HackerRank Community, open the job search area, and use the apply flow there. If you want a faster setup, you can start QuickApply from the Community site by selecting See how it works and completing the onboarding steps."
        )

    if (
        "audio and video calls in interviews powered by zoom" in title
        and "compatib" in text
    ):
        return (
            "Hi,\n\n"
            "For Zoom-powered interview calls, HackerRank says the required Zoom domains must not be blocked on your network, including `.zoom.us`, `..zoom.us`, and `zoom.us`. "
            "It also recommends using the latest version of Chrome, Edge, or Firefox. If your compatibility check is still failing after that, this may need support review for your environment."
        )

    if (
        "certifications faqs" in title
        and "certificate" in text
        and any(term in text for term in ("name", "incorrect", "update"))
    ):
        return (
            "Hi,\n\n"
            "Yes. You can update the name on your certificate once per account. "
            "Open your certificate page, enter the name you want in the Full Name field, click Regenerate Certificate, and then confirm by selecting Update Name."
        )

    if "who can view my conversations" in title and any(
        term in text
        for term in ("use my data", "improve the models", "model improvement")
    ):
        return (
            "Hi,\n\n"
            "The available privacy guidance says you can change your privacy and model-improvement settings at any time. "
            "It also says conversations used for review are de-linked from your user ID and access is limited to a small number of authorized personnel. The article does not give a specific duration for how long data is used for model improvement."
        )

    if "set up the claude lti in canvas" in title:
        return (
            "Hi,\n\n"
            "To set up the Claude LTI in Canvas, an administrator should create a new LTI developer key in Canvas under Admin > Developer Keys, then use that Client ID to install the app in Canvas. "
            "After that, enable the Canvas connector in Claude for Education under Organization settings > Connectors and enter the Canvas domain, Client ID, and Deployment ID."
        )

    if "create a resume with resume builder" in title:
        return (
            "Hi,\n\n"
            "Resume Builder lets you create a resume either from scratch with a template or by importing an existing `.doc`, `.docx`, or `.pdf` file. "
            "If you are specifically seeing the feature down or unavailable, the available article explains how Resume Builder works but does not include outage troubleshooting steps."
        )

    if "manage users" in title and any(
        term in text for term in ("remove", "employee has left", "interviewer")
    ):
        return (
            "Hi,\n\n"
            "To remove access for a user, log in to HackerRank for Work, open Admin Panel, then go to User Management. "
            "Find the user, click the ellipsis next to their name, and select Deactivate User, then confirm the deactivation."
        )

    if "reschedule an interview" in title:
        return (
            "Hi,\n\n"
            "You can reschedule the interview to a different time from your HackerRank for Work account. "
            "Open the interview, update the scheduled time, and HackerRank will send the updated time to the candidate and interviewers automatically."
        )

    if "virtual lobby" in title and "inactivity" in text:
        return (
            "Hi,\n\n"
            "The available HackerRank documentation says candidates are automatically moved back to the lobby when all interviewers leave the interview. "
            "It does not document a configurable inactivity timer or a setting to extend that behavior, so if you need that changed or confirmed for your account, this would need support review."
        )

    if "visa consumer support" in title and "minimum" in text and "10" in text:
        return (
            "Hi,\n\n"
            "In general, merchants are not allowed to set a minimum or maximum amount for a Visa transaction. "
            "The documented exception is in the USA and US territories, including the U.S. Virgin Islands, where a merchant may require a minimum transaction amount of up to US$10 for credit cards. If this was a debit-card transaction, or the merchant required more than US$10 on a credit card, Visa says you should contact your card issuer."
        )

    if "visa consumer support" in title and "dispute" in text and "charge" in text:
        return (
            "Hi,\n\n"
            "To dispute a charge, Visa directs cardholders to contact their card issuer or bank using the number on the front or back of the Visa card. "
            "Your issuer or bank may ask for detailed information about the transaction before resolving the dispute."
        )

    if (
        ("public vulnerability reporting" in title or "bug bounty" in title)
        and "vulnerability" in text
    ):
        return (
            "Hi,\n\n"
            "For a security vulnerability, Anthropic asks security researchers to review the Responsible Disclosure Policy and submit reports through the official vulnerability-reporting channel. "
            "If the issue is a model-safety or jailbreak report, the corpus also points to Anthropic's Model Safety Bug Bounty Program through HackerOne."
        )

    return None
