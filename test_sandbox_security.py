import os
import sys
import time

# Ensure UTF-8 stdout on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import get_db_connection, init_db
from subagents.generator import sandbox_execution_node

def test_timeout():
    print("\n--- Test 1: Execution Timeout ---")
    state = {
        "generated_code": "import time\ntime.sleep(20)"
    }
    start_time = time.time()
    result = sandbox_execution_node(state)
    elapsed = time.time() - start_time
    
    print(f"Elapsed Time: {elapsed:.2f} seconds")
    print(f"Execution Error: {result.get('execution_error')}")
    
    assert "TimeoutError" in str(result.get("execution_error")), "Test 1 Failed: Timeout error was not triggered."
    assert elapsed < 18, "Test 1 Failed: Execution exceeded timeout window significantly."
    print("[PASS] Test 1 Passed: Infinite loop / long execution timed out successfully!")

def test_authorizer_schema_protection():
    print("\n--- Test 2: SQLite Authorizer (Schema & Data Protection) ---")
    state_drop = {
        "generated_code": """
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE users")
"""
    }
    result_drop = sandbox_execution_node(state_drop)
    print(f"DROP Table Error: {result_drop.get('execution_error')}")
    assert result_drop.get("execution_error") is not None, "Test 2 Failed: DROP TABLE was permitted."
    assert "not authorized" in str(result_drop.get("execution_error")).lower(), "Test 2 Failed: Authorizer did not block DROP TABLE."

    state_delete = {
        "generated_code": """
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
"""
    }
    result_delete = sandbox_execution_node(state_delete)
    print(f"DELETE Error: {result_delete.get('execution_error')}")
    assert result_delete.get("execution_error") is None, "Test 2 Failed: DELETE should be permitted."

    print("[PASS] Test 2 Passed: Schema modification commands (DROP) were blocked by authorizer, while DELETE is permitted!")

def test_transaction_rollback():
    print("\n--- Test 3: Transaction Atomic Rollback ---")
    init_db()  # Ensure DB is in valid state
    
    test_email = "sandbox_test_user_rollback@example.com"
    
    # Verify test user does not exist initially
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE email = ?", (test_email,))
        initial_count = cursor.fetchone()['count']
    
    assert initial_count == 0, "Test 3 Setup Issue: Test email already exists."

    # Code inserts a row and then throws an error before finishing
    state_failure = {
        "generated_code": f"""
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name, email) VALUES ('Test User', '{test_email}')")
    raise ValueError("Simulated unexpected failure during insertion")
"""
    }
    
    result = sandbox_execution_node(state_failure)
    print(f"Execution Error: {result.get('execution_error')}")
    assert result.get("execution_error") is not None, "Test 3 Failed: Error was not raised."

    # Verify that partial insert was rolled back completely
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE email = ?", (test_email,))
        final_count = cursor.fetchone()['count']
        
    print(f"User count in DB after failure: {final_count}")
    assert final_count == 0, "Test 3 Failed: Partial data was persisted despite execution failure!"
    print("[PASS] Test 3 Passed: Failed executions rolled back atomically!")

def test_restricted_imports():
    print("\n--- Test 4: Restricted Import Controls ---")
    state_os = {
        "generated_code": "import os\nos.system('echo Hacked')"
    }
    result_os = sandbox_execution_node(state_os)
    print(f"Forbidden Import Error: {result_os.get('execution_error')}")
    assert result_os.get("execution_error") is not None, "Test 4 Failed: Restricted module 'os' was imported."
    assert "forbidden" in str(result_os.get("execution_error")).lower(), "Test 4 Failed: ImportError was not triggered for forbidden module."
    print("[PASS] Test 4 Passed: Forbidden modules (like 'os') were blocked by safe_import!")

def test_conn_attribute_protection():
    print("\n--- Test 5: Connection Attribute Access Protection ---")
    state_conn = {
        "generated_code": """
with get_db_connection() as conn:
    raw_conn = getattr(conn, "_conn", None)
    if raw_conn is not None:
        raise ValueError("Exposed internal _conn attribute!")
    conn.set_authorizer(None)
"""
    }
    result_conn = sandbox_execution_node(state_conn)
    print(f"Attribute Access Error: {result_conn.get('execution_error')}")
    assert result_conn.get("execution_error") is not None, "Test 5 Failed: Internal connection attribute or set_authorizer was accessible."
    assert "restricted" in str(result_conn.get("execution_error")).lower(), "Test 5 Failed: Attribute restriction error was not raised."
    print("[PASS] Test 5 Passed: Access to internal _conn and set_authorizer was blocked by SafeConn!")

def test_strptime_import():
    print("\n--- Test 6: Datetime strptime & Internal Module Import ---")
    state_strptime = {
        "generated_code": """
from datetime import datetime
dt = datetime.strptime("2026-07-29 12:00:00", "%Y-%m-%d %H:%M:%S")
assert dt.year == 2026
"""
    }
    result = sandbox_execution_node(state_strptime)
    print(f"strptime Execution Result: {result.get('execution_result')}")
    assert result.get("execution_error") is None, f"Test 6 Failed: strptime raised error: {result.get('execution_error')}"
    print("[PASS] Test 6 Passed: datetime.strptime and internal _strptime import allowed in sandbox!")

if __name__ == "__main__":
    print("==========================================")
    print(" Running Sandbox Hardening Security Tests ")
    print("==========================================")
    
    try:
        test_timeout()
        test_authorizer_schema_protection()
        test_transaction_rollback()
        test_restricted_imports()
        test_conn_attribute_protection()
        test_strptime_import()
        print("\n[SUCCESS] ALL SANDBOX SECURITY TESTS PASSED SUCCESSFULLY!")
    except AssertionError as e:
        print(f"\n[FAIL] SECURITY TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        sys.exit(1)
