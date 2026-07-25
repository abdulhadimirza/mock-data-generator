from langchain_core.tools import tool, ToolException
from langgraph.types import interrupt
from database import get_readonly_connection, get_db_connection
from .helpers import create_timeout_handler, parse_sql_statements

@tool()
def execute_read_query(query: str) -> str:
    """Safely execute one or more raw SQL queries provided by the LLM (separated by semicolons) and return the results."""
    statements = parse_sql_statements(query)
    if not statements:
        return "No valid SQL statements found in input."

    try:
        with get_readonly_connection() as conn:
            conn.set_progress_handler(create_timeout_handler(2.0), 1000)
            cursor = conn.cursor()
            
            results_output = []
            for idx, stmt in enumerate(statements, 1):
                cursor.execute(stmt)
                rows = cursor.fetchmany(101)
                output_rows = rows[:100]
                
                stmt_hdr = f"Results for Statement {idx} ('{stmt}'):" if len(statements) > 1 else "Query Results:"
                if not output_rows:
                    results_output.append(f"{stmt_hdr}\nQuery executed successfully, but returned no rows.")
                else:
                    lines = [stmt_hdr]
                    for row in output_rows:
                        lines.append(str(dict(row)))
                    if len(rows) > 100:
                        lines.append("... Output truncated (100 rows maximum) ...")
                    results_output.append("\n".join(lines))
                    
            return "\n\n".join(results_output)
    except Exception as e:
        raise ToolException(f"Database Error: {e}")

@tool()
def execute_write_query(query: str, explanation: str) -> str:
    """Execute one or more raw SQL queries that modify the database (separated by semicolons). Requires a plain-English explanation of the blast radius / impact."""
    statements = parse_sql_statements(query)
    if not statements:
        return "No valid SQL statements found in input."

    response = interrupt({
        "tool_name": "execute_write_query",
        "arguments": {"query": query, "explanation": explanation},
        "message": f"Approve executing the following SQL write query/queries?\n\nExplanation:\n{explanation}\n\nSQL:\n{query}"
    })
    
    if not response:
        return "Query execution cancelled by user."
        
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            total_rows_affected = 0
            for stmt in statements:
                cursor.execute(stmt)
                total_rows_affected += cursor.rowcount if cursor.rowcount > 0 else 0
            conn.commit()
            
            return f"All {len(statements)} statement(s) executed successfully. Total rows affected: {total_rows_affected}"
    except Exception as e:
        raise ToolException(f"Database Error: {e}")
