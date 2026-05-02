from __future__ import annotations

from .models import RiskSignal, Ticket


HIGH_RISK_PATTERNS = {
    "unauthorized account access": (
        "restore my access",
        "not the workspace owner",
        "not admin",
        "removed my seat",
    ),
    "score or hiring outcome change": (
        "increase my score",
        "move me to the next round",
        "review my answers",
    ),
    "payment dispute or forced refund": (
        "refund me today",
        "ban the seller",
        "chargeback",
    ),
    "security vulnerability": (
        "security vulnerability",
        "bug bounty",
        "exploit",
        "vulnerability",
    ),
    "identity or fraud": (
        "identity has been stolen",
        "identity theft",
        "fraud",
        "stolen card",
    ),
    "destructive or malicious request": (
        "delete all files",
        "rules internal",
        "logic exact",
        "documents retrieved",
    ),
    "broad outage": (
        "site is down",
        "all requests are failing",
        "stopped working completely",
        "none of the submissions",
    ),
    "human security review": (
        "infosec process",
        "filling in the forms",
        "fill in the forms",
        "security questionnaire",
    ),
}

MEDIUM_RISK_PATTERNS = {
    "billing or subscription": (
        "payment",
        "refund",
        "subscription",
        "order id",
        "billing",
    ),
    "privacy or data": (
        "private info",
        "personal data",
        "crawl",
        "crawling",
        "delete my account",
    ),
    "access management": ("remove a user", "employee has left", "remove them", "admin"),
}


def assess_risk(ticket: Ticket) -> RiskSignal:
    text = ticket.query.lower()
    issue_text = ticket.issue.lower()
    if (
        ticket.company is None
        and any(phrase in issue_text for phrase in ("not working", "help", "issue"))
        and len(issue_text.split()) <= 8
    ):
        return RiskSignal(
            "unsupported", ("too little detail for an unsupported company",)
        )

    high_reasons = [
        reason
        for reason, patterns in HIGH_RISK_PATTERNS.items()
        if any(pattern in text for pattern in patterns)
    ]
    if high_reasons:
        return RiskSignal("high", tuple(high_reasons))

    medium_reasons = [
        reason
        for reason, patterns in MEDIUM_RISK_PATTERNS.items()
        if any(pattern in text for pattern in patterns)
    ]
    if medium_reasons:
        return RiskSignal("medium", tuple(medium_reasons))

    if len(text.split()) < 5 and any(
        term in text for term in ("help", "working", "issue")
    ):
        return RiskSignal("unsupported", ("too little detail",))

    return RiskSignal("low", ())
