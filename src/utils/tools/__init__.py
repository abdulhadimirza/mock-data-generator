from .introspection import list_tables, describe_table, search_tables_by_keyword
from .execution import execute_read_query, execute_write_query
from .analytics import get_column_distinct_values, get_table_statistics, analyze_query_impact
from .mock import generate_mock_records, batch_insert_mock_data

tools = [
    list_tables, 
    describe_table, 
    execute_read_query,
    get_column_distinct_values,
    get_table_statistics,
    analyze_query_impact,
    execute_write_query,
    search_tables_by_keyword,
    generate_mock_records,
    batch_insert_mock_data
]

for t in tools:
    t.handle_tool_error = True

reader_tools = [
    list_tables, 
    describe_table, 
    execute_read_query,
    get_column_distinct_values,
    get_table_statistics,
    search_tables_by_keyword
]

# Kept for backward compatibility and backup
assistant_tools = reader_tools

editor_tools = [
    analyze_query_impact,
    execute_write_query
]

generator_tools = [
    describe_table,
    list_tables,
    execute_read_query,
    generate_mock_records,
    batch_insert_mock_data
]

__all__ = [
    "list_tables",
    "describe_table",
    "search_tables_by_keyword",
    "execute_read_query",
    "execute_write_query",
    "get_column_distinct_values",
    "get_table_statistics",
    "analyze_query_impact",
    "generate_mock_records",
    "batch_insert_mock_data",
    "reader_tools",
    "assistant_tools",
    "editor_tools",
    "generator_tools",
    "tools",
]
