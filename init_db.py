"""Создаёт схему с именем префикса и таблицы в ней (пересоздаёт, если есть)."""
from pathlib import Path

import psycopg

from app import config


def create_schema():
    sql = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text()
    sql = sql.replace(':"schema"', f'"{config.SCHEMA}"')
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute(sql)


if __name__ == "__main__":
    create_schema()
    print(f"schema {config.SCHEMA} created")
