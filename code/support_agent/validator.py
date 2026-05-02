from __future__ import annotations

from .models import AgentOutput, VALID_REQUEST_TYPES, VALID_STATUSES


def validate_output(output: AgentOutput) -> AgentOutput:
    status = output.status.lower().strip()
    request_type = output.request_type.lower().strip()
    response = output.response.strip()
    product_area = output.product_area.strip()
    justification = output.justification.strip()

    if status not in VALID_STATUSES:
        status = "escalated"
        justification = _append_reason(
            justification, "Invalid status was corrected to escalated."
        )
    if request_type not in VALID_REQUEST_TYPES:
        request_type = "product_issue"
        justification = _append_reason(
            justification, "Invalid request type was corrected to product_issue."
        )
    if not response:
        response = (
            "Escalate to a human"
            if status == "escalated"
            else "I am sorry, this is out of scope from my capabilities."
        )
    if status == "escalated" and response.lower() != "escalate to a human":
        response = "Escalate to a human"
    if not justification:
        justification = "Validated output after applying schema and safety checks."

    return AgentOutput(
        issue=output.issue,
        subject=output.subject,
        company=output.company,
        response=response,
        product_area=product_area,
        status=status,
        request_type=request_type,
        justification=justification,
    )


def _append_reason(existing: str, addition: str) -> str:
    return f"{existing} {addition}".strip()
