import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import auth, config, db, services
from .rules import RuleViolation


@asynccontextmanager
async def lifespan(app):
    db.pool.open(wait=True)
    yield
    db.pool.close()


app = FastAPI(title=f"Библиотека ({config.PREFIX})", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["prefix"] = config.PREFIX

Status = Literal["active", "overdue", "returned"]


@app.middleware("http")
async def timing(request: Request, call_next):
    stats = db.start_stats()
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - t0) * 1000:.2f}"
    response.headers["X-DB-Time-Ms"] = f"{stats['db_ms']:.2f}"
    response.headers["X-DB-Queries"] = str(stats["queries"])
    return response


@app.exception_handler(services.NotFound)
async def not_found(request, exc):
    return JSONResponse({"detail": f"{exc} not found"}, status_code=404)


@app.exception_handler(RuleViolation)
async def rule_violation(request, exc: RuleViolation):
    return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=409)


# ---------- программный интерфейс ----------

class LoginIn(BaseModel):
    username: str
    password: str


class LoanIn(BaseModel):
    reader_id: int
    copy_id: int


@app.post("/api/login")
def api_login(body: LoginIn):
    user = auth.check_credentials(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Неверное имя или пароль")
    resp = JSONResponse({"username": user["username"], "full_name": user["full_name"]})
    resp.set_cookie(auth.COOKIE, auth.sign(user["username"]), httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/loans")
def api_loans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=config.PAGE_SIZE_MAX),
    status: Status | None = None,
    reader_id: int | None = None,
    user=Depends(auth.current_user),
):
    return services.list_loans(status, reader_id, page, size)


@app.get("/api/loans/{loan_id}")
def api_loan(loan_id: int, user=Depends(auth.current_user)):
    return services.loan_card(loan_id)


@app.post("/api/loans", status_code=201)
def api_issue(body: LoanIn, user=Depends(auth.current_user)):
    return services.issue(body.reader_id, body.copy_id, user["id"])


@app.post("/api/loans/{loan_id}/return")
def api_return(loan_id: int, user=Depends(auth.current_user)):
    return services.return_loan(loan_id)


@app.get("/api/readers/{reader_id}")
def api_reader(reader_id: int, user=Depends(auth.current_user)):
    return services.reader_card(reader_id)


@app.get("/api/books")
def api_books(
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=config.PAGE_SIZE_MAX),
    user=Depends(auth.current_user),
):
    return services.books(q, page, size)


@app.get("/api/summary")
def api_summary(user=Depends(auth.current_user)):
    return services.summary()


# ---------- клиентская часть: страницы сервера ----------

def page_user(request: Request):
    try:
        return auth.current_user(request)
    except HTTPException:
        return None


def need_login():
    return RedirectResponse("/login", status_code=303)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/loans", status_code=303)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse(request, "login.html", {"error": error, "user": None})


@app.post("/login", include_in_schema=False)
def login_form(username: str = Form(...), password: str = Form(...)):
    user = auth.check_credentials(username, password)
    if user is None:
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/loans", status_code=303)
    resp.set_cookie(auth.COOKIE, auth.sign(user["username"]), httponly=True, samesite="lax")
    return resp


@app.get("/logout", include_in_schema=False)
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/loans", response_class=HTMLResponse, include_in_schema=False)
def loans_page(request: Request, page: int = 1, status: str = "", reader_id: str = ""):
    user = page_user(request)
    if user is None:
        return need_login()
    st = status if status in ("active", "overdue", "returned") else None
    rid = int(reader_id) if reader_id.isdigit() else None
    data = services.list_loans(st, rid, max(page, 1), 20)
    pages = max(1, (data["total"] + 19) // 20)
    return templates.TemplateResponse(request, "loans.html", {
        "user": user, "data": data, "status": status, "reader_id": reader_id, "pages": pages,
    })


@app.get("/loans/new", response_class=HTMLResponse, include_in_schema=False)
def new_loan_page(request: Request, error: str | None = None):
    user = page_user(request)
    if user is None:
        return need_login()
    return templates.TemplateResponse(request, "new_loan.html", {"user": user, "error": error})


@app.post("/loans/new", include_in_schema=False)
def new_loan_form(request: Request, reader_id: int = Form(...), copy_id: int = Form(...)):
    user = page_user(request)
    if user is None:
        return need_login()
    try:
        loan = services.issue(reader_id, copy_id, user["id"])
    except (RuleViolation, services.NotFound) as e:
        msg = e.message if isinstance(e, RuleViolation) else f"Не найден объект: {e}"
        return templates.TemplateResponse(request, "new_loan.html", {"user": user, "error": msg}, status_code=409)
    return RedirectResponse(f"/loans/{loan['id']}", status_code=303)


@app.get("/loans/{loan_id}", response_class=HTMLResponse, include_in_schema=False)
def loan_page(request: Request, loan_id: int):
    user = page_user(request)
    if user is None:
        return need_login()
    try:
        loan = services.loan_card(loan_id)
    except services.NotFound:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "loan.html", {"user": user, "loan": loan})


@app.post("/loans/{loan_id}/return", include_in_schema=False)
def return_form(request: Request, loan_id: int):
    if page_user(request) is None:
        return need_login()
    try:
        services.return_loan(loan_id)
    except RuleViolation:
        pass
    return RedirectResponse(f"/loans/{loan_id}", status_code=303)


@app.get("/readers/{reader_id}", response_class=HTMLResponse, include_in_schema=False)
def reader_page(request: Request, reader_id: int):
    user = page_user(request)
    if user is None:
        return need_login()
    try:
        reader = services.reader_card(reader_id)
    except services.NotFound:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "reader.html", {"user": user, "reader": reader})


@app.get("/books", response_class=HTMLResponse, include_in_schema=False)
def books_page(request: Request, q: str = "", page: int = 1):
    user = page_user(request)
    if user is None:
        return need_login()
    data = services.books(q or None, max(page, 1), 20)
    pages = max(1, (data["total"] + 19) // 20)
    return templates.TemplateResponse(request, "books.html", {"user": user, "data": data, "q": q, "pages": pages})


@app.get("/summary", response_class=HTMLResponse, include_in_schema=False)
def summary_page(request: Request):
    user = page_user(request)
    if user is None:
        return need_login()
    return templates.TemplateResponse(request, "summary.html", {"user": user, "s": services.summary()})
