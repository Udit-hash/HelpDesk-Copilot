"""Safety checks for SQL written by the LLM.

The agent can query ticket data, but it must never change it. Protection is
layered (defence in depth):

1. `validate_select` - only a single SELECT/WITH statement is accepted;
   comments, multiple statements and write/DDL keywords are rejected.
2. The query is wrapped so at most SQL_ROW_LIMIT rows come back.
3. `db.run_readonly_query` runs it on a read-only connection
   (SQLite opened with mode=ro, PostgreSQL in a READ ONLY transaction).
"""
import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|merge|grant|revoke|"
    r"attach|detach|pragma|vacuum|reindex|copy|call|exec|execute|set|begin|commit|rollback|"
    r"pg_sleep|pg_read_file|lo_import|load_extension)\b",
    re.IGNORECASE,
)


class UnsafeSQLError(ValueError):
    pass


def validate_select(sql: str, row_limit: int = 50) -> str:
    """Return a safe, row-limited version of `sql` or raise UnsafeSQLError."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("Empty query.")
    query = sql.strip().rstrip(";").strip()

    if "--" in query or "/*" in query or "*/" in query:
        raise UnsafeSQLError("SQL comments are not allowed.")
    if ";" in query:
        raise UnsafeSQLError("Only one statement is allowed.")
    if not re.match(r"^(select|with)\b", query, flags=re.IGNORECASE):
        raise UnsafeSQLError("Only SELECT queries are allowed.")

    # Check keywords outside string literals, so a search like WHERE title LIKE '%update%' still works.
    without_strings = re.sub(r"'(?:[^']|'')*'", "''", query)
    match = FORBIDDEN.search(without_strings)
    if match:
        raise UnsafeSQLError(f"Keyword '{match.group(0)}' is not allowed.")

    return f"SELECT * FROM ({query}) AS q LIMIT {int(row_limit)}"
