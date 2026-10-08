-- Схема сервиса выдачи книг. Имя схемы подставляется из переменной PREFIX.
-- Индексов сверх первичных ключей нет: это требование первого задания.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

DROP SCHEMA IF EXISTS :"schema" CASCADE;
CREATE SCHEMA :"schema";
SET search_path TO :"schema";

CREATE TABLE app_users (
    id            serial PRIMARY KEY,
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    full_name     text NOT NULL
);

CREATE TABLE readers (
    id         serial PRIMARY KEY,
    full_name  text NOT NULL,
    card_no    text NOT NULL,
    phone      text,
    created_at date NOT NULL
);

CREATE TABLE books (
    id     serial PRIMARY KEY,
    title  text NOT NULL,
    author text NOT NULL,
    year   int  NOT NULL,
    isbn   text NOT NULL
);

CREATE TABLE copies (
    id         serial PRIMARY KEY,
    book_id    int  NOT NULL REFERENCES books(id),
    inv_no     text NOT NULL,
    shelf      text NOT NULL
);

CREATE TABLE loans (
    id          serial PRIMARY KEY,
    reader_id   int  NOT NULL REFERENCES readers(id),
    copy_id     int  NOT NULL REFERENCES copies(id),
    issued_at   date NOT NULL,
    due_at      date NOT NULL,
    returned_at date,
    issued_by   int  NOT NULL REFERENCES app_users(id)
);
