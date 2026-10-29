# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Recommendation executors: `off`, `noop` (default), and `webhook`. Approve writes `recommendation_audit` (`decided`, `executed`, `execute_failed`). Webhook POSTs only to `PROAGENT_EXECUTOR_WEBHOOK_URL`; the action payload is JSON, not a URL or command. The mock demo marks the monitor recommendation executed without network.
- README scan path for first-time visitors: one-line product description, who it is for, a positioning table, and a harness architecture diagram.
- Scripted mock-demo notes in `docs/DEMO.md` (commands and the output to expect). No API key required.
- This changelog. The `v0.1.0` GitHub Release tag is not published yet; cutting it is tracked in [issue #2](https://github.com/jahonn/ProAgent-OS/issues/2).

## [0.1.0] - 2026-10-29

First public MVP. `pyproject.toml` and `proagent_os.__version__` are `0.1.0`. Early open source: demos, vertical scaffolding, and self-hosted experiments.

### Added

- Agent harness: planner → specialists → aggregator, YAML agent registry, SQLite task and trace memory.
- Commercial surface: FastAPI `/api/v1`, one Bearer API key per tenant, a small web console, and Docker Compose (`api` + `worker` on a shared SQLite volume).
- Private knowledge base: URL/HTML and file ingest (md/txt/html, PDF best-effort), per-tenant BM25 search, brand context, and skill packs. Built-in tools: `http_fetch`, `file_read`, `kb_search`, `clock`, `emit_recommendation`.
- Proactive monitors (`kb_change`, `metric_stub`, `data_source`) that write a recommendation inbox. Approve and reject update status. They do not execute the proposed action.
- Outcome loop: `record_outcome`, tenant-memory feedback, and a simple skill-weight nudge (not a trained policy).
- Native OpenAI-style tool calling with a multi-round specialist loop, plus a JSON-in-content fallback. Planner and aggregator stay text-only. `PROAGENT_LLM_PROVIDER=mock` runs with no API key.
- GitHub Actions CI: `pytest` on Python 3.11 and 3.12 with the mock LLM, and a pull request template.
- Optional `hybrid` and `vector` retrieval using an offline hash-bag stub embedder (`PROAGENT_KB_EMBED_BACKEND=stub`). Default search remains BM25, which is what CI runs. sqlite-vec, pgvector, and remote embedding providers are not wired; the `vec` extra is a placeholder.

[Unreleased]: https://github.com/jahonn/ProAgent-OS/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jahonn/ProAgent-OS/releases/tag/v0.1.0
