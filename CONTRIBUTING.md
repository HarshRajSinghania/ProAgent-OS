# Contributing to ProAgent OS

Thanks for helping. Short version:

1. Open an issue first for large features (use the templates).
2. Fork → branch → PR against `main`.
3. Run `pytest -q` before opening the PR.
4. Never commit secrets (`.env`, keys, live databases under `data/`).

Vertical packs that plug in via `verticals/` + `PROAGENT_SKILLS_DIRS` without core changes are especially welcome.
