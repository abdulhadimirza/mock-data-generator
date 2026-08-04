from .schema import (
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
    get_topological_table_order,
)
from .query import (
    execute_select_query,
    get_table_sample,
)
from .stats import (
    get_table_row_count,
)

shared_tools = [
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
    execute_select_query,
    get_table_sample,
    get_table_row_count,
]

for t in shared_tools:
    t.handle_tool_error = True

__all__ = [
    "list_tables",
    "get_full_schema",
    "get_tables_schema_with_deps",
    "get_topological_table_order",
    "execute_select_query",
    "get_table_sample",
    "get_table_row_count",
    "shared_tools",
]

