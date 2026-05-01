from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Sequence

from agent import run_pipeline


REPO_ROOT = Path(__file__).resolve().parents[1]
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


def run_agent(input_path: Path, output_path: Path, data_dir: Path, use_llm: bool) -> int:
    outputs = run_pipeline(input_path, output_path, data_dir, use_llm=use_llm)
    print(f"Wrote output for {len(outputs)} tickets to {output_path}")
    return 0


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

    sample_parser = subparsers.add_parser("show-sample", help="Print one labeled sample row.")
    sample_parser.add_argument("row", type=int, help="1-based row number.")
    sample_parser.add_argument("--input", type=Path, default=DEFAULT_SAMPLE)

    subparsers.add_parser("schema", help="Print expected input/output schema.")

    run_parser = subparsers.add_parser("run", help="Run the agent on the input CSV.")
    run_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    run_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    run_parser.add_argument("--no-llm", action="store_true", help="Disable optional OpenAI response generation.")

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
        return run_agent(args.input, args.output, args.data_dir, use_llm=not args.no_llm)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
