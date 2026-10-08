"""Бизнес-правила варианта 1: выдача книг в библиотеке.

Функции чистые: не обращаются к базе и не зависят от текущей даты,
поэтому проверяются модульными тестами на подготовленных данных.
"""
from datetime import date, timedelta

LOAN_DAYS = 14          # срок выдачи, дней
FINE_PER_DAY = 10       # штраф за день просрочки, руб.


class RuleViolation(Exception):
    """Нарушение бизнес-правила: операция отклоняется с кодом 409."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def due_date(issued_at: date) -> date:
    return issued_at + timedelta(days=LOAN_DAYS)


def overdue_days(due_at: date, returned_at: date | None, today: date) -> int:
    """Разница между сроком возврата и фактической датой (или сегодняшней, если книга на руках)."""
    end = returned_at or today
    return max(0, (end - due_at).days)


def fine(days_overdue: int) -> int:
    return days_overdue * FINE_PER_DAY


def is_overdue(due_at: date, returned_at: date | None, today: date) -> bool:
    return returned_at is None and due_at < today


def check_can_issue(copy_is_busy: bool, reader_overdue_count: int) -> None:
    """Экземпляр выдаётся, если он свободен и у читателя нет просроченных выдач."""
    if copy_is_busy:
        raise RuleViolation("copy_busy", "Экземпляр уже выдан другому читателю")
    if reader_overdue_count > 0:
        raise RuleViolation("reader_has_overdue", "У читателя есть просроченные выдачи")


def check_can_return(returned_at: date | None) -> None:
    if returned_at is not None:
        raise RuleViolation("already_returned", "Выдача уже закрыта")
