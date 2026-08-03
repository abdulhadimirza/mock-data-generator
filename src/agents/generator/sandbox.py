import random
import datetime
import uuid
import sqlite3
import json
import decimal
from decimal import Decimal
from enum import Enum
from contextlib import contextmanager
from faker import Faker
from database import get_db_connection

import builtins

def to_sql_primitive(val):
    """Converts complex Python types to SQLite primitive values (str, int, float, bytes, None)."""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bytes)):
        return val
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, Enum):
        return to_sql_primitive(val.value)
    if isinstance(val, tuple):
        return tuple(to_sql_primitive(item) for item in val)
    if isinstance(val, (dict, list, set)):
        return json.dumps(val, default=str)
    return str(val)

def batch_insert(cursor, sql, data_rows):
    """
    Executes cursor.executemany on data_rows after converting all complex types in data_rows
    to SQLite-compatible primitives using to_sql_primitive.
    """
    converted_rows = (
        to_sql_primitive(row) if isinstance(row, (tuple, list)) else to_sql_primitive(row)
        for row in data_rows
    )
    cursor.executemany(sql, converted_rows)

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    forbidden_modules = {
        'os', 'sys', 'subprocess', 'shutil', 'socket', 'importlib', 
        'multiprocessing', 'threading', 'ctypes', 'winreg', 'pty', 'fcntl',
        'builtins', 'gc', 'pdb', 'syslog', 'urllib', 'http'
    }
    
    root_module = name.split('.')[0]
    if root_module in forbidden_modules:
        raise ImportError(f"Import of module '{name}' is forbidden in sandbox environment.")
        
    return __import__(name, globals, locals, fromlist, level)

SAFE_BUILTINS = {k: v for k, v in builtins.__dict__.items() if k not in {
    'eval', 'exec', 'open', 'compile', '__import__', 'input', 'breakpoint',
    'memoryview', 'delattr', 'setattr', 'globals', 'locals', 'vars'
}}
SAFE_BUILTINS['__import__'] = safe_import

def run_in_sandbox(code: str, safe_builtins: dict = None):
    if safe_builtins is None:
        safe_builtins = SAFE_BUILTINS
    with get_db_connection() as conn:
        def authorizer(action_code, arg1, arg2, dbname, source):
            forbidden = {
                sqlite3.SQLITE_DROP_TABLE,
                sqlite3.SQLITE_ALTER_TABLE,
                sqlite3.SQLITE_DROP_INDEX,
                sqlite3.SQLITE_DROP_TRIGGER,
                sqlite3.SQLITE_DROP_VIEW,
                sqlite3.SQLITE_DROP_VTABLE
            }
            if action_code in forbidden:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)

        class SafeConn:
            def __init__(self, *args, **kwargs):
                pass

            def cursor(self):
                return conn.cursor()

            def commit(self):
                pass  # Ignore manual commits in LLM script to ensure overall transaction atomicity

            def rollback(self):
                conn.rollback()

            def close(self):
                pass  # Managed by parent context manager

            def __getattr__(self, item):
                if item.startswith('_') or item == 'set_authorizer':
                    raise AttributeError(f"Access to '{item}' is restricted.")
                return getattr(conn, item)

        @contextmanager
        def safe_get_db_connection():
            yield SafeConn()

        safe_globals = {
            '__name__': '__main__',
            '__builtins__': safe_builtins,
            'sqlite3': sqlite3,
            'random': random,
            'datetime': datetime,
            'uuid': uuid,
            'Decimal': Decimal,
            'decimal': decimal,
            'json': json,
            'Faker': Faker,
            'fake': Faker(),
            'get_db_connection': safe_get_db_connection,
            'to_sql_primitive': to_sql_primitive,
            'batch_insert': batch_insert
        }

        try:
            exec(code, safe_globals)
            conn.commit()
            return True, "Successfully executed mock data insertion script in sandbox environment."
        except Exception as e:
            conn.rollback()
            return False, f"{type(e).__name__}: {str(e)}"
