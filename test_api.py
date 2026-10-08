"""Операции контракта: код ответа, состав полей, авторизация, неверные параметры."""
from app import db
from scripts.seed import gen

SMALL_LOANS = len(gen("small")[3])

LOAN_FIELDS = {"id", "reader", "copy", "book", "issued_at", "due_at", "returned_at",
               "status", "overdue_days", "fine"}


def free_copy_and_clean_reader():
    with db.pool.connection() as conn:
        copy_id = conn.execute(
            "SELECT c.id FROM copies c WHERE NOT EXISTS "
            "(SELECT 1 FROM loans l WHERE l.copy_id = c.id AND l.returned_at IS NULL) ORDER BY c.id LIMIT 1"
        ).fetchone()["id"]
        reader_id = conn.execute(
            "SELECT r.id FROM readers r WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.reader_id = r.id "
            "AND l.returned_at IS NULL AND l.due_at < current_date) ORDER BY r.id LIMIT 1"
        ).fetchone()["id"]
    return copy_id, reader_id


def test_login_with_wrong_password_is_401(client):
    r = client.post("/api/login", json={"username": "librarian", "password": "wrong"})
    assert r.status_code == 401


def test_endpoints_require_authorization(anon_client):
    for url in ["/api/loans", "/api/loans/1", "/api/readers/1", "/api/books", "/api/summary"]:
        assert anon_client.get(url).status_code == 401, url
    assert anon_client.post("/api/loans", json={"reader_id": 1, "copy_id": 1}).status_code == 401


def test_loans_list_returns_requested_page(auth_client):
    r = auth_client.get("/api/loans?page=1&size=20")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == SMALL_LOANS
    assert set(body["items"][0]) == LOAN_FIELDS


def test_loans_filter_overdue_returns_only_overdue(auth_client):
    body = auth_client.get("/api/loans?status=overdue&size=100").json()
    assert body["total"] > 0
    assert all(i["status"] == "overdue" and i["fine"] > 0 for i in body["items"])


def test_loans_list_rejects_bad_parameters(auth_client):
    assert auth_client.get("/api/loans?size=1000").status_code == 422
    assert auth_client.get("/api/loans?page=0").status_code == 422
    assert auth_client.get("/api/loans?status=lost").status_code == 422


def test_loan_card_has_related_entities(auth_client):
    r = auth_client.get("/api/loans/1")
    assert r.status_code == 200
    body = r.json()
    assert LOAN_FIELDS <= set(body)
    assert body["copy_history"]
    assert auth_client.get("/api/loans/999999").status_code == 404


def test_reader_card(auth_client):
    r = auth_client.get("/api/readers/1")
    assert r.status_code == 200
    assert {"id", "full_name", "loans", "on_hands", "overdue", "fine_total"} <= set(r.json())
    assert auth_client.get("/api/readers/999999").status_code == 404


def test_books_list_shows_free_copies(auth_client):
    body = auth_client.get("/api/books?size=10").json()
    assert body["total"] == 100
    assert all(0 <= b["free"] <= b["copies"] for b in body["items"])


def test_summary_fields(auth_client):
    body = auth_client.get("/api/summary").json()
    assert body["loans_total"] == SMALL_LOANS
    assert body["copies_total"] == 200
    assert 0 <= body["overdue"] <= body["on_hands"]
    assert len(body["top_books"]) == 10


def test_issue_and_return_cycle(auth_client):
    copy_id, reader_id = free_copy_and_clean_reader()
    r = auth_client.post("/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
    assert r.status_code == 201
    loan = r.json()
    assert loan["status"] == "active" and loan["returned_at"] is None
    # тот же экземпляр второй раз не выдаётся
    again = auth_client.post("/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
    assert again.status_code == 409 and again.json()["code"] == "copy_busy"
    r = auth_client.post(f"/api/loans/{loan['id']}/return")
    assert r.status_code == 200 and r.json()["status"] == "returned"
    assert auth_client.post(f"/api/loans/{loan['id']}/return").status_code == 409


def test_issue_refused_for_reader_with_overdue(auth_client):
    overdue = auth_client.get("/api/loans?status=overdue&size=1").json()["items"][0]
    copy_id, _ = free_copy_and_clean_reader()
    r = auth_client.post("/api/loans", json={"reader_id": overdue["reader"]["id"], "copy_id": copy_id})
    assert r.status_code == 409 and r.json()["code"] == "reader_has_overdue"


def test_issue_unknown_reader_is_404_and_bad_body_is_422(auth_client):
    assert auth_client.post("/api/loans", json={"reader_id": 999999, "copy_id": 1}).status_code == 404
    assert auth_client.post("/api/loans", json={"reader_id": "x"}).status_code == 422


def test_loans_page_shows_copy_inventory_number(auth_client):
    # регресс: в шаблоне l.copy возвращал метод dict.copy, колонка «Экз.» была пустой
    r = auth_client.get("/loans")
    assert r.status_code == 200
    assert "ИНВ-" in r.text
