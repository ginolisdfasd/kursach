"""Тесты операций работают с отдельной схемой <префикс>_test.

Схема создаётся и наполняется малым объёмом автоматически при запуске
набора, рабочая схема сервиса не затрагивается.
"""
import os

os.environ["DB_SCHEMA"] = os.environ.get("PREFIX", "library") + "_test"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.init_db import create_schema
from scripts.seed import load


@pytest.fixture(scope="session")
def client():
    create_schema()
    load("small")
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_client(client):
    r = client.post("/api/login", json={"username": "librarian", "password": "librarian"})
    assert r.status_code == 200
    return client


@pytest.fixture
def anon_client(client):
    cookies = dict(client.cookies)
    client.cookies.clear()
    yield client
    for k, v in cookies.items():
        client.cookies.set(k, v)
