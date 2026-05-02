from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path

from .agent import SupportAgent, read_tickets, run_pipeline
from .evaluation import audit_input, compare_sample_labels


CODE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = next(
    (
        candidate
        for candidate in (CODE_ROOT.parent, CODE_ROOT)
        if (candidate / "data").exists() or (candidate / "support_tickets").exists()
    ),
    CODE_ROOT.parent,
)
DEFAULT_INPUT = REPO_ROOT / "support_tickets" / "support_tickets.csv"
DEFAULT_SAMPLE = REPO_ROOT / "support_tickets" / "sample_support_tickets.csv"
DEFAULT_OUTPUT = REPO_ROOT / "support_tickets" / "output.csv"
DEFAULT_DATA = REPO_ROOT / "data"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def inspect_csv(path: Path) -> int:
    rows = read_rows(path)
    print(f"File: {path}")
    print(f"Rows: {len(rows)}")
    if not rows:
        print("Columns: <none>")
        return 0

    print(f"Columns: {', '.join(rows[0].keys())}")
    companies: dict[str, int] = {}
    for row in rows:
        company = (row.get("Company") or "None").strip() or "None"
        companies[company] = companies.get(company, 0) + 1

    print("Companies:")
    for company, count in sorted(companies.items()):
        print(f"  {company}: {count}")
    return 0


def show_ticket(path: Path, row_number: int) -> int:
    rows = read_rows(path)
    if row_number < 1 or row_number > len(rows):
        raise SystemExit(f"row must be between 1 and {len(rows)}")

    row = rows[row_number - 1]
    print(f"File: {path}")
    print(f"Row: {row_number}")
    for key, value in row.items():
        print(f"\n{key}:")
        print((value or "").strip())
    return 0


def print_schema() -> int:
    print("Input columns:")
    print("  Issue")
    print("  Subject")
    print("  Company")
    print()
    print("Required output columns:")
    print("  issue")
    print("  subject")
    print("  company")
    print("  response")
    print("  product_area")
    print("  status: replied | escalated")
    print("  request_type: product_issue | feature_request | bug | invalid")
    print("  justification")
    return 0


def run_agent(
    input_path: Path, output_path: Path, data_dir: Path, use_llm: bool
) -> int:
    outputs = run_pipeline(input_path, output_path, data_dir, use_llm=use_llm)
    print(f"Wrote output for {len(outputs)} tickets to {output_path}")
    return 0


def explain_ticket(
    input_path: Path, data_dir: Path, row_number: int, use_llm: bool
) -> int:
    tickets = read_tickets(input_path)
    if row_number < 1 or row_number > len(tickets):
        raise SystemExit(f"row must be between 1 and {len(tickets)}")

    trace = SupportAgent(data_dir=data_dir, use_llm=use_llm).trace(
        tickets[row_number - 1]
    )
    output = trace.output

    print(f"File: {input_path}")
    print(f"Row: {row_number}")
    print(f"Company: {trace.ticket.company or 'None'}")
    print(f"Subject: {trace.ticket.subject}")
    print(f"Issue: {trace.ticket.issue}")
    print()
    print("Intent:")
    print(f"  candidates: {', '.join(trace.intent.candidates)}")
    print(f"  confidence: {trace.intent.confidence:.2f}")
    print(f"  reason: {trace.intent.reason}")
    print()
    print("Risk:")
    print(f"  level: {trace.risk.level}")
    print(f"  reasons: {', '.join(trace.risk.reasons) or '<none>'}")
    print()
    print("Top evidence:")
    for index, result in enumerate(trace.evidence[:5], 1):
        chunk = result.chunk
        print(
            f"  {index}. {chunk.company} | {chunk.product_area or '<blank>'} | {chunk.title}"
        )
        print(
            "     "
            f"final={result.final_score:.3f} "
            f"lexical={result.lexical_score:.3f} "
            f"vector={result.vector_score:.3f} "
            f"grep={result.grep_score:.3f} "
            f"metadata={result.metadata_boost:.3f}"
        )
        print(f"     reason: {result.reason}")
    print()
    print("Decision:")
    print(f"  status: {output.status}")
    print(f"  request_type: {output.request_type}")
    print(f"  product_area: {output.product_area or '<blank>'}")
    print(f"  justification: {output.justification}")
    print()
    print("Response:")
    print(output.response)
    return 0


def audit_agent(input_path: Path, data_dir: Path, sample_path: Path | None) -> int:
    result = audit_input(input_path=input_path, data_dir=data_dir, use_llm=False)
    print(f"Rows: {result.rows}")
    print(f"Status counts: {_format_counts(result.status_counts)}")
    print(f"Request type counts: {_format_counts(result.request_type_counts)}")
    print(f"Product area counts: {_format_counts(result.product_area_counts)}")
    if sample_path:
        sample = compare_sample_labels(sample_path, data_dir)
        print(
            "Sample calibration: "
            f"status={sample['status']}/{sample['rows']}, "
            f"request_type={sample['request_type']}/{sample['rows']}, "
            f"product_area={sample['product_area']}/{sample['rows']}"
        )

    if result.issues:
        print("Issues:")
        for issue in result.issues:
            print(f"  - {issue}")
        return 1

    print("Audit: passed")
    return 0


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) or "<none>"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Debug and run the HackerRank Orchestrate support agent."
    )
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Summarize a ticket CSV.")
    inspect_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    show_parser = subparsers.add_parser("show-ticket", help="Print one ticket row.")
    show_parser.add_argument("row", type=int, help="1-based row number.")
    show_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    sample_parser = subparsers.add_parser(
        "show-sample", help="Print one labeled sample row."
    )
    sample_parser.add_argument("row", type=int, help="1-based row number.")
    sample_parser.add_argument("--input", type=Path, default=DEFAULT_SAMPLE)

    subparsers.add_parser("schema", help="Print expected input/output schema.")

    run_parser = subparsers.add_parser("run", help="Run the agent on the input CSV.")
    run_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    run_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    run_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Compatibility flag; deterministic local generation is already the default.",
    )
    run_parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable optional OpenAI response and justification generation.",
    )

    explain_parser = subparsers.add_parser(
        "explain", help="Show pipeline signals and retrieval evidence for one row."
    )
    explain_parser.add_argument("row", type=int, help="1-based row number.")
    explain_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    explain_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    explain_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Compatibility flag; deterministic local generation is already the default.",
    )
    explain_parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable optional OpenAI response and justification generation.",
    )

    audit_parser = subparsers.add_parser(
        "audit", help="Run release-quality structural checks over generated answers."
    )
    audit_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    audit_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    audit_parser.add_argument(
        "--sample",
        type=Path,
        default=DEFAULT_SAMPLE,
        help="Optional labeled sample CSV for calibration reporting.",
    )
    audit_parser.add_argument(
        "--no-sample",
        action="store_true",
        help="Skip labeled sample calibration reporting.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return inspect_csv(args.input)
    if args.command == "show-ticket":
        return show_ticket(args.input, args.row)
    if args.command == "show-sample":
        return show_ticket(args.input, args.row)
    if args.command == "schema":
        return print_schema()
    if args.command == "run":
        return run_agent(
            args.input, args.output, args.data_dir, use_llm=args.use_llm
        )
    if args.command == "explain":
        return explain_ticket(
            args.input, args.data_dir, args.row, use_llm=args.use_llm
        )
    if args.command == "audit":
        return audit_agent(
            args.input,
            args.data_dir,
            sample_path=None if args.no_sample else args.sample,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
