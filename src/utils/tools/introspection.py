from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import verify_table_exists

@tool()
def list_tables() -> str:
    """Query the database to return only a list of available table names."""
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM sqlite_master WHERE type="table";')
            tables = []
            for row in cursor.fetchall():
                name = row['name']
                if name and not name.startswith('sqlite_'):
                    tables.append(name)
            
            if not tables:
                return "No tables found in the database."
                
            return "\n".join(tables)
    except Exception as e:
        raise ToolException(f"Error reading tables: {e}")

@tool()
def describe_table(table_name: str) -> str:
    """Given a table name, execute PRAGMA table_info and PRAGMA foreign_key_list to fetch the schema, AND run SELECT * FROM table_name LIMIT 3 to fetch a data sample."""
    try:
        with get_readonly_connection() as conn:
            if not verify_table_exists(conn, table_name):
                return f"Table '{table_name}' does not exist."
                
            cursor = conn.cursor()
            
            # Get schema
            cursor.execute(f'PRAGMA table_info({table_name});')
            columns = cursor.fetchall()
            
            # Get foreign keys
            cursor.execute(f'PRAGMA foreign_key_list({table_name});')
            fks = cursor.fetchall()
            
            # Get sample data
            cursor.execute(f'SELECT * FROM {table_name} LIMIT 3;')
            sample_rows = cursor.fetchall()
            
            output = [f"Schema for table '{table_name}':", "Columns:"]
            for col in columns:
                output.append(f"  {col['name']} ({col['type']})")
                
            if fks:
                output.append("Foreign Keys:")
                for fk in fks:
                    output.append(f"  {fk['from']} -> {fk['table']}({fk['to']})")
                    
            output.append("Sample Data (max 3 rows):")
            for row in sample_rows:
                truncated_row = []
                for val in row:
                    val_str = str(val)
                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    truncated_row.append(val_str)
                output.append(f"  {truncated_row}")
                
            return "\n".join(output)
    except Exception as e:
        raise ToolException(f"Error describing table '{table_name}': {e}")

@tool()
def search_tables_by_keyword(keyword: str) -> str:
    """Search for relevant tables based on a keyword match in table names or column names."""
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT name FROM sqlite_master WHERE type="table";')
            tables = []
            for row in cursor.fetchall():
                name = row['name']
                if name and not name.startswith('sqlite_'):
                    tables.append(name)
                    
            matching_tables = set()
            keyword_lower = keyword.lower()
            
            for table in tables:
                if keyword_lower in table.lower():
                    matching_tables.add(table)
                    continue
                    
                cursor.execute(f'PRAGMA table_info({table});')
                columns = cursor.fetchall()
                for col in columns:
                    if keyword_lower in col['name'].lower():
                        matching_tables.add(table)
                        break
                        
            if not matching_tables:
                return f"No tables found matching keyword '{keyword}'."
                
            return "\n".join(sorted(list(matching_tables)))
    except Exception as e:
        raise ToolException(f"Error searching tables for keyword '{keyword}': {e}")
