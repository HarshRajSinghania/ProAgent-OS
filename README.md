# ProAgent OS

**Vertical-agnostic Pro-Agent framework** for commercial products:  
**Professional** knowledge & skills · **Proactive** monitors & human-in-the-loop recommendations · **Profitable** outcome / learning loop.

Product name: **ProAgent OS** (`proagent-os`). Original design and code — not affiliated with any third-party agent product.

## What you get

| Layer | Capabilities |
|-------|----------------|
| **Agent Harness** | Planner → Specialists → Aggregator; YAML agent registry; tool calls; SQLite task/trace memory |
| **Professional** | KB ingest (URL/HTML, md/txt/html/pdf best-effort); BM25 retrieval; brand/tenant context; skill packs; MCP-style tools |
| **Proactive** | Interval monitors (`kb_change`, `metric_stub`, `data_source`); recommendation inbox; approve/reject API; APScheduler worker |
| **Profitable** | `record_outcome`; skill weight nudges + tenant memory feedback; dashboard API |
| **Commercial surface** | FastAPI `/api/v1/*`, Bearer API keys per tenant, Jinja+HTMX-style SPA console, Docker Compose |

## Quick start (local, mock LLM — no API keys)

```bash
cd proagent-os
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# End-to-end demo (creates data/demo.db)
python scripts/demo.py

# API + UI
export PROAGENT_ADMIN_KEY=dev-admin-key
export PROAGENT_LLM_PROVIDER=mock
export PROAGENT_DB_PATH=./data/proagent.db
uvicorn proagent_os.main:app --host 0.0.0.0 --port 8080

# Optional proactive worker (separate process)
python -m proagent_os.worker
```

Open http://localhost:8080 — paste a tenant API key (from the demo or `POST /api/v1/tenants`).

### Create a tenant (admin)

```bash
curl -s -X POST http://localhost:8080/api/v1/tenants \
  -H "Authorization: Bearer dev-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme","goals":"Grow conversion","tone":"concise"}'
```

Use the returned `api_key` as `Authorization: Bearer …` for all tenant APIs.

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
| `PROAGENT_LLM_PROVIDER` | `mock` | `mock` (offline) or `openai` (OpenAI-compatible `/v1/chat/completions`) |
| `PROAGENT_LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible APIs (vLLM, Ollama compat, proxies, etc.) |
| `PROAGENT_LLM_API_KEY` | empty | Bearer token. If empty while `openai` is selected, factory falls back to mock |
| `PROAGENT_LLM_MODEL` | `gpt-4o-mini` | Model id sent in the chat payload |
| `PROAGENT_MAX_TOOL_ROUNDS` | `8` | Max native tool-calling rounds per specialist |
| `PROAGENT_SKILLS_DIRS` | `./skills,./verticals/example/skills` | Skill pack roots |
| `PROAGENT_AGENTS_CONFIG` | `./config/agents.yaml` | Core agent registry |

### Enable a real LLM

```bash
export PROAGENT_LLM_PROVIDER=openai
export PROAGENT_LLM_BASE_URL=https://api.openai.com/v1   # or your compatible endpoint
export PROAGENT_LLM_API_KEY=sk-...                       # do not commit
export PROAGENT_LLM_MODEL=gpt-4o-mini
export PROAGENT_MAX_TOOL_ROUNDS=8
python scripts/demo_live.py   # prints tool-round traces
```

Specialists use **native OpenAI-style `tools` / `tool_calls`** (with JSON-in-content fallback). Planner and aggregator stay text-only.

Copy `.env.example` → `.env` as needed. **Never commit secrets.**

## Architecture map

```
proagent-os/
├── proagent_os/
│   ├── main.py              # FastAPI app + web UI
│   ├── worker.py            # Proactive scheduler process
│   ├── config.py / db.py / auth.py / services.py
│   ├── harness/             # Orchestrator, agent registry, conversation memory
│   ├── llm/                 # Provider interface, mock, OpenAI-compatible
│   ├── professional/        # KB, skills, tools, brand
│   ├── proactive/           # Monitors, recommendations, scheduler
│   ├── profitable/          # Metrics + learning loop stub
│   ├── api/                 # REST /api/v1/*
│   └── web/                 # Console UI
├── config/agents.yaml
├── skills/                  # Built-in skill packs
├── verticals/example/       # How to add a vertical without core changes
├── scripts/demo.py
├── tests/
├── docker-compose.yml
└── fixtures/                # Offline sample HTML/MD
```

### Built-in tools

`http_fetch` · `file_read` · `kb_search` · `clock` · `emit_recommendation`

### Core agents

`planner` · `researcher` · `analyst` · `aggregator` (+ optional vertical agents merged from `verticals/*/agents/`)

## Add a vertical pack

1. Create `verticals/<your_vertical>/agents/agents.yaml` with extra agent specs.
2. Add `verticals/<your_vertical>/skills/<id>/SKILL.md` (optional `run.py`).
3. Append the skills path to `PROAGENT_SKILLS_DIRS`.
4. Restart API/worker — no core code changes required.

See `verticals/example/` for a working stub (`market_scout` agent + `market_scan` skill).

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

## API overview

- `POST /api/v1/tenants` (admin) · `GET /api/v1/tenants/me`
- `GET /api/v1/agents` · `GET /api/v1/agents/tools`
- `POST /api/v1/tasks` · `GET /api/v1/tasks/{id}`
- `POST /api/v1/kb/ingest/url|text|file` · `POST /api/v1/kb/search`
- `GET /api/v1/skills` · `POST /api/v1/skills/{id}/invoke`
- `POST /api/v1/monitors` · `POST /api/v1/monitors/{id}/run`
- `GET /api/v1/recommendations` · `POST .../approve|reject|decide`
- `POST /api/v1/metrics/outcomes` · `GET /api/v1/dashboard`

Interactive docs: `/docs`.

## License

MIT — see [LICENSE](LICENSE).

## Out of scope (by design for this MVP)

- Training large models / real RL
- Dozens of production MCP servers
- Ad-network connectors / multi-region billing

These can hang off the same harness + tool/skill interfaces later.
