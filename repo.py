"""Доступ к данным: по функции на сущность и на типовую выборку."""
from datetime import date

from .db import execute, query, query_one


def get_user_by_name(username: str):
    return query_one("SELECT * FROM app_users WHERE username = %s", (username,))


def get_reader(reader_id: int):
    return query_one("SELECT * FROM readers WHERE id = %s", (reader_id,))


def get_book(book_id: int):
    return query_one("SELECT * FROM books WHERE id = %s", (book_id,))


def get_copy(copy_id: int):
    return query_one("SELECT * FROM copies WHERE id = %s", (copy_id,))


def get_loan(loan_id: int):
    return query_one("SELECT * FROM loans WHERE id = %s", (loan_id,))


def _loan_filter(status: str | None, reader_id: int | None, today: date):
    where, params = [], []
    if status == "active":
        where.append("returned_at IS NULL")
    elif status == "overdue":
        where.append("returned_at IS NULL AND due_at < %s")
        params.append(today)
    elif status == "returned":
        where.append("returned_at IS NOT NULL")
    if reader_id is not None:
        where.append("reader_id = %s")
        params.append(reader_id)
    sql = (" WHERE " + " AND ".join(where)) if where else ""
    return sql, params


def count_loans(status, reader_id, today) -> int:
    where, params = _loan_filter(status, reader_id, today)
    return query_one("SELECT count(*) AS n FROM loans" + where, params)["n"]


def list_loans(status, reader_id, today, limit: int, offset: int):
    where, params = _loan_filter(status, reader_id, today)
    return query(
        "SELECT * FROM loans" + where + " ORDER BY issued_at DESC, id DESC LIMIT %s OFFSET %s",
        params + [limit, offset],
    )


def loans_of_reader(reader_id: int):
    return query("SELECT * FROM loans WHERE reader_id = %s ORDER BY issued_at DESC", (reader_id,))


def loans_of_copy(copy_id: int):
    return query("SELECT * FROM loans WHERE copy_id = %s ORDER BY issued_at DESC", (copy_id,))


def copy_is_busy(copy_id: int) -> bool:
    return query_one(
        "SELECT 1 AS x FROM loans WHERE copy_id = %s AND returned_at IS NULL LIMIT 1", (copy_id,)
    ) is not None


def reader_overdue_count(reader_id: int, today: date) -> int:
    return query_one(
        "SELECT count(*) AS n FROM loans WHERE reader_id = %s AND returned_at IS NULL AND due_at < %s",
        (reader_id, today),
    )["n"]


def insert_loan(reader_id, copy_id, issued_at, due_at, user_id):
    return execute(
        "INSERT INTO loans (reader_id, copy_id, issued_at, due_at, issued_by)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (reader_id, copy_id, issued_at, due_at, user_id),
    )["id"]


def set_returned(loan_id: int, returned_at: date):
    execute("UPDATE loans SET returned_at = %s WHERE id = %s", (returned_at, loan_id))


def search_books(q: str | None, limit: int, offset: int):
    if q:
        pat = f"%{q}%"
        return query(
            "SELECT * FROM books WHERE title ILIKE %s OR author ILIKE %s ORDER BY title, id LIMIT %s OFFSET %s",
            (pat, pat, limit, offset),
        )
    return query("SELECT * FROM books ORDER BY title, id LIMIT %s OFFSET %s", (limit, offset))


def count_books(q: str | None) -> int:
    if q:
        pat = f"%{q}%"
        return query_one(
            "SELECT count(*) AS n FROM books WHERE title ILIKE %s OR author ILIKE %s", (pat, pat)
        )["n"]
    return query_one("SELECT count(*) AS n FROM books")["n"]


def copies_of_book(book_id: int):
    return query("SELECT * FROM copies WHERE book_id = %s ORDER BY id", (book_id,))


def all_loans_dates():
    return query("SELECT id, due_at, returned_at FROM loans")


def top_books(limit: int = 10):
    return query(
        "SELECT b.id, b.title, b.author, count(*) AS loans"
        " FROM loans l JOIN copies c ON c.id = l.copy_id JOIN books b ON b.id = c.book_id"
        " GROUP BY b.id, b.title, b.author ORDER BY loans DESC, b.id LIMIT %s",
        (limit,),
    )


def count_copies() -> int:
    return query_one("SELECT count(*) AS n FROM copies")["n"]
