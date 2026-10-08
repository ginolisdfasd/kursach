# Сервис выдачи книг в библиотеке

Выдаёт экземпляры книг читателям, принимает возвраты, считает просрочку и штраф, показывает сводку по фонду. Учебный сервис курсовой работы по дисциплине «Оптимизация клиент-серверных приложений», вариант 1. Автор: Андреади В. В., префикс `vladislav_andreadi`.

## Требования

- Python 3.11 (проверено на 3.11.14);
- PostgreSQL 16 (поднимается в Docker, образ `postgres:16-alpine`);
- Docker 28 с Docker Compose v2.

## Установка и запуск

    git clone <адрес репозитория>
    cd kr1-andreadi
    cp .env.example .env              # заполнить переменные (см. ниже)
    python3.11 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    set -a; . ./.env; set +a
    docker compose up -d
    .venv/bin/python -m scripts.init_db
    .venv/bin/python -m scripts.seed small
    .venv/bin/uvicorn app.main:app --port $APP_PORT

Рабочее наполнение (около 75 тысяч выдач) вместо малого:

    .venv/bin/python -m scripts.seed work

Наполнение воспроизводимо: зерно генератора и дата отсчёта фиксированы, повторный запуск очищает таблицы и даёт те же записи.

## Переменные окружения

| Переменная   | Назначение                                     | Пример |
|--------------|------------------------------------------------|--------|
| PREFIX       | префикс: имя базы, схемы и проекта Compose     | vladislav_andreadi |
| DB_PORT      | порт PostgreSQL на машине                      | 5442 |
| DB_PASSWORD  | пароль пользователя library                    | changeme |
| DATABASE_URL | подключение к базе данных                      | postgresql://library:changeme@localhost:5442/vladislav_andreadi |
| APP_PORT     | порт сервиса                                   | 18082 |
| SECRET_KEY   | ключ подписи сессионной куки                   | changeme |
| SEED         | зерно генератора наполнения                    | 2 |

## Проверка работоспособности

Интерфейс открывается по адресу http://localhost:18082, учётная запись для проверки — `demo` / `demo`; все замеры снимаются под `librarian` / `librarian`. После входа открывается список выдач с фильтром по статусу и постраничным выводом; из него — карточка выдачи и карточка читателя; сверху — «Выдать» и «Сводка».

## Тесты

    .venv/bin/python -m pytest

Тесты операций сами создают схему `vladislav_andreadi_test` и наполняют её малым объёмом; рабочая схема не затрагивается.

## Замеры

    .venv/bin/python -m scripts.measure --base http://localhost:18082 --label work --repeats 30 --warmup 5

Печатает по каждой операции p50, p95, максимум, время в базе и число запросов к базе; результат сохраняется в `results/<label>.json`. Каждый ответ сервиса несёт заголовки `X-Response-Time-Ms`, `X-DB-Time-Ms`, `X-DB-Queries`.

## Программный интерфейс

Все операции, кроме входа, требуют сессионной куки `session` (выдаётся `POST /api/login`); без неё — 401.

| Метод и путь                  | Параметры                                         | Ответ | Ошибки |
|-------------------------------|---------------------------------------------------|-------|--------|
| POST /api/login               | username, password (JSON)                         | 200, {"username", "full_name"} и кука session | 401, 422 |
| POST /api/logout              | —                                                 | 200, {"ok": true} | — |
| GET /api/loans                | page ≥ 1, size 1–100, status (active, overdue, returned), reader_id | 200, {"items": [выдача], "total", "page", "size"} | 401, 422 |
| GET /api/loans/{id}           | id выдачи                                         | 200, выдача + copy_history | 401, 404 |
| POST /api/loans               | reader_id, copy_id (JSON)                         | 201, созданная выдача | 401, 404, 409 (copy_busy, reader_has_overdue), 422 |
| POST /api/loans/{id}/return   | id выдачи                                         | 200, закрытая выдача | 401, 404, 409 (already_returned) |
| GET /api/readers/{id}         | id читателя                                       | 200, читатель + loans, on_hands, overdue, fine_total | 401, 404 |
| GET /api/books                | q (название или автор), page, size                | 200, {"items": [книга + copies, free], "total"} | 401, 422 |
| GET /api/summary              | —                                                 | 200, {"loans_total", "copies_total", "on_hands", "overdue", "overdue_share", "fines_total", "top_books"} | 401 |

Выдача: `{"id", "reader": {id, full_name, card_no}, "copy": {id, inv_no}, "book": {id, title, author}, "issued_at", "due_at", "returned_at", "status", "overdue_days", "fine"}`. Срок выдачи 14 дней, штраф 10 ₽ за день просрочки.
