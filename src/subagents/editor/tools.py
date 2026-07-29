import sqlglot
from sqlglot import exp
from langchain_core.tools import tool, ToolException
from langgraph.types import interrupt
from database import get_readonly_connection, get_db_connection
from shared.tools.helpers import parse_sql_statements

@tool()
def analyze_query_impact(query: str) -> str:
    """Analyze one or more proposed write queries (separated by semicolons) by generating EXPLAIN QUERY PLAN and estimating affected row counts for each statement."""
    try:
        parsed_expressions = sqlglot.parse(query, read="sqlite")
    except Exception:
        parsed_expressions = []

    if not parsed_expressions:
        statements = [stmt.strip() for stmt in query.split(";") if stmt.strip()]
        if not statements:
            return "No valid SQL statements found in input."
        statements_to_process = [(stmt, None) for stmt in statements]
    else:
        statements_to_process = [(expr.sql(dialect="sqlite"), expr) for expr in parsed_expressions if expr]

    if not statements_to_process:
        return "No valid SQL statements found in input."
        
    outputs = []
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            
            for idx, (stmt, expr) in enumerate(statements_to_process, 1):
                stmt_output = [f"Statement {idx}: {stmt}"] if len(statements_to_process) > 1 else [f"Query: {stmt}"]
                
                has_error = False
                # EXPLAIN QUERY PLAN
                try:
                    cursor.execute(f"EXPLAIN QUERY PLAN {stmt}")
                    plan_rows = cursor.fetchall()
                    stmt_output.append("Query Plan:")
                    for row in plan_rows:
                        stmt_output.append(f"  detail: {row['detail']}")
                except Exception as plan_err:
                    has_error = True
                    stmt_output.append(f"Query Plan Error: {plan_err}")
                    
                # Estimate row count only if query plan succeeded
                if not has_error:
                    row_count_info = ""
                    if expr is not None:
                        try:
                            if isinstance(expr, (exp.Update, exp.Delete)):
                                table = expr.this
                                where = expr.args.get("where")
                                count_query = sqlglot.select("COUNT(*) as cnt").from_(table)
                                if where:
                                    count_query = count_query.where(where.this)
                                count_sql = count_query.sql(dialect="sqlite")
                                
                                cursor.execute(count_sql)
                                cnt = cursor.fetchone()["cnt"]
                                row_count_info = f"Estimated Affected Rows: {cnt}"
                            elif isinstance(expr, exp.Insert):
                                expression_type = expr.args.get("expression")
                                if isinstance(expression_type, exp.Values):
                                    cnt = len(expression_type.expressions)
                                    row_count_info = f"Estimated Affected Rows: {cnt}"
                                elif isinstance(expression_type, exp.Select):
                                    count_query = sqlglot.select("COUNT(*) as cnt").from_(expression_type.subquery("subq"))
                                    count_sql = count_query.sql(dialect="sqlite")
                                    cursor.execute(count_sql)
                                    cnt = cursor.fetchone()["cnt"]
                                    row_count_info = f"Estimated Affected Rows: {cnt}"
                                else:
                                    row_count_info = "Estimated Affected Rows: 1"
                            else:
                                row_count_info = "Estimated Affected Rows: N/A"
                        except Exception:
                            row_count_info = "Estimated Affected Rows: Unknown (could not parse row count pre-check)"
                    else:
                        row_count_info = "Estimated Affected Rows: Unknown (could not parse row count pre-check)"
                        
                    if row_count_info:
                        stmt_output.append(row_count_info)
                else:
                    stmt_output.append("Estimated Affected Rows: N/A (Invalid Query)")
                    
                outputs.append("\n".join(stmt_output))
                
            return "\n\n".join(outputs)
    except Exception as e:
        raise ToolException(f"Error analyzing query impact: {e}")

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

analyze_query_impact.handle_tool_error = True
execute_write_query.handle_tool_error = True

editor_tools = [
    analyze_query_impact,
    execute_write_query,
]

__all__ = [
    "analyze_query_impact",
    "execute_write_query",
    "editor_tools",
]
