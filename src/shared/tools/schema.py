import json
from collections import deque, defaultdict
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool, ToolException
from database import get_readonly_connection
from .helpers import verify_table_exists

def get_topological_table_order(schema_map: dict) -> List[str]:
    """
    Computes a topological sort (parent before child) for database table schemas.
    Uses Kahn's Algorithm on Foreign Key dependencies.
    """
    if not schema_map:
        return []

    tables = list(schema_map.keys())
    adj_list = defaultdict(list)
    in_degree = {tbl: 0 for tbl in tables}

    for table_name, schema_info in schema_map.items():
        foreign_keys = schema_info.get('foreign_keys', [])
        parents = set()
        for fk in foreign_keys:
            parent_tbl = fk.get('table')
            if parent_tbl and parent_tbl in schema_map and parent_tbl != table_name:
                parents.add(parent_tbl)

        for parent_tbl in parents:
            adj_list[parent_tbl].append(table_name)
            in_degree[table_name] += 1

    queue = deque([tbl for tbl in tables if in_degree[tbl] == 0])
    order = []

    while queue:
        current = queue.popleft()
        order.append(current)

        for neighbor in adj_list[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) < len(tables):
        for tbl in tables:
            if tbl not in order:
                order.append(tbl)

    return order


def _get_table_schema_dict(cursor, table_name: str, create_sql: Optional[str] = None) -> Dict[str, Any]:
    """Helper function to extract schema metadata (create_sql and foreign_keys) for internal python logic."""
    if create_sql is None:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
        row = cursor.fetchone()
        create_sql = row['sql'] if row else ''

    # Foreign key info (needed for topological sorting and dependency resolution)
    cursor.execute(f'PRAGMA foreign_key_list("{table_name}");')
    fks = cursor.fetchall()
    fk_info = [
        {
            'id': fk['id'],
            'seq': fk['seq'],
            'table': fk['table'],
            'from': fk['from'],
            'to': fk['to'],
            'on_update': fk['on_update'],
            'on_delete': fk['on_delete'],
            'match': fk['match']
        }
        for fk in fks
    ]

    return {
        'create_sql': create_sql,
        'foreign_keys': fk_info,
    }


def get_table_metadata_with_deps(table_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Python helper to fetch schemas and parent foreign key dependencies as rich dictionaries."""
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
            tbl_schema['is_requested_table'] = tbl in table_names
            schemas[tbl] = tbl_schema
            
            for fk in tbl_schema['foreign_keys']:
                parent_table = fk['table']
                if parent_table and parent_table not in visited:
                    to_visit.append(parent_table)

        return schemas


def format_metadata_to_sql_json(metadata_map: Dict[str, Dict[str, Any]]) -> str:
    """Formats a schema metadata dictionary into a clean JSON string mapping table names to CREATE TABLE statements."""
    sql_map = {tbl: data['create_sql'] for tbl, data in metadata_map.items()}
    return json.dumps(sql_map, indent=2)


@tool()
def list_tables() -> str:
    """Query the database to return only a list of available table names without full schemas. Ideal for table discovery or when only table names are needed."""
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = []
            for row in cursor.fetchall():
                name = row['name']
                if name and not name.startswith('sqlite_'):
                    tables.append(name)
            
            if not tables:
                return 'No tables found in the database.'
                
            return '\n'.join(tables)
    except Exception as e:
        raise ToolException(f'Error reading tables: {e}')

@tool()
def get_full_schema() -> str:
    """Dumps the entire database CREATE SQL schema in a single JSON payload mapping table names to CREATE TABLE statements."""
    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            schema = {}
            for row in tables:
                table_name = row['name']
                if not table_name or table_name.startswith('sqlite_'):
                    continue
                schema[table_name] = row['sql']

            return json.dumps(schema, indent=2)
    except Exception as e:
        raise ToolException(f'Error fetching full database schema: {e}')

@tool()
def get_tables_schema_with_deps(table_names: List[str]) -> str:
    """Fetches CREATE TABLE schema for specific tables and automatically appends upstream parent foreign key tables as a clean JSON map."""
    try:
        metadata_map = get_table_metadata_with_deps(table_names)
        return format_metadata_to_sql_json(metadata_map)
    except Exception as e:
        raise ToolException(f'Error fetching schema with dependencies: {e}')

