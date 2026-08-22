# Cursor notes

Project conventions for agents working in this repo.

## Structure

- `app/` — FastAPI (or similar) application code only. Keep HTTP handlers thin.
- `scraper/` — fetch and normalize external data. Do not mix scraping with API routes.
- `agents/` — agent prompts, tools, and orchestration. No I/O that belongs in `scraper/` or `app/`.
- `tests/` — tests that mirror the package names (`tests/test_app.py`, etc.).
- `observability/` — shared logging, metrics, and tracing helpers. Import these instead of adding ad-hoc print/debug.

## Rules

- Python 3.12+. Dependencies go in `requirements.txt`.
- Do not commit `.env`, secrets, or API tokens.
- Prefer small, focused modules over one large file.
- Add or update a test when you change behavior.
- Keep README status accurate when the project shape changes.

## Run

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest
```
