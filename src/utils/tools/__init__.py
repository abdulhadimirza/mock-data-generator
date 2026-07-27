from .schema import (
    get_full_schema,
    get_tables_schema_with_deps,
)
from .query import (
    execute_select_query,
    execute_write_query,
    get_table_sample,
)
from .stats import (
    get_table_row_count,
    analyze_query_impact,
)
from .mock_data import (
    generate_mock_records,
    batch_insert_mock_data,
)

tools = [
    get_full_schema,
    get_tables_schema_with_deps,
    execute_select_query,
    get_table_sample,
    get_table_row_count,
    analyze_query_impact,
    execute_write_query,
    generate_mock_records,
    batch_insert_mock_data,
]

for t in tools:
    t.handle_tool_error = True

reader_tools = [
    get_full_schema,
    get_tables_schema_with_deps,
    execute_select_query,
    get_table_sample,
    get_table_row_count,
]

# Kept for backward compatibility and backup
assistant_tools = reader_tools

editor_tools = [
    analyze_query_impact,
    execute_write_query,
]

generator_tools = [
    get_full_schema,
    get_tables_schema_with_deps,
    get_table_sample,
    get_table_row_count,
    execute_select_query,
    generate_mock_records,
    batch_insert_mock_data,
]

__all__ = [
    "get_full_schema",
    "get_tables_schema_with_deps",
    "execute_select_query",
    "execute_write_query",
    "get_table_sample",
    "get_table_row_count",
    "analyze_query_impact",
    "generate_mock_records",
    "batch_insert_mock_data",
    "reader_tools",
    "assistant_tools",
    "editor_tools",
    "generator_tools",
    "tools",
]
