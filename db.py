"""Пул соединений и учёт обращений к базе в пределах одного запроса.

Каждое обращение проходит через query()/execute(): вокруг него ставятся
отметки времени, а число запросов и суммарное время в базе копятся в
контекстной переменной и отдаются в заголовках X-DB-Queries и X-DB-Time-Ms.
"""
import contextvars
import time

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_stats: contextvars.ContextVar[dict | None] = contextvars.ContextVar("db_stats", default=None)

pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=2,
    max_size=10,
    open=False,
    kwargs={"options": f"-c search_path={config.SCHEMA}", "autocommit": True, "row_factory": dict_row},
)


def start_stats() -> dict:
    s = {"queries": 0, "db_ms": 0.0}
    _stats.set(s)
    return s


def _account(t0: float) -> None:
    s = _stats.get()
    if s is not None:
        s["queries"] += 1
        s["db_ms"] += (time.perf_counter() - t0) * 1000


def query(sql: str, params=None) -> list[dict]:
    with pool.connection() as conn:
        t0 = time.perf_counter()
        rows = conn.execute(sql, params).fetchall()
        _account(t0)
    return rows


def query_one(sql: str, params=None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=None) -> dict | None:
    with pool.connection() as conn:
        t0 = time.perf_counter()
        cur = conn.execute(sql, params)
        row = cur.fetchone() if cur.description else None
        _account(t0)
    return row
