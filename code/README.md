# HackerRank Orchestrate Support Agent

Terminal-based support ticket triage agent for the HackerRank Orchestrate hackathon.

## Setup

```bash
uv sync
```

Secrets must be provided through environment variables or a local `.env` file. Do not commit `.env`.

Optional LLM generation uses:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

If no OpenAI key is present, the agent falls back to deterministic evidence-based response generation.

## Commands

```bash
uv run python code/main.py schema
uv run python code/main.py inspect
uv run python code/main.py show-ticket 1
uv run python code/main.py show-sample 1
uv run python code/main.py run
```

Run without LLM calls:

```bash
uv run python code/main.py run --no-llm
```

The default run command reads `support_tickets/support_tickets.csv` and writes `support_tickets/output.csv`.

## Architecture

```text
CSV input
  -> ticket parser
  -> provisional intent and risk scan
  -> corpus loader and chunker
  -> TF-IDF retriever with metadata boosts
  -> evidence evaluator
  -> post-retrieval intent revision
  -> decision engine
  -> LLM or template response generator
  -> output validator
  -> output.csv
```

The retriever is the core quality layer. It loads markdown support articles from `data/`, preserves metadata such as company, product area, title, breadcrumbs, and source URL, then searches metadata-enriched chunks.

## Safety Policy

The agent escalates when a ticket requires human authority, private account action, security review, fraud/payment handling, legal/compliance judgment, operational investigation, or when retrieved evidence is weak.

The LLM, when enabled, only writes from retrieved evidence. Final schema and safety checks still run after generation.
