"""Операции сервиса: собирают ответ из репозитория и применяют правила."""
from datetime import date

from . import repo, rules


class NotFound(Exception):
    pass


def today() -> date:
    return date.today()


def _book_short(book):
    return {"id": book["id"], "title": book["title"], "author": book["author"]}


def loan_view(loan, d: date):
    reader = repo.get_reader(loan["reader_id"])
    copy = repo.get_copy(loan["copy_id"])
    book = repo.get_book(copy["book_id"])
    days = rules.overdue_days(loan["due_at"], loan["returned_at"], d)
    return {
        "id": loan["id"],
        "reader": {"id": reader["id"], "full_name": reader["full_name"], "card_no": reader["card_no"]},
        "copy": {"id": copy["id"], "inv_no": copy["inv_no"]},
        "book": _book_short(book),
        "issued_at": loan["issued_at"].isoformat(),
        "due_at": loan["due_at"].isoformat(),
        "returned_at": loan["returned_at"].isoformat() if loan["returned_at"] else None,
        "status": "returned" if loan["returned_at"] else ("overdue" if days > 0 else "active"),
        "overdue_days": days,
        "fine": rules.fine(days),
    }


def list_loans(status, reader_id, page: int, size: int):
    d = today()
    total = repo.count_loans(status, reader_id, d)
    loans = repo.list_loans(status, reader_id, d, size, (page - 1) * size)
    return {"items": [loan_view(l, d) for l in loans], "total": total, "page": page, "size": size}


def loan_card(loan_id: int):
    d = today()
    loan = repo.get_loan(loan_id)
    if loan is None:
        raise NotFound("loan")
    view = loan_view(loan, d)
    history = repo.loans_of_copy(loan["copy_id"])
    view["copy_history"] = [
        {
            "id": h["id"],
            "reader_id": h["reader_id"],
            "issued_at": h["issued_at"].isoformat(),
            "returned_at": h["returned_at"].isoformat() if h["returned_at"] else None,
        }
        for h in history
    ]
    return view


def reader_card(reader_id: int):
    d = today()
    reader = repo.get_reader(reader_id)
    if reader is None:
        raise NotFound("reader")
    loans = [loan_view(l, d) for l in repo.loans_of_reader(reader_id)]
    return {
        "id": reader["id"],
        "full_name": reader["full_name"],
        "card_no": reader["card_no"],
        "phone": reader["phone"],
        "loans": loans,
        "on_hands": sum(1 for l in loans if l["returned_at"] is None),
        "overdue": sum(1 for l in loans if l["status"] == "overdue"),
        "fine_total": sum(l["fine"] for l in loans),
    }


def issue(reader_id: int, copy_id: int, user_id: int):
    d = today()
    if repo.get_reader(reader_id) is None:
        raise NotFound("reader")
    if repo.get_copy(copy_id) is None:
        raise NotFound("copy")
    rules.check_can_issue(repo.copy_is_busy(copy_id), repo.reader_overdue_count(reader_id, d))
    loan_id = repo.insert_loan(reader_id, copy_id, d, rules.due_date(d), user_id)
    return loan_view(repo.get_loan(loan_id), d)


def return_loan(loan_id: int):
    d = today()
    loan = repo.get_loan(loan_id)
    if loan is None:
        raise NotFound("loan")
    rules.check_can_return(loan["returned_at"])
    repo.set_returned(loan_id, d)
    return loan_view(repo.get_loan(loan_id), d)


def books(q, page: int, size: int):
    d = today()
    total = repo.count_books(q)
    items = []
    for b in repo.search_books(q, size, (page - 1) * size):
        copies = repo.copies_of_book(b["id"])
        free = sum(1 for c in copies if not repo.copy_is_busy(c["id"]))
        items.append({**_book_short(b), "year": b["year"], "copies": len(copies), "free": free})
    return {"items": items, "total": total, "page": page, "size": size}


def summary():
    d = today()
    loans = repo.all_loans_dates()
    on_hands = [l for l in loans if l["returned_at"] is None]
    overdue = [l for l in on_hands if rules.is_overdue(l["due_at"], None, d)]
    fines = sum(rules.fine(rules.overdue_days(l["due_at"], l["returned_at"], d)) for l in loans)
    return {
        "loans_total": len(loans),
        "copies_total": repo.count_copies(),
        "on_hands": len(on_hands),
        "overdue": len(overdue),
        "overdue_share": round(len(overdue) / len(on_hands), 4) if on_hands else 0.0,
        "fines_total": fines,
        "top_books": [dict(b) for b in repo.top_books(10)],
    }
