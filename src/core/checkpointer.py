import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

def get_checkpointer() -> SqliteSaver:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_db_path = os.getenv('CHECKPOINT_DB_PATH', 'checkpoints.db')
    db_path = raw_db_path if os.path.isabs(raw_db_path) else os.path.abspath(os.path.join(project_root, raw_db_path))
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
