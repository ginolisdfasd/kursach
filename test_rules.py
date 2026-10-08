"""Бизнес-правила варианта 1 на подготовленных данных, без обращения к сервису."""
from datetime import date

import pytest

from app import rules


def test_due_date_is_fourteen_days_after_issue():
    assert rules.due_date(date(2026, 10, 1)) == date(2026, 10, 15)


def test_return_in_time_has_no_overdue_and_no_fine():
    days = rules.overdue_days(date(2026, 10, 15), date(2026, 10, 15), today=date(2026, 11, 1))
    assert days == 0
    assert rules.fine(days) == 0


def test_late_return_counts_overdue_and_fine():
    days = rules.overdue_days(date(2026, 10, 15), date(2026, 10, 20), today=date(2026, 11, 1))
    assert days == 5
    assert rules.fine(days) == 5 * rules.FINE_PER_DAY


def test_not_returned_book_is_overdue_relative_to_today():
    assert rules.overdue_days(date(2026, 10, 1), None, today=date(2026, 10, 8)) == 7
    assert rules.is_overdue(date(2026, 10, 1), None, today=date(2026, 10, 8))
    assert not rules.is_overdue(date(2026, 10, 9), None, today=date(2026, 10, 8))


def test_busy_copy_is_not_issued():
    with pytest.raises(rules.RuleViolation) as e:
        rules.check_can_issue(copy_is_busy=True, reader_overdue_count=0)
    assert e.value.code == "copy_busy"


def test_reader_with_overdue_loans_is_refused():
    with pytest.raises(rules.RuleViolation) as e:
        rules.check_can_issue(copy_is_busy=False, reader_overdue_count=1)
    assert e.value.code == "reader_has_overdue"


def test_free_copy_is_issued_to_reader_without_debts():
    rules.check_can_issue(copy_is_busy=False, reader_overdue_count=0)


def test_closed_loan_cannot_be_returned_twice():
    with pytest.raises(rules.RuleViolation):
        rules.check_can_return(date(2026, 10, 1))
