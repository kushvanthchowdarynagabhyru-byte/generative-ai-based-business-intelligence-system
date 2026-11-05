"""Only allow a single read-only SELECT. (The store is also opened with query_only=ON.)"""
import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex)\b", re.I
)


def validate_sql(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("Empty query")
    if ";" in s:
        raise ValueError("Only a single statement is allowed")
    if not re.match(r"(?is)^(select|with)\b", s):
        raise ValueError("Only SELECT queries are allowed")
    if FORBIDDEN.search(s):
        raise ValueError("Query contains a forbidden keyword")
    return s
