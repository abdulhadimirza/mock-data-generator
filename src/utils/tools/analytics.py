import sqlglot
from sqlglot import exp
from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import verify_table_exists

@tool()
def get_column_distinct_values(table: str, column: str) -> str:
    """Queries and returns the distinct categorical values in a specified column."""
    try:
        with get_readonly_connection() as conn:
            if not verify_table_exists(conn, table):
                return f"Table '{table}' does not exist."
                
            cursor = conn.cursor()
            cursor.execute(f'PRAGMA table_info({table});')
            columns = [row['name'] for row in cursor.fetchall()]
            if column not in columns:
                return f"Column '{column}' does not exist in table '{table}'."
                
            query = f'SELECT DISTINCT {column} FROM {table} LIMIT 100;'
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if not rows:
                return f"No values found in column '{column}'."
                
            values = [str(row[column]) for row in rows]
            return "\n".join(values)
    except Exception as e:
        raise ToolException(f"Error getting distinct values for '{table}.{column}': {e}")

@tool()
def get_table_statistics(table: str) -> str:
    """Returns row counts and basic bounds (min/max) for a specified table."""
    try:
        with get_readonly_connection() as conn:
            if not verify_table_exists(conn, table):
                return f"Table '{table}' does not exist."
                
            cursor = conn.cursor()
            cursor.execute(f'PRAGMA table_info({table});')
            columns = cursor.fetchall()
            
            cursor.execute(f'SELECT COUNT(*) as count FROM {table};')
            count = cursor.fetchone()['count']
            
            output = [f"Statistics for table '{table}':", f"Total Rows: {count}"]
            
            numeric_types = ('INTEGER', 'REAL', 'NUMERIC')
            for col in columns:
                col_name = col['name']
                col_type = col['type'].upper()
                if any(t in col_type for t in numeric_types):
                    cursor.execute(f'SELECT MIN({col_name}) as min_val, MAX({col_name}) as max_val FROM {table};')
                    stats = cursor.fetchone()
                    output.append(f"  {col_name} ({col['type']}): MIN = {stats['min_val']}, MAX = {stats['max_val']}")
                    
            return "\n".join(output)
    except Exception as e:
        raise ToolException(f"Error getting statistics for '{table}': {e}")

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
