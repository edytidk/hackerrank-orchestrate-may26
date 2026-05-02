# HackerRank Orchestrate Support Agent

This folder contains a terminal-based support-ticket agent for the HackerRank Orchestrate challenge. The agent reads support tickets, searches the provided local support corpus, decides whether it is safe to answer, and writes the required `support_tickets/output.csv`.

The design goal is simple: answer only when the local corpus supports the answer; otherwise escalate to a human.

## Why This Project Is Strong

- **Deterministic by default:** `uv run python main.py run` uses the local corpus and deterministic rules. It does not call an LLM unless `--use-llm` is explicitly passed.
- **Grounded in the provided corpus:** answers come from the markdown files under `data/`, not from live web search or model memory.
- **Hybrid retrieval:** combines lexical search, local vector search, grep-style evidence scoring, and metadata boosts.
- **Safety-first decisioning:** high-risk, sensitive, unsupported, or authority-sensitive tickets escalate instead of guessing.
- **Detailed justifications:** the `justification` column explains why the agent replied or escalated, including risk and evidence.
- **Explainable CLI:** `explain` shows intent, risk, retrieval scores, decision, justification, and response for any ticket row.
- **Release audit:** `audit` checks output quality, schema validity, evidence strength, and sample calibration.

## Quickstart

Run commands from inside this `code/` directory.

Prerequisites:

- Python 3.11
- `uv`
- the provided `data/` and `support_tickets/` folders next to `code/` in the parent directory during local development/evaluation

Enter the code directory:

```bash
cd code
```

Install dependencies and create the virtual environment from the files included in this folder:

```bash
uv sync
```

No API key is required for the default submission path.

Optional OpenAI-assisted response and justification writing can be enabled with a local `.env` file in this `code/` directory or the repo root:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

Do not commit `.env`.

Run the deterministic submission pipeline:

```bash
uv run python main.py run
```

This reads:

```text
../support_tickets/support_tickets.csv
```

and writes:

```text
../support_tickets/output.csv
```

## Main Commands

```bash
uv run python main.py schema
uv run python main.py inspect
uv run python main.py show-ticket 1
uv run python main.py show-sample 1
uv run python main.py run
uv run python main.py audit
uv run python main.py explain 21
```

Optional LLM-assisted response and justification writing:

```bash
uv run python main.py run --use-llm
```

For the judged submission, prefer the default deterministic command:

```bash
uv run python main.py run
```

## High-Level Architecture

```text
CSV ticket
  -> ticket parser
  -> intent classifier
  -> risk scanner
  -> corpus preprocessing
  -> hybrid retriever
       -> TF-IDF lexical scoring
       -> local SVD vector scoring
       -> grep-style term/phrase evidence scoring
       -> metadata and support-concept boosts
  -> decision engine
  -> response generator
  -> justification generator
  -> output validator
  -> output.csv
```

## Module Guide

- `main.py`
  Evaluator-facing entrypoint. It loads the CLI from `support_agent.cli`.

- `support_agent/agent.py`
  Pipeline orchestrator. It runs parsing, classification, risk, retrieval, decisioning, response generation, justification generation, and validation.

- `support_agent/corpus.py`
  Loads and preprocesses markdown support documents from `data/`.

- `support_agent/retriever.py`
  Core retrieval layer. It builds local search indexes and returns ranked support evidence.

- `support_agent/classifier.py`
  Classifies request type: `product_issue`, `feature_request`, `bug`, or `invalid`.

- `support_agent/risk.py`
  Detects sensitive or high-risk tickets, such as refunds, fraud, account access, score changes, outages, and security review.

- `support_agent/decision.py`
  Decides whether to reply or escalate.

- `support_agent/generator.py`
  Writes the user-facing response from retrieved evidence.

- `support_agent/justification.py`
  Writes detailed justifications for the output CSV.

- `support_agent/validator.py`
  Enforces valid output schema and fixed escalation response formatting.

- `support_agent/evaluation.py`
  Implements the internal release audit and sample calibration checks.

- `support_agent/cli.py`
  Provides terminal commands for running, inspecting, explaining, and auditing the agent.

## Document Preprocessing

Preprocessing happens automatically when the agent starts. There is no separate manual preprocessing command.

When you run:

```bash
uv run python main.py run
```

the agent:

1. Finds all markdown files under `data/`.
2. Reads frontmatter metadata such as title, breadcrumbs, source URL, and product area.
3. Cleans markdown text by removing images, comments, markdown links, and noisy formatting.
4. Splits documents into sections based on headings.
5. Chunks long sections into overlapping text chunks.
6. Links neighboring chunks from the same document.
7. Builds retrieval indexes in memory.

Current measured preprocessing/indexing time on this repo:

```text
chunks: 6494
document parsing and chunking: ~0.23 seconds
retriever index build: ~9.65 seconds
total startup: ~9.88 seconds
```

Most startup time is not document cleaning. It is building the retrieval index, especially the local vector/SVD layer.

The preprocessing is in-memory. It does not write a vector database, cache, or external index. This keeps the submission simple and reproducible.

## Retrieval Design

The retriever is the most important quality layer.

It uses:

- **TF-IDF lexical search** for exact support words and product terms.
- **Local SVD vector search** for meaning-like similarity without external embeddings.
- **Character n-gram features** to handle spelling variation and noisy tickets.
- **Grep-style evidence scoring** for important ticket terms and phrases.
- **Metadata boosts** for same company, product area, title overlap, headings, and support concepts.

This gives us strong retrieval without sending the corpus to OpenAI, Chroma, Weaviate, Postgres, or any remote service.

## Safety And Escalation

The agent escalates when the case is risky or unsupported.

Examples:

- unauthorized account access
- score or hiring-outcome changes
- payment disputes or refund demands
- identity theft or fraud
- security questionnaire / infosec review
- broad outage reports
- vague tickets with too little detail
- requests that need recruiter, admin, bank, or human authority

Escalation is not treated as failure. In this challenge, escalation is the correct behavior when the agent should not guess.

## Justification Design

The `justification` column is generated after the decision step.

For escalated rows, it explains:

- the concrete escalation reason,
- the risk level,
- the top retrieved evidence when available,
- why a human should review before any resolution is given.

For replied rows, it explains:

- why the retrieved corpus evidence was strong enough,
- which source matched,
- why the response is grounded.

Optional LLM justification rewriting exists through `--use-llm`, but the default submitted output is deterministic.

## Determinism And Reproducibility

The default pipeline is deterministic:

- no LLM call by default,
- no live web call,
- local corpus only,
- dependencies pinned by `uv.lock`,
- local SVD has `random_state=42`,
- fixed validation rules,
- fixed output schema.

Use this command for reproducible submission output:

```bash
uv run python main.py run
```

## Evaluation Criteria Alignment

### Agent Design

The system has clear separation of concerns:

- retrieval,
- risk,
- decisioning,
- response generation,
- justification,
- validation,
- audit.

This makes the agent easier to explain and debug.

### Use Of Provided Corpus

The default pipeline uses only the local `data/` corpus. Responses are grounded in retrieved support documents.

### Escalation Logic

The agent has explicit safety rules for high-risk, sensitive, unsupported, ambiguous, and authority-sensitive tickets.

### Determinism

The judged path is deterministic by default. Optional OpenAI usage is opt-in, not part of the default submission run.

### Engineering Hygiene

Secrets are read from environment variables only. `.env` is local and should not be committed. The code is organized into small modules and tested with `pytest`.

### Output CSV Quality

The `audit` command checks:

- valid status values,
- valid request types,
- nonblank responses,
- nonblank justifications,
- exact escalation response text,
- no low-signal article junk,
- replied rows have evidence,
- sample calibration.

## Verification Commands

Run these before submission:

```bash
uv run python main.py run
uv run python main.py audit
uv run pytest ../tests -q
```

Useful manual inspection commands:

```bash
uv run python main.py inspect
uv run python main.py show-ticket 1
uv run python main.py show-sample 1
uv run python main.py explain 21
```

Expected current state:

```text
audit: passed
tests: 12 passed with `uv run pytest ../tests -q`
sample calibration: 10/10 status, 10/10 request_type, 10/10 product_area
```

## Submission Packaging

Upload a zip of this `code/` directory only. Do not include `data/`, `support_tickets/`, virtual environments, caches, or generated bytecode.

From the repository root:

```bash
zip -r code.zip code \
  -x "code/.venv/*" \
  -x "code/__pycache__/*" \
  -x "code/support_agent/__pycache__/*" \
  -x "*.pyc"
```

## Judge Interview Talking Point

Short version:

> This is a deterministic, corpus-grounded, safety-first support agent. It uses hybrid local retrieval to find evidence, policy-aware decisioning to decide reply vs escalation, grounded response generation, detailed justifications, and validation/audit tooling to keep the final CSV reliable.
