from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import verify_table_exists

@tool()
def get_table_row_count(table_name: str) -> str:
    """Returns the exact row volume for a given table to verify population status."""
    try:
        with get_readonly_connection() as conn:
            if not verify_table_exists(conn, table_name):
                return f"Table '{table_name}' does not exist."
                
            cursor = conn.cursor()
            cursor.execute(f'SELECT COUNT(*) as count FROM {table_name};')
            count = cursor.fetchone()['count']
            return f"Table '{table_name}' total row count: {count}"
    except Exception as e:
        raise ToolException(f"Error getting row count for '{table_name}': {e}")
