"""In-memory SQLite store for uploaded datasets (read-only for queries)."""
import re
import sqlite3
import threading
import time

import pandas as pd

MAX_ROWS = 500
NUMERIC = ("INTEGER", "REAL")
PREFERRED_VALUES = ("revenue", "sales", "amount", "profit", "total")

_conn = sqlite3.connect(":memory:", check_same_thread=False)
_conn.execute("PRAGMA query_only = ON")
_lock = threading.RLock()


def clean_name(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower() or "col"
    return f"t_{s}" if s[0].isdigit() else s


def _clean_columns(cols) -> list[str]:
    seen, out = {}, []
    for c in cols:
        base = clean_name(c)
        if base[0].isdigit():
            base = f"c_{base}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(base if n == 0 else f"{base}_{n + 1}")
    return out


def load_dataframe(name: str, df: pd.DataFrame) -> str:
    name = clean_name(name)
    df = df.copy()
    df.columns = _clean_columns(df.columns)
    with _lock:
        _conn.execute("PRAGMA query_only = OFF")
        try:
            df.to_sql(name, _conn, if_exists="replace", index=False)
            _conn.commit()
        finally:
            _conn.execute("PRAGMA query_only = ON")
    return name


def get_schema() -> dict:
    """{table: {"columns": [(name, type)], "row_count": int, "sample": [[...]]}}"""
    schema = {}
    with _lock:
        tables = [r[0] for r in _conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            cols = [(r[1], (r[2] or "TEXT").upper()) for r in _conn.execute(f'PRAGMA table_info("{t}")')]
            count = _conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            sample = [list(r) for r in _conn.execute(f'SELECT * FROM "{t}" LIMIT 3')]
            schema[t] = {"columns": cols, "row_count": count, "sample": sample}
    return schema


def run_query(sql: str, timeout: float = 5.0):
    with _lock:
        deadline = time.monotonic() + timeout
        _conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = _conn.execute(sql)
            columns = [d[0] for d in (cur.description or [])]
            rows = [list(r) for r in cur.fetchmany(MAX_ROWS)]
        finally:
            _conn.set_progress_handler(None, 0)
    return columns, rows


def pick_value_column(numeric_cols: list[str]):
    for pref in PREFERRED_VALUES:
        for c in numeric_cols:
            if pref in c:
                return c
    return numeric_cols[0] if numeric_cols else None


def overview(name: str) -> dict:
    schema = get_schema()
    if name not in schema:
        raise KeyError(name)
    cols = schema[name]["columns"]
    numeric = [c for c, t in cols if t in NUMERIC]
    text = [c for c, t in cols if t == "TEXT"]
    dims = [c for c in text if "date" not in c and "month" not in c]

    kpis = [{"label": "Rows", "value": schema[name]["row_count"]}]
    for c in numeric[:4]:
        _, rows = run_query(f'SELECT SUM("{c}") FROM "{name}"')
        kpis.append({"label": f"Total {c.replace('_', ' ')}", "value": round(rows[0][0] or 0, 2)})

    chart = None
    value = pick_value_column(numeric)
    if dims and value:
        columns, rows = run_query(
            f'SELECT "{dims[0]}", ROUND(SUM("{value}"), 2) AS total_{value} FROM "{name}" '
            f"GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
        )
        chart = {"type": "bar", "title": f"{value.replace('_', ' ').title()} by {dims[0].replace('_', ' ')}",
                 "columns": columns, "rows": rows}
    return {"name": name, "kpis": kpis, "chart": chart}
