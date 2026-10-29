# ProAgent OS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/jahonn/ProAgent-OS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jahonn/ProAgent-OS/actions/workflows/ci.yml)
[![GitHub issues](https://img.shields.io/github/issues/jahonn/ProAgent-OS)](https://github.com/jahonn/ProAgent-OS/issues)

**Vertical-agnostic Pro-Agent framework** for building commercial agent products:

| Pillar | Meaning |
|--------|---------|
| **Professional** | Private knowledge base, brand context, skills, tools |
| **Proactive** | Monitors that propose actions; humans approve |
| **Profitable** | Outcomes recorded back into a simple learning loop |

Product name: **ProAgent OS** (`proagent-os`). Original design and code — not affiliated with any third-party agent product.

> Status: **MVP / early open source**. Suitable for demos, scaffolding vertical packs, and self-hosted experiments. See [Roadmap gaps](#roadmap--honest-gaps) before production SaaS use.

## Features

| Layer | Capabilities |
|-------|----------------|
| **Agent Harness** | Planner → Specialists → Aggregator; YAML agent registry; **native OpenAI-style tool calls** (multi-round); SQLite task/trace memory |
| **Professional** | KB ingest (URL/HTML, md/txt/html/pdf best-effort); BM25 retrieval; brand/tenant context; skill packs; MCP-style tools |
| **Proactive** | Interval monitors (`kb_change`, `metric_stub`, `data_source`); recommendation inbox; approve/reject API; APScheduler worker |
| **Profitable** | `record_outcome`; skill weight nudges + tenant memory feedback; dashboard API |
| **Commercial surface** | FastAPI `/api/v1/*`, Bearer API keys per tenant, web console, Docker Compose |

## Quick start (mock LLM — no API keys)

```bash
git clone https://github.com/jahonn/ProAgent-OS.git
cd ProAgent-OS
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

python scripts/demo.py      # end-to-end offline demo → data/demo.db

export PROAGENT_ADMIN_KEY=dev-admin-key
export PROAGENT_LLM_PROVIDER=mock
export PROAGENT_DB_PATH=./data/proagent.db
uvicorn proagent_os.main:app --host 0.0.0.0 --port 8080

# optional proactive worker
python -m proagent_os.worker
```

Open http://localhost:8080 — paste a tenant API key (from the demo or `POST /api/v1/tenants`). API docs: `/docs`.

### Create a tenant (admin)

```bash
curl -s -X POST http://localhost:8080/api/v1/tenants \
  -H "Authorization: Bearer dev-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme","goals":"Grow conversion","tone":"concise"}'
```

Use the returned `api_key` as `Authorization: Bearer …` for tenant APIs.

## Real LLM (OpenAI-compatible)

Any OpenAI-compatible `/v1/chat/completions` endpoint works (OpenAI, Xiaomi Mimo Token Plan, DeepSeek, vLLM, etc.).

```bash
cp .env.example .env
# edit .env — never commit it

export PROAGENT_LLM_PROVIDER=openai
export PROAGENT_LLM_BASE_URL=https://api.openai.com/v1   # or your /v1 endpoint
export PROAGENT_LLM_API_KEY=sk-...
export PROAGENT_LLM_MODEL=gpt-4o-mini
export PROAGENT_MAX_TOOL_ROUNDS=8

python scripts/demo_live.py   # prints multi-round tool traces
```

Specialists use native `tools` / `tool_calls` (JSON-in-content fallback still supported). Planner and aggregator stay text-only.

## Docker Compose

```bash
export PROAGENT_ADMIN_KEY=dev-admin-key
docker compose up --build
```

- API/UI: http://localhost:8080  
- Services: `api` + `worker` sharing a SQLite volume

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PROAGENT_ADMIN_KEY` | `dev-admin-key` | Bootstrap / list tenants |
| `PROAGENT_DB_PATH` | `./data/proagent.db` | SQLite path |
| `PROAGENT_LLM_PROVIDER` | `mock` | `mock` or `openai` (OpenAI-compatible) |
| `PROAGENT_LLM_BASE_URL` | `https://api.openai.com/v1` | Compatible `/v1` base |
| `PROAGENT_LLM_API_KEY` | empty | Bearer token; empty → mock fallback |
| `PROAGENT_LLM_MODEL` | `gpt-4o-mini` | Model id |
| `PROAGENT_MAX_TOOL_ROUNDS` | `8` | Max tool rounds per specialist |
| `PROAGENT_SKILLS_DIRS` | `./skills,./verticals/example/skills` | Skill pack roots |
| `PROAGENT_AGENTS_CONFIG` | `./config/agents.yaml` | Core agent registry |

## Architecture

```
proagent-os/
├── proagent_os/
│   ├── main.py              # FastAPI app + web UI
│   ├── worker.py            # Proactive scheduler process
│   ├── harness/             # Orchestrator, registry, memory
│   ├── llm/                 # mock + OpenAI-compatible + tool_calls
│   ├── professional/        # KB, skills, tools, brand
│   ├── proactive/           # Monitors, recommendations, scheduler
│   ├── profitable/          # Metrics + learning stub
│   ├── api/                 # REST /api/v1/*
│   └── web/                 # Console UI
├── config/agents.yaml
├── skills/
├── verticals/example/       # How to add a vertical without core changes
├── scripts/demo.py · demo_live.py
├── tests/
└── docker-compose.yml
```

**Built-in tools:** `http_fetch` · `file_read` · `kb_search` · `clock` · `emit_recommendation`  

**Core agents:** `planner` · `researcher` · `analyst` · `aggregator` (+ vertical agents from `verticals/*/agents/`)

## Add a vertical pack

1. Create `verticals/<your_vertical>/agents/agents.yaml`
2. Add `verticals/<your_vertical>/skills/<id>/SKILL.md` (optional `run.py`)
3. Append the skills path to `PROAGENT_SKILLS_DIRS`
4. Restart API/worker — no core code changes required

See `verticals/example/` (`market_scout` + `market_scan`).

## API overview

- `POST /api/v1/tenants` (admin) · `GET /api/v1/tenants/me`
- `GET /api/v1/agents` · `GET /api/v1/agents/tools`
- `POST /api/v1/tasks` · `GET /api/v1/tasks/{id}`
- `POST /api/v1/kb/ingest/url|text|file` · `POST /api/v1/kb/search`
- `GET /api/v1/skills` · `POST /api/v1/skills/{id}/invoke`
- `POST /api/v1/monitors` · `POST /api/v1/monitors/{id}/run`
- `GET /api/v1/recommendations` · `POST .../approve|reject|decide`
- `POST /api/v1/metrics/outcomes` · `GET /api/v1/dashboard`

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

## Contributing

1. Fork and create a feature branch
2. Keep changes focused; add/adjust tests when behavior changes
3. Do **not** commit `.env`, API keys, or tenant databases
4. Open a PR against `main`

Bug reports and feature ideas: use [GitHub Issues](https://github.com/jahonn/ProAgent-OS/issues) (templates provided).

## Roadmap / honest gaps

- Production vector search (pgvector / sqlite-vec), not only BM25
- OAuth / SSO, RBAC, audit log, rate limits
- Multi-node deploy, migrations, backups (beyond single SQLite)
- Recommendation **executors** (today approve is status-only)
- Real evaluation harness (learning loop is score nudges)
- Billing, metering, OpenTelemetry
- Richer product UI / i18n

## Security

- Never commit `.env` or API keys
- Rotate any key that was pasted into chat or logs
- Treat recommendation approve/execute as privileged actions in production

## License

MIT — see [LICENSE](LICENSE).
