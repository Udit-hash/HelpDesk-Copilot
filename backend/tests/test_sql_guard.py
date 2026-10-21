import pytest

from app.sql_guard import UnsafeSQLError, validate_select


@pytest.mark.parametrize("sql", [
    "SELECT * FROM tickets",
    "select category, count(*) from tickets group by category;",
    "WITH t AS (SELECT * FROM tickets) SELECT count(*) FROM t",
    "SELECT * FROM tickets WHERE title LIKE '%update%'",  # keyword inside a string is fine
])
def test_allows_selects(sql):
    assert validate_select(sql, 50).endswith("LIMIT 50")


@pytest.mark.parametrize("sql", [
    "DELETE FROM tickets",
    "DROP TABLE tickets",
    "UPDATE tickets SET status='Resolved'",
    "SELECT 1; DROP TABLE tickets",
    "SELECT * FROM tickets -- comment",
    "SELECT * FROM tickets /* x */",
    "WITH x AS (DELETE FROM tickets RETURNING *) SELECT * FROM x",
    "ATTACH DATABASE 'x.db' AS x",
    "",
])
def test_blocks_unsafe(sql):
    with pytest.raises(UnsafeSQLError):
        validate_select(sql)
