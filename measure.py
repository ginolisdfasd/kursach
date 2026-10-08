"""Замер времени ответа операций контракта.

Для каждой операции: прогрев (в расчёт не входит), затем серия повторов.
Время берётся на стороне клиента вокруг запроса; из заголовков ответа
берутся время в базе (X-DB-Time-Ms) и число запросов к базе (X-DB-Queries).

    python -m scripts.measure --label small --repeats 30 --warmup 5
"""
import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import httpx
import psycopg

from app import config

LOAN_ID = 100      # карточка выдачи: одна и та же запись на обоих объёмах
READER_ID = 10     # карточка читателя


def pct(values, p):
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def free_pairs(n):
    """Свободные экземпляры и читатели без просрочек — для замера выдачи."""
    with psycopg.connect(config.DATABASE_URL, options=f"-c search_path={config.SCHEMA}") as conn:
        copies = [r[0] for r in conn.execute(
            "SELECT c.id FROM copies c WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.copy_id = c.id "
            "AND l.returned_at IS NULL) ORDER BY c.id DESC LIMIT %s", (n,))]
        readers = [r[0] for r in conn.execute(
            "SELECT r.id FROM readers r WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.reader_id = r.id "
            "AND l.returned_at IS NULL AND l.due_at < current_date) ORDER BY r.id DESC LIMIT %s", (n,))]
    return list(zip(copies, readers))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--label", required=True)
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--user", default="librarian")
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base, timeout=120)

    def call(method, url, **kw):
        t0 = time.perf_counter()
        r = c.request(method, url, **kw)
        ms = (time.perf_counter() - t0) * 1000
        return r, {"ms": ms, "db_ms": float(r.headers.get("x-db-time-ms", 0)),
                   "queries": int(r.headers.get("x-db-queries", 0)), "status": r.status_code,
                   "bytes": len(r.content)}

    r, _ = call("POST", "/api/login", json={"username": args.user, "password": args.user})
    assert r.status_code == 200, r.text

    gets = [
        ("Список выдач", "GET /api/loans?page=1&size=20"),
        ("Список просроченных", "GET /api/loans?status=overdue&page=1&size=20"),
        ("Карточка выдачи", f"GET /api/loans/{LOAN_ID}"),
        ("Карточка читателя", f"GET /api/readers/{READER_ID}"),
        ("Список книг", "GET /api/books?page=1&size=20"),
        ("Поиск книг", "GET /api/books?q=маяк&page=1&size=20"),
        ("Сводка", "GET /api/summary"),
    ]
    samples: dict[str, list] = {}
    for name, spec in gets:
        method, url = spec.split(" ", 1)
        for _ in range(args.warmup):
            call(method, url)
        samples[spec] = []
        for _ in range(args.repeats):
            r, m = call(method, url)
            assert r.status_code == 200, (spec, r.status_code)
            samples[spec].append(m)

    # запись: выдача и возврат парами, чтобы данные не менялись от замера к замеру
    pairs = free_pairs(args.warmup + args.repeats)
    issue, ret = "POST /api/loans", "POST /api/loans/{id}/return"
    samples[issue], samples[ret] = [], []
    for i, (copy_id, reader_id) in enumerate(pairs):
        r, m1 = call("POST", "/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
        assert r.status_code == 201, r.text
        r2, m2 = call("POST", f"/api/loans/{r.json()['id']}/return")
        assert r2.status_code == 200
        if i >= args.warmup:
            samples[issue].append(m1)
            samples[ret].append(m2)
    for _ in range(args.warmup):
        call("POST", "/api/login", json={"username": args.user, "password": args.user})
    login = "POST /api/login"
    samples[login] = []
    for _ in range(args.repeats):
        r, m = call("POST", "/api/login", json={"username": args.user, "password": args.user})
        samples[login].append(m)

    names = dict((s, n) for n, s in gets) | {issue: "Выдача экземпляра", ret: "Приём возврата", login: "Вход"}
    out = {"label": args.label, "repeats": args.repeats, "warmup": args.warmup, "user": args.user,
           "machine": f"{platform.machine()} {platform.platform()}", "written_loans": len(pairs), "ops": []}
    print(f"{'операция':<48}{'p50':>9}{'p95':>9}{'max':>9}{'в БД p50':>10}{'запр.':>7}")
    for spec, ms in samples.items():
        t = [m["ms"] for m in ms]
        row = {"op": spec, "name": names[spec], "p50": statistics.median(t), "p95": pct(t, 95), "max": max(t),
               "db_p50": statistics.median(m["db_ms"] for m in ms), "queries": statistics.median(m["queries"] for m in ms),
               "bytes": statistics.median(m["bytes"] for m in ms), "n": len(t)}
        out["ops"].append(row)
        print(f"{spec:<48}{row['p50']:>9.2f}{row['p95']:>9.2f}{row['max']:>9.2f}{row['db_p50']:>10.2f}{row['queries']:>7.0f}")
    Path("results").mkdir(exist_ok=True)
    Path(f"results/{args.label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"повторов {args.repeats}, прогрев {args.warmup}, учётная запись {args.user}, записано выдач {len(pairs)}")


if __name__ == "__main__":
    main()
