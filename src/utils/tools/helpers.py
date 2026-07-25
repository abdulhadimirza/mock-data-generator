import time
import sqlglot

def verify_table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in sqlite_master."""
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?;', (table_name,))
    return cursor.fetchone() is not None

def create_timeout_handler(timeout_seconds: float):
    """Create a progress handler callback for query timeout."""
    start_time = time.time()
    def progress_handler() -> int:
        if time.time() - start_time > timeout_seconds:
            return 1  # Return non-zero to abort query
        return 0
    return progress_handler

def parse_sql_statements(query: str) -> list[str]:
    """Parse raw SQL query string into individual SQL statements using sqlglot, falling back to semicolon split if parsing fails."""
    try:
        expressions = sqlglot.parse(query, read="sqlite")
        statements = [expr.sql(dialect="sqlite") for expr in expressions if expr]
        if statements:
            return statements
    except Exception:
        pass
    return [stmt.strip() for stmt in query.split(";") if stmt.strip()]
