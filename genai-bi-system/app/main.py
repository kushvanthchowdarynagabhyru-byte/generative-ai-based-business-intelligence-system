import io
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import data_store as store
from .ai_service import ai_service, suggest_chart
from .sql_guard import validate_sql

BASE = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / "static"
SAMPLE = BASE / "sample_data" / "sales.csv"
MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SAMPLE.exists():
        store.load_dataframe("sales", pd.read_csv(SAMPLE))
    yield


app = FastAPI(title="Generative AI-Based Business Intelligence System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    dataset: str | None = None


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "ai_mode": ai_service.mode}


@app.get("/api/datasets")
def datasets():
    return [
        {"name": n, "row_count": i["row_count"], "columns": [{"name": c, "type": t} for c, t in i["columns"]]}
        for n, i in store.get_schema().items()
    ]


@app.get("/api/datasets/{name}/overview")
def overview(name: str):
    try:
        return store.overview(name)
    except KeyError:
        raise HTTPException(404, "Dataset not found")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 10 MB")
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, "Could not parse the CSV file")
    if df.empty:
        raise HTTPException(400, "The CSV file has no rows")
    name = store.load_dataframe(Path(file.filename).stem, df)
    return {"name": name, "rows": len(df), "columns": list(df.columns)}


def _execute(sql: str):
    safe = validate_sql(sql)
    columns, rows = store.run_query(safe)
    return safe, columns, rows


@app.post("/api/ask")
def ask(req: AskRequest):
    schema = store.get_schema()
    if not schema:
        raise HTTPException(400, "No datasets loaded. Upload a CSV first.")
    try:
        sql = ai_service.question_to_sql(req.question, schema, req.dataset)
        try:
            sql, columns, rows = _execute(sql)
        except Exception as exc:
            if ai_service.mode != "claude":
                raise
            sql = ai_service.fix_sql(req.question, schema, sql, str(exc))  # one retry
            sql, columns, rows = _execute(sql)
    except Exception as exc:
        raise HTTPException(400, f"Could not answer that question: {exc}")
    return {
        "mode": ai_service.mode,
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "chart": suggest_chart(columns, rows),
        "insight": ai_service.insight(req.question, columns, rows),
    }
