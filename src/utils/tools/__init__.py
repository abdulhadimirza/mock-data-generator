from .schema import (
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
)
from .query import (
    execute_select_query,
    get_table_sample,
)
from .stats import (
    get_table_row_count,
)
from .mock_data import (
    generate_mock_records,
    batch_insert_mock_data,
)
from .backup import (
    analyze_query_impact,
    execute_write_query,
    editor_tools,
)

tools = [
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
    execute_select_query,
    get_table_sample,
    get_table_row_count,
    generate_mock_records,
    batch_insert_mock_data,
]

for t in tools:
    t.handle_tool_error = True

for t in editor_tools:
    t.handle_tool_error = True

reader_tools = [
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
    execute_select_query,
    get_table_sample,
    get_table_row_count,
]

# Kept for backward compatibility and backup
assistant_tools = reader_tools

generator_tools = [
    list_tables,
    get_full_schema,
    get_tables_schema_with_deps,
    get_table_sample,
    get_table_row_count,
    execute_select_query,
    generate_mock_records,
    batch_insert_mock_data,
]

__all__ = [
    "list_tables",
    "get_full_schema",
    "get_tables_schema_with_deps",
    "execute_select_query",
    "get_table_sample",
    "get_table_row_count",
    "generate_mock_records",
    "batch_insert_mock_data",
    "analyze_query_impact",
    "execute_write_query",
    "reader_tools",
    "assistant_tools",
    "editor_tools",
    "generator_tools",
    "tools",
]

