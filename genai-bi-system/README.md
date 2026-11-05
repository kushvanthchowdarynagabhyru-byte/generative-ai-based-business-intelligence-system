# Generative AI-Based Business Intelligence System

A small base project: upload a CSV, see an automatic overview, then **ask business questions in
plain English**. Claude turns each question into a read-only SQL query, the system runs it,
charts the result and writes a short insight.

## Features
- CSV upload into an in-memory SQLite store (sample `sales` dataset loaded on start)
- Automatic KPI cards and a default breakdown chart
- Natural language → SQL → table + chart + written insight
- SQL safety: single `SELECT` only, forbidden keywords blocked, database opened read-only, 5s timeout, 500-row cap
- Works without an API key through a rule-based fallback (handles "total/average/count X by Y", "top N", "monthly trend")

## Run it
```bash
cd genai-bi-system
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optionally add ANTHROPIC_API_KEY for full natural-language support
uvicorn app.main:app --reload
```
Open http://localhost:8000 (API docs at `/docs`).

## API
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status and AI mode (`claude` / `fallback`) |
| GET | `/api/datasets` | Loaded datasets and columns |
| GET | `/api/datasets/{name}/overview` | KPIs and a default chart |
| POST | `/api/upload` | Upload a CSV (max 10 MB) |
| POST | `/api/ask` | `{"question": "...", "dataset": "sales"}` → sql, rows, chart type, insight |

## Structure
```
app/
  main.py          API routes
  data_store.py    SQLite store, schema, queries, overview
  sql_guard.py     SELECT-only validation
  ai_service.py    Claude NL→SQL + insights, rule-based fallback
  static/index.html  Dashboard UI (Chart.js)
sample_data/sales.csv
```

## Next steps
Authentication, persistent databases (Postgres/warehouse connectors), saved dashboards,
scheduled reports, and multi-table joins with a data dictionary.
