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

The default agent path is deterministic and local. OpenAI is opt-in with `--use-llm`; if no OpenAI key is present, the agent uses deterministic evidence-based response and justification generation.

## Commands

```bash
uv run python code/main.py schema
uv run python code/main.py inspect
uv run python code/main.py show-ticket 1
uv run python code/main.py show-sample 1
uv run python code/main.py run
uv run python code/main.py audit
uv run python code/main.py explain 21
```

Optional LLM-assisted response and justification writing:

```bash
uv run python code/main.py run --use-llm
```

The default run command reads `support_tickets/support_tickets.csv` and writes `support_tickets/output.csv` without LLM calls.

## Architecture

```text
CSV input
  -> ticket parser
  -> provisional intent and risk scan
  -> corpus loader and chunker
  -> hybrid retriever
       -> TF-IDF lexical scoring
       -> local SVD vector scoring
       -> grep-style term/phrase evidence scoring
       -> metadata and support-concept boosts
  -> evidence evaluator
  -> post-retrieval intent revision
  -> decision engine
  -> LLM or template response generator
  -> output validator
  -> output.csv
```

The retriever is the core quality layer. It loads markdown support articles from `data/`, preserves metadata such as company, product area, title, breadcrumbs, and source URL, then searches metadata-enriched chunks. The vector layer is fully local and deterministic; it does not send corpus text to an external embedding API.

Use `explain` to inspect one row end to end. It prints intent, risk, evidence, lexical/vector/grep/metadata scores, decision, and final response.

Use `audit` before submission. It checks output schema, escalation formatting, response quality invariants, replied-row evidence strength, same-company evidence alignment, and labeled sample calibration.

## Safety Policy

The agent escalates when a ticket requires human authority, private account action, security review, fraud/payment handling, legal/compliance judgment, operational investigation, or when retrieved evidence is weak.

The LLM, when enabled, only writes from retrieved evidence. Final schema and safety checks still run after generation.
