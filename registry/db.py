"""
registry.db — Thread-safe Postgres connection pool.

Uses ThreadedConnectionPool (not SimpleConnectionPool) because FastAPI runs
sync handlers in a thread pool. The pool is initialised lazily on first use
with a double-checked lock to prevent duplicate pool creation under concurrent
startup. release_conn() always rolls back before returning a connection so the
next caller is never handed a connection in an aborted transaction state.
"""
import os
import threading
import psycopg2
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

_pool = None
_pool_lock = threading.Lock()


def get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.getenv("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL environment variable is not set")
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=dsn,
                )
    return _pool


def get_conn():
    return get_pool().getconn()


def release_conn(conn):
    try:
        conn.rollback()
    except Exception:
        pass
    get_pool().putconn(conn)
