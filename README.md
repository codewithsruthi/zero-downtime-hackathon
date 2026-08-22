# zero-downtime-hackathon

Hackathon project scaffold. Python services live in `app/`, collection in `scraper/`, agent workflows in `agents/`, and telemetry in `observability/`.

## Layout

```
app/             application and API entrypoints
scraper/         data collection
agents/          agent workflows
tests/           unit and integration tests
observability/   logging, metrics, tracing
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Or with `uv`:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Status

Folder structure is in place. Implementation starts here.
