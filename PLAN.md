# HackerRank Orchestrate Project Plan

## Current Status

- CLI scaffold exists in `code/cli.py`.
- `code/main.py` delegates to the CLI entry point.
- The first real agent pipeline is implemented with deterministic retrieval, decisioning, validation, and optional LLM generation.
- `uv` is the selected Python dependency and virtual environment manager.
- The final required output is `support_tickets/output.csv`.
- The visible final ticket set has 29 rows: 14 HackerRank, 7 Claude, 6 Visa, and 2 with `Company=None`.
- The local corpus has 774 markdown files across `data/hackerrank`, `data/claude`, and `data/visa`.
- The solution should optimize for a reliable batch CSV generator, not a polished chatbot or heavyweight platform.

## Product Goal And Evaluation Target

- Build a terminal-based support triage agent for HackerRank Orchestrate.
- Read `support_tickets/support_tickets.csv` and write predictions to `support_tickets/output.csv`.
- Use only the local corpus in `data/` as the source of truth.
- Score well on:
  - correct `Status`: `Replied` or `Escalated`;
  - correct `Product Area`;
  - grounded user-facing `Response`;
  - concise `Justification`;
  - correct `Request Type`: `product_issue`, `feature_request`, `bug`, or `invalid`.
- Submission requires:
  - zipped `code/` directory;
  - populated `support_tickets/output.csv`;
  - shared chat transcript at `$HOME/hackerrank_orchestrate/log.txt`.
- Add `code/README.md` before submission with setup, run commands, architecture, and limitations.

## Operating Rules

- If implementation discovers an issue that requires changing this plan materially, stop and discuss the change before proceeding.
- Do not hardcode secrets. Read API keys from environment variables, with `.env` support through `python-dotenv`.
- Prefer deterministic, explainable logic before LLM judgment.
- Escalate when the system lacks strong evidence, faces sensitive authority boundaries, or would need to guess.
- Keep dependency and runtime setup simple enough for submission and judge review.

## Target Architecture

```text
CSV input
  -> ticket parser
  -> provisional intent and risk scan
  -> corpus loader and chunker
  -> hybrid retriever
  -> evidence evaluator
  -> post-retrieval intent revision
  -> decision engine
  -> LLM response generator
  -> output validator
  -> output.csv
```

Core modules planned under `code/`:

- `models.py`: shared dataclasses and enums.
- `corpus.py`: markdown loading, metadata extraction, cleanup, and chunking.
- `retriever.py`: TF-IDF retrieval, optional vector retrieval, metadata boosts, and reranking.
- `classifier.py`: provisional and post-retrieval request type classification. Early intent is a signal, not a final decision.
- `risk.py`: escalation risk signals for sensitive, unsupported, and ambiguous tickets.
- `decision.py`: final status, request type, product area, and answerability decision.
- `generator.py`: grounded LLM response generation from retrieved evidence.
- `validator.py`: schema, enum, and safety validation before CSV writing.
- `cli.py`: terminal commands for running and debugging the agent.

## Terminal Interface

- Treat "terminal-based" as a runnable command-line program, not necessarily an interactive CLI product.
- `code/main.py` remains the submission-friendly entry point.
- `code/cli.py` remains the developer/debug interface.
- Keep these commands working throughout development:

```bash
python3 code/main.py schema
uv run python code/main.py inspect
uv run python code/main.py show-ticket 1
uv run python code/main.py show-sample 1
uv run python code/main.py run
```

The `run` command must eventually execute the real pipeline and write `support_tickets/output.csv`.

## Milestones

- [x] Add CLI scaffold for schema, inspect, ticket viewing, and run command.
- [x] Add `uv` project metadata and Python version file.
- [x] Define dataclasses and parser.
- [x] Build corpus preprocessing and token-aware chunking approximation.
- [x] Build hybrid retriever with TF-IDF first.
- [ ] Add optional in-memory embedding vector search.
- [x] Add provisional intent and risk evaluation.
- [x] Add decision engine with evidence thresholds.
- [x] Add LLM response generator.
- [x] Add output validator and CSV writer.
- [x] Run against sample tickets and inspect failures.
- [x] Run against final support tickets and produce `support_tickets/output.csv`.
- [x] Write `code/README.md` with setup, run commands, architecture, and limitations.

## Dependency Plan

- Use `uv` as the only Python dependency and virtual environment manager.
- Use Python 3.11 through `.python-version`.
- Runtime dependencies:
  - `numpy`
  - `scikit-learn`
  - `openai`
  - `python-dotenv`
- Dev/test dependency:
  - `pytest`
- Do not add Chroma, Weaviate, Postgres, pgvector, FAISS, or Hugging Face reranker until the core pipeline works and there is a concrete need.
- If vector embeddings are added, store them as an in-memory `numpy` matrix with a local cache, not a vector database.

## Data Model Plan

- Represent every input row as a `Ticket` dataclass:
  - row id;
  - issue;
  - subject;
  - company;
  - normalized query text.
- Represent every support document and chunk with metadata-rich dataclasses:
  - `doc_id`;
  - `chunk_id`;
  - company;
  - product area;
  - title;
  - breadcrumbs;
  - source URL;
  - file path;
  - heading path;
  - chunk index;
  - previous and next chunk ids;
  - cleaned text.
- Represent retrieval results with:
  - chunk;
  - lexical score;
  - vector score if available;
  - metadata boost;
  - final score;
  - explanation of why the chunk matched.

## Retriever Plan

- Treat retrieval as the core quality layer.
- Parse markdown frontmatter and infer metadata from file paths.
- Store chunk metadata: company, product area, title, breadcrumbs, source URL, file path, heading, chunk index, and neighboring chunk IDs.
- Prefer token-aware chunks around 250-450 tokens with 40-80 token overlap.
- If a tokenizer is unavailable, approximate token counts by characters or words and keep the fallback deterministic.
- Preserve document structure where possible: title, breadcrumbs, H2/H3 section headings, paragraph/list content.
- Prepend useful metadata to chunk search text, such as company, product area, title, breadcrumbs, and heading.
- Use TF-IDF lexical retrieval as the reliable baseline.
- Add vector search with cached in-memory embeddings after the baseline works.
- Use hybrid retrieval:
  - TF-IDF top candidates;
  - vector top candidates if embeddings are available;
  - merge candidates;
  - apply metadata boosts;
  - rerank final candidates.
- Use metadata boosts for company, title, and product area matches, but do not train scoring weights from the 10-row sample because it would overfit.
- Use manually tuned weights first, with company matching acting as a strong filter when `Company` is known.
- If `Company` is known, search that company first; if evidence is weak, fall back to all-company retrieval and mark ambiguity risk.
- If `Company=None`, search all companies and infer company/product area from the strongest evidence cluster.
- Use reranking as an optional improvement, with deterministic fallback.
- Escalate when evidence is weak instead of answering from a poor match.
- Retrieval must return enough evidence for response generation and justification, not just a best file path.

## Intent And Risk Plan

- Do not let the first intent classifier decide the final label.
- Use a lifecycle:
  1. pre-retrieval provisional intent signal;
  2. retrieval;
  3. post-retrieval intent revision from evidence;
  4. final decision.
- Provisional intent should include candidate labels and confidence, not only one hard label.
- Intent rule examples:
  - `feature_request`: "can you add", "would like", "support for", "enhancement";
  - `bug`: "site is down", "not working", "error", "crash", "cannot access", "broken";
  - `invalid`: clearly unrelated to HackerRank, Claude, or Visa support;
  - `product_issue`: normal how-to, account, billing, configuration, or product behavior.
- Risk levels:
  - `low`: normal FAQ/how-to with strong corpus evidence;
  - `medium`: account, billing, privacy, or access topic with safe documented user steps;
  - `high`: requires human authority, private account action, security review, fraud handling, legal/compliance judgment, or operational investigation;
  - `unsupported`: no strong corpus evidence.
- Escalate examples:
  - restore access without admin/owner authorization;
  - platform outage or broad service failure;
  - fraud, stolen card/payment instrument, suspicious transaction, or payment dispute;
  - legal, compliance, security vulnerability, or identity verification;
  - ambiguous request with weak evidence.
- Safe reply examples:
  - delete or rename a Claude conversation when the corpus provides steps;
  - explain HackerRank test expiration when the corpus provides behavior;
  - answer Visa traveller's cheque issuer instructions when the corpus provides contact guidance.

## Decision Engine Plan

- Use deterministic evaluators instead of multiple personality agents.
- Evaluators:
  - scope evaluator;
  - evidence evaluator;
  - risk evaluator;
  - intent evaluator;
  - answerability evaluator.
- Final policy:
  - `invalid` and unrelated: usually `Replied` with an out-of-scope response;
  - high-risk: `Escalated`;
  - outage/platform-wide bug: `Escalated`;
  - weak evidence: `Escalated`;
  - strong evidence and low/medium risk: `Replied`.
- Product area should come from corpus metadata when possible, not free-form guessing.
- Multi-agent voting with five personality agents is intentionally deferred because it is less deterministic, harder to debug, and harder to defend in the judge interview.

## LLM Generation Plan

- Prefer option B: LLM-assisted response generation.
- LLM should generate the response from retrieved evidence, but should not be the only safety authority.
- Prompt inputs:
  - ticket;
  - final decision;
  - top retrieved evidence chunks;
  - allowed schema values;
  - instruction to use only provided evidence;
  - instruction to escalate if evidence is insufficient.
- Expected output should be structured JSON or a dataclass-compatible object before CSV writing.
- `validator.py` must be able to override unsafe or malformed LLM output.
- Do not invent links, phone numbers, product policies, or operational guarantees unless present in retrieved evidence.

## Debug And Run Commands

```bash
python3 code/main.py schema
uv run python code/main.py inspect
uv run python code/main.py show-ticket 1
uv run python code/main.py show-sample 1
uv run python code/main.py run
```

## Testing And Review Plan

- Smoke tests:
  - `uv sync`;
  - `uv run python code/main.py schema`;
  - `uv run python code/main.py inspect`;
  - `uv run python code/main.py show-ticket 1`;
  - `uv run python code/main.py show-sample 1`.
- Pipeline tests:
  - parser preserves row count and order;
  - output writer emits exactly one output row per input row;
  - validator rejects invalid enum values;
  - known sample rows classify correctly where rules are obvious.
- Retrieval tests:
  - ticket about HackerRank test expiration retrieves Screen/test settings docs;
  - Claude conversation deletion retrieves conversation management docs;
  - Visa traveller's cheques retrieves Visa traveller cheque docs;
  - unrelated Iron Man-style question is treated as invalid/out-of-scope.
- Manual review:
  - inspect all 29 final ticket outputs before submission;
  - check every `Replied` row has clear corpus support;
  - check every `Escalated` row has a concise justification.

## Risks

- Weak retrieval can cause hallucinated or unsupported responses.
- Early intent classification can incorrectly constrain the final decision.
- Runtime dependency or model downloads may fail during evaluation.
- LLM output can violate schema or safety rules without validation.
- Product area guesses can drift unless tied to corpus metadata.
- Vector search may improve semantic matching, but external model downloads can create submission risk.
- The 10 labeled sample rows are useful for calibration, not enough for training a scoring model.

## Acceptance Criteria

- `support_tickets/output.csv` has one output row per input ticket.
- All output enum values are valid.
- High-risk, sensitive, unsupported, and ambiguous cases are escalated.
- Replied responses are grounded in retrieved corpus evidence.
- The terminal command runs reproducibly with `uv`.
- `code/README.md` explains setup, run commands, architecture, and limitations.
- The final system remains explainable for the AI judge interview.
