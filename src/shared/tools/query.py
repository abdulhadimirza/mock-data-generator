import sqlglot
from sqlglot import exp
from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import create_timeout_handler, parse_sql_statements, verify_table_exists, format_row

@tool()
def execute_select_query(sql_query: str) -> str:
    """Runs analytical SELECT queries to answer user questions or check table states. Strictly enforces read-only operations."""
    try:
        parsed_expressions = sqlglot.parse(sql_query, read='sqlite')
    except Exception as e:
        raise ToolException(f'SQL Parsing Error: Could not parse query with sqlglot: {e}')

    for expr in parsed_expressions:
        if expr is None:
            continue
        # Hard-block any non-SELECT or mutation operations at AST level
        if any(isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Replace)) for node in expr.walk()):
            raise ToolException('Execution blocked: Only SELECT queries are permitted in execute_select_query. Found forbidden statement in AST.')

    statements = parse_sql_statements(sql_query)
    if not statements:
        return 'No valid SQL statements found in input.'

    try:
        with get_readonly_connection() as conn:
            conn.set_progress_handler(create_timeout_handler(2.0), 1000)
            cursor = conn.cursor()
            
            results_output = []
            for idx, stmt in enumerate(statements, 1):
                cursor.execute(stmt)
                rows = cursor.fetchmany(101)
                output_rows = rows[:100]
                
                stmt_hdr = f"Results for Statement {idx} ('{stmt}'):" if len(statements) > 1 else 'Query Results:'
                if not output_rows:
                    results_output.append(f'{stmt_hdr}\nQuery executed successfully, but returned no rows.')
                else:
                    lines = [stmt_hdr]
                    for row in output_rows:
                        lines.append(str(format_row(dict(row))))
                    if len(rows) > 100:
                        lines.append('... Output truncated (100 rows maximum) ...')
                    results_output.append('\n'.join(lines))
                    
            return '\n\n'.join(results_output)
    except Exception as e:
        raise ToolException(f'Database Error: {e}')

@tool()
def get_table_sample(table_name: str, limit: int = 3) -> str:
    """Returns a few real database rows so the agent can inspect existing date string formats, enums, or ID conventions."""
    try:
        limit = max(1, min(limit, 20))
        with get_readonly_connection() as conn:
            if not verify_table_exists(conn, table_name):
                return f"Table '{table_name}' does not exist."
                
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM "{table_name}" LIMIT {limit};')
            rows = cursor.fetchall()
            
            if not rows:
                return f"Table '{table_name}' is empty (0 rows)."
                
            lines = [f"Sample Data for table '{table_name}' ({len(rows)} row(s)):"]
            for r in rows:
                lines.append(str(format_row(dict(r))))
            return '\n'.join(lines)
    except Exception as e:
        raise ToolException(f"Error fetching sample data for table '{table_name}': {e}")

