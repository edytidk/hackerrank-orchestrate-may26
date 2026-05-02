from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load_main():
    return import_module("support_agent.cli").main


if __name__ == "__main__":
    raise SystemExit(_load_main()())
