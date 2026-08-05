import time
import pytest

from database import get_db_connection, init_db
from agents.generator import sandbox_execution_node


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


def test_timeout():
    state = {
        'generated_code': "import time\ntime.sleep(20)"
    }
    start_time = time.time()
    result = sandbox_execution_node(state)
    elapsed = time.time() - start_time
    
    assert 'TimeoutError' in str(result.get('execution_error')), "Timeout error was not triggered."
    assert elapsed < 18, "Execution exceeded timeout window significantly."


def test_infinite_while_loop_termination():
    state = {
        'generated_code': "i = 0\nwhile True:\n    i += 1"
    }
    start_time = time.time()
    result = sandbox_execution_node(state)
    elapsed = time.time() - start_time
    
    assert 'TimeoutError' in str(result.get('execution_error')), "Timeout error was not triggered."
    assert elapsed < 18, "Execution exceeded timeout window significantly."


def test_authorizer_schema_protection():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS authorizer_test_table (id INT)")
            conn.commit()

        state_drop = {
            'generated_code': """
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE authorizer_test_table")
"""
        }
        result_drop = sandbox_execution_node(state_drop)
        assert result_drop.get('execution_error') is not None, "DROP TABLE was permitted."
        assert 'not authorized' in str(result_drop.get('execution_error')).lower(), "Authorizer did not block DROP TABLE."

        state_delete = {
            'generated_code': """
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM authorizer_test_table")
"""
        }
        result_delete = sandbox_execution_node(state_delete)
        assert result_delete.get('execution_error') is None, "DELETE should be permitted."
    finally:
        # Clean up test table
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS authorizer_test_table")
            conn.commit()


def test_transaction_rollback():
    test_email = "sandbox_test_user_rollback@example.com"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS rollback_test_table (id INTEGER PRIMARY KEY, email TEXT)")
            cursor.execute("DELETE FROM rollback_test_table")
            conn.commit()

        state_failure = {
            'generated_code': f"""
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO rollback_test_table (email) VALUES ('{test_email}')")
    raise ValueError("Simulated unexpected failure during insertion")
"""
        }
        
        result = sandbox_execution_node(state_failure)
        assert result.get('execution_error') is not None, "Error was not raised."

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM rollback_test_table WHERE email = ?', (test_email,))
            final_count = cursor.fetchone()['count']
            
        assert final_count == 0, "Partial data was persisted despite execution failure!"
    finally:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS rollback_test_table")
            conn.commit()


def test_restricted_imports():
    state_os = {
        'generated_code': "import os\nos.system('echo Hacked')"
    }
    result_os = sandbox_execution_node(state_os)
    assert result_os.get('execution_error') is not None, "Restricted module 'os' was imported."
    assert 'forbidden' in str(result_os.get('execution_error')).lower(), "ImportError was not triggered for forbidden module."


def test_conn_attribute_protection():
    state_conn = {
        'generated_code': """
with get_db_connection() as conn:
    raw_conn = getattr(conn, "_conn", None)
    if raw_conn is not None:
        raise ValueError("Exposed internal _conn attribute!")
    conn.set_authorizer(None)
"""
    }
    result_conn = sandbox_execution_node(state_conn)
    assert result_conn.get('execution_error') is not None, "Internal connection attribute or set_authorizer was accessible."
    assert 'restricted' in str(result_conn.get('execution_error')).lower(), "Attribute restriction error was not raised."


def test_strptime_import():
    state_strptime = {
        'generated_code': """
from datetime import datetime
dt = datetime.strptime("2026-07-29 12:00:00", "%Y-%m-%d %H:%M:%S")
assert dt.year == 2026
"""
    }
    result = sandbox_execution_node(state_strptime)
    assert result.get('execution_error') is None, f"strptime raised error: {result.get('execution_error')}"


def test_sqlite_adapter_helpers():
    try:
        state_adapter = {
            'generated_code': """
import uuid
from datetime import datetime, date
from decimal import Decimal

u = uuid.uuid4()
d = date(2026, 8, 3)
dt = datetime(2026, 8, 3, 21, 0, 0)
dec = Decimal("49.99")
meta = {"key": "value"}
items = [1, 2, 3]

assert to_sql_primitive(u) == str(u)
assert to_sql_primitive(d) == "2026-08-03"
assert to_sql_primitive(dt) == "2026-08-03T21:00:00"
assert to_sql_primitive(dec) == 49.99
assert '"key"' in to_sql_primitive(meta)

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS adapter_test (id TEXT, date_col TEXT, price REAL, data TEXT)")
    rows = [(u, d, dec, meta)]
    batch_insert(cursor, "INSERT INTO adapter_test VALUES (?, ?, ?, ?)", rows)
    cursor.execute("DELETE FROM adapter_test")
"""
        }
        result = sandbox_execution_node(state_adapter)
        assert result.get('execution_error') is None, f"SQLite adapter helpers test raised error: {result.get('execution_error')}"
    finally:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS adapter_test")
            conn.commit()

