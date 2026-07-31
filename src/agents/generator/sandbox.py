import random
import datetime
import uuid
import sqlite3
from contextlib import contextmanager
from faker import Faker
from database import get_db_connection

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed_modules = {
        'sqlite3', '_sqlite3', 'random', '_random',
        'datetime', '_datetime', '_strptime', 'uuid',
        'faker', 'math', 'time', 'decimal'
    }
    if name in allowed_modules:
        return __import__(name, globals, locals, fromlist, level)
    raise ImportError(f"Import of module '{name}' is forbidden in sandbox environment.")

SAFE_BUILTINS = {
    'range': range, 'len': len, 'str': str, 'int': int, 'float': float,
    'bool': bool, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
    'print': print, 'enumerate': enumerate, 'zip': zip, 'min': min, 'max': max,
    'abs': abs, 'sum': sum, 'any': any, 'all': all, 'isinstance': isinstance,
    'getattr': getattr, 'hasattr': hasattr, 'round': round, 'map': map,
    'filter': filter, 'sorted': sorted, 'divmod': divmod, 'pow': pow,
    'ord': ord, 'chr': chr, 'hash': hash, 'next': next, 'iter': iter,
    'reversed': reversed, 'type': type, 'format': format, 'slice': slice, 'repr': repr,
    'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
    'KeyError': KeyError, 'AttributeError': AttributeError, 'IndexError': IndexError,
    'ZeroDivisionError': ZeroDivisionError, 'StopIteration': StopIteration,
    'AssertionError': AssertionError,
    '__import__': safe_import
}

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
            'Faker': Faker,
            'fake': Faker(),
            'get_db_connection': safe_get_db_connection
        }

        try:
            exec(code, safe_globals)
            conn.commit()
            return True, "Successfully executed mock data insertion script in sandbox environment."
        except Exception as e:
            conn.rollback()
            return False, f"{type(e).__name__}: {str(e)}"
