"""Наполнение базы. Воспроизводимо: фиксированное зерно и фиксированная дата отсчёта.

    python -m scripts.seed small   # малое наполнение
    python -m scripts.seed work    # рабочее наполнение
"""
import argparse
import random
from datetime import date, timedelta

import psycopg

from app import config
from app.auth import hash_password
from app.rules import LOAN_DAYS

SIZES = {
    #        читатели книги экземпляры выдачи
    "small": (50, 100, 200, 300),
    "work": (3000, 10000, 30000, 80000),
}
SEED = int(__import__("os").environ.get("SEED", "1"))
ANCHOR = date(2026, 10, 5)      # «сегодня» генератора: выдачи идут за год до этой даты
HISTORY_DAYS = 365

LAST = ["Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов", "Попов", "Васильев", "Соколов",
        "Михайлов", "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов",
        "Егоров", "Павлов", "Козлов", "Степанов", "Николаев", "Орлов", "Андреев", "Макаров"]
FIRST_M = ["Борис", "Глеб", "Егор", "Иван", "Лев", "Никита", "Павел", "Роман", "Тимур", "Фёдор"]
FIRST_F = ["Анна", "Вера", "Дарья", "Жанна", "Ксения", "Мария", "Ольга", "София", "Ульяна", "Юлия"]
ADJ = ["Тихий", "Северный", "Последний", "Забытый", "Красный", "Ночной", "Долгий", "Белый",
       "Старый", "Морской", "Далёкий", "Ясный", "Каменный", "Зимний", "Тайный", "Новый"]
NOUN = ["сад", "берег", "город", "путь", "дом", "лес", "ветер", "остров", "мост", "огонь",
        "архив", "маяк", "перевал", "колокол", "край", "след", "свет", "час", "век", "мир"]
AUTH_LAST = ["Арсеньев", "Белов", "Воронцов", "Горский", "Данилов", "Ершов", "Жуков", "Зорин",
             "Ильин", "Каменев", "Ларин", "Мельников", "Нестеров", "Осипов", "Прохоров", "Рябов"]


def gen(size: str):
    n_readers, n_books, n_copies, n_loans = SIZES[size]
    rnd = random.Random(SEED)

    readers = []
    for i in range(1, n_readers + 1):
        female = rnd.random() < 0.5
        name = f"{rnd.choice(LAST)}{'а' if female else ''} {rnd.choice(FIRST_F if female else FIRST_M)}"
        readers.append((i, name, f"Ч-{i:06d}", f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                        ANCHOR - timedelta(days=rnd.randint(400, 3000))))

    books = []
    for i in range(1, n_books + 1):
        title = f"{rnd.choice(ADJ)} {rnd.choice(NOUN)}" + (f". Книга {rnd.randint(2, 5)}" if rnd.random() < 0.15 else "")
        author = f"{rnd.choice(AUTH_LAST)} {rnd.choice('АБВГДЕИКЛМНОПРС')}. {rnd.choice('АБВГДЕИКЛМНОПРС')}."
        books.append((i, title, author, rnd.randint(1950, 2026), f"978-5-{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}-{i % 10}"))

    # экземпляры: у каждой книги хотя бы один, остальные — по случайным книгам
    copies = []
    for i in range(1, n_copies + 1):
        book_id = i if i <= n_books else rnd.randint(1, n_books)
        copies.append((i, book_id, f"ИНВ-{i:07d}", f"{rnd.choice('АБВГД')}-{rnd.randint(1, 40)}"))

    # популярность книг неравномерна: часть фонда берут заметно чаще
    weight = {b[0]: (1.0 / (1 + (rnd.random() * 50))) for b in books}
    copy_w = [weight[c[1]] for c in copies]

    # выдачи раскладываются по экземплярам, внутри экземпляра идут друг за другом без наложений
    per_copy: dict[int, int] = {}
    for cid in rnd.choices([c[0] for c in copies], weights=copy_w, k=n_loans):
        per_copy[cid] = per_copy.get(cid, 0) + 1

    loans = []
    lid = 0
    for cid in sorted(per_copy):
        k = per_copy[cid]
        step = HISTORY_DAYS // k
        day = ANCHOR - timedelta(days=HISTORY_DAYS)
        for j in range(k):
            issued = day + timedelta(days=rnd.randint(0, max(0, step - 1)))
            last = j == k - 1
            if last and rnd.random() < 0.35:
                # книга на руках: чаще взята недавно, реже — давно и просрочена
                back = rnd.randint(1, 14) if rnd.random() < 0.8 else rnd.randint(15, 90)
                issued = max(day, ANCHOR - timedelta(days=back))
                returned = None
            elif issued >= ANCHOR:
                break
            else:
                returned = issued + timedelta(days=rnd.choice([3, 7, 10, 12, 14, 14, 16, 20, 30]))
                if returned > ANCHOR:
                    returned = None
            due = issued + timedelta(days=LOAN_DAYS)
            lid += 1
            loans.append((lid, rnd.randint(1, n_readers), cid, issued, due, returned, 1))
            day = (returned or issued) + timedelta(days=1)
            if returned is None or day >= ANCHOR:
                break
    return readers, books, copies, loans


def load(size: str):
    readers, books, copies, loans = gen(size)
    with psycopg.connect(config.DATABASE_URL, options=f"-c search_path={config.SCHEMA}") as conn:
        conn.execute("TRUNCATE loans, copies, books, readers, app_users RESTART IDENTITY CASCADE")
        conn.execute(
            "INSERT INTO app_users (username, password_hash, full_name) VALUES (%s, %s, %s), (%s, %s, %s)",
            ("librarian", hash_password("librarian"), "Библиотекарь (замеры)",
             "demo", hash_password("demo"), "Демонстрационная учётная запись"),
        )
        with conn.cursor() as cur:
            for table, cols, rows in [
                ("readers", "id, full_name, card_no, phone, created_at", readers),
                ("books", "id, title, author, year, isbn", books),
                ("copies", "id, book_id, inv_no, shelf", copies),
                ("loans", "id, reader_id, copy_id, issued_at, due_at, returned_at, issued_by", loans),
            ]:
                with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
            for t in ("readers", "books", "copies", "loans"):
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT max(id) FROM {t}))")
        conn.execute("ANALYZE")
    return len(readers), len(books), len(copies), len(loans)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("size", choices=SIZES)
    size = ap.parse_args().size
    readers, books, copies, loans = load(size)
    print(f"{size}: readers={readers} books={books} copies={copies} loans={loans}")


if __name__ == "__main__":
    main()
