import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import verify_table_exists

def _get_table_schema_dict(cursor, table_name: str, create_sql: Optional[str] = None) -> Dict[str, Any]:
    """Helper function to extract complete schema dictionary for a single table."""
    if create_sql is None:
        cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?;', (table_name,))
        row = cursor.fetchone()
        create_sql = row['sql'] if row else ""

    # Column info
    cursor.execute(f'PRAGMA table_info({table_name});')
    cols = cursor.fetchall()
    columns_info = [
        {
            "cid": col['cid'],
            "name": col['name'],
            "type": col['type'],
            "notnull": bool(col['notnull']),
            "default_value": col['dflt_value'],
            "pk": col['pk']
        }
        for col in cols
    ]

    # Foreign key info
    cursor.execute(f'PRAGMA foreign_key_list({table_name});')
    fks = cursor.fetchall()
    fk_info = [
        {
            "id": fk['id'],
            "seq": fk['seq'],
            "table": fk['table'],
            "from": fk['from'],
            "to": fk['to'],
            "on_update": fk['on_update'],
            "on_delete": fk['on_delete'],
            "match": fk['match']
        }
        for fk in fks
    ]

    # Index / Unique info
    cursor.execute(f'PRAGMA index_list({table_name});')
    idx_list = cursor.fetchall()
    unique_constraints = []
    for idx in idx_list:
        if idx['unique']:
            cursor.execute(f'PRAGMA index_info({idx["name"]});')
            idx_cols = [c['name'] for c in cursor.fetchall()]
            unique_constraints.append({
                "name": idx['name'],
                "columns": idx_cols,
                "origin": idx['origin'] if 'origin' in idx.keys() else 'c'
            })

    return {
        "create_sql": create_sql,
        "columns": columns_info,
        "foreign_keys": fk_info,
        "unique_constraints": unique_constraints
    }

@tool()
def get_full_schema() -> str:
    """Dumps the entire database schema (tables, column types, NOT NULL flags, primary keys, foreign keys, unique constraints) in a single JSON payload. Ideal for small/medium databases (< 15 tables)."""
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name, sql FROM sqlite_master WHERE type="table";')
            tables = cursor.fetchall()
            
            schema = {}
            for row in tables:
                table_name = row['name']
                if not table_name or table_name.startswith('sqlite_'):
                    continue
                
                schema[table_name] = _get_table_schema_dict(cursor, table_name, create_sql=row['sql'])

            return json.dumps(schema, indent=2)
    except Exception as e:
        raise ToolException(f"Error fetching full database schema: {e}")

@tool()
def get_tables_schema_with_deps(table_names: List[str]) -> str:
    """Fetches schema for specific tables and automatically resolves and appends upstream parent foreign key tables in Python. Prevents multi-turn tool chaining."""
    try:
        with get_readonly_connection() as conn:
            visited = set()
            to_visit = list(table_names)
            schemas = {}
            
            while to_visit:
                tbl = to_visit.pop(0)
                if tbl in visited:
                    continue
                
                if not verify_table_exists(conn, tbl):
                    continue
                    
                visited.add(tbl)
                cursor = conn.cursor()
                
                tbl_schema = _get_table_schema_dict(cursor, tbl)
                tbl_schema["is_requested_table"] = tbl in table_names
                schemas[tbl] = tbl_schema
                
                for fk in tbl_schema["foreign_keys"]:
                    parent_table = fk['table']
                    if parent_table and parent_table not in visited:
                        to_visit.append(parent_table)

            return json.dumps(schemas, indent=2)
    except Exception as e:
        raise ToolException(f"Error fetching schema with dependencies: {e}")
