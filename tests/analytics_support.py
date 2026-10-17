"""Nur Tests: echter SereneDB-Transport, bis Bereich 2 tools.db liefert.

Fixtures werden als CTEs eingebettet. Es werden keine Tabellen angelegt,
verändert oder gelöscht. Das ist ausdrücklich kein produktiver DB-Helfer.
"""
import os
import time


def connect():
    import psycopg
    from dotenv import load_dotenv
    load_dotenv()
    return psycopg.connect(
        os.getenv("ANALYTICS_TEST_DSN") or os.getenv("DB_DSN", "host=127.0.0.1 port=7890 dbname=postgres user=postgres"),
        autocommit=True, cursor_factory=psycopg.ClientCursor, connect_timeout=5,
    )


class SereneQuery:
    def __init__(self, connection, fixtures=None):
        self.connection = connection
        self.fixtures = fixtures
        self.evidence = []

    def __call__(self, sql, params=None, limit=200):
        from psycopg.rows import dict_row
        params = list(params or [])
        if self.fixtures:
            assert sql.startswith("WITH "), "Fixture benötigt eine WITH-Abfrage"
            prefix, fixture_params = self.fixtures
            sql = "WITH " + prefix + ", " + sql[5:]
            params = fixture_params + params
        start = time.perf_counter()
        with self.connection.cursor(row_factory=dict_row) as cur:
            executed = cur.mogrify(sql, params)
            cur.execute(sql, params)
            rows = cur.fetchmany(limit)
        result = {"sql": executed, "zeilen": len(rows), "daten": rows}
        self.evidence.append({**result, "laufzeit_sek": time.perf_counter() - start})
        return result


def fixture_ctes(extra_logs=()):
    rows = []

    def add(ds, ts, level, template, node=None, pid=None, request=None, vm=None, alert=None):
        rows.append((len(rows) + 1, ds, ts, level, "kernel" if ds == "BGL" else "compute",
                     node, pid, request, vm, alert, template))

    for ts in ["2005-06-03 00:00Z", "2005-06-03 01:00Z", "2005-06-05 00:00Z", "2005-06-05 01:00Z"]:
        add("BGL", ts, "FATAL", "BGL-A", node="A", alert="alert")
    for i, ts in enumerate(["2005-06-03 00:00Z", "2005-06-04 00:00Z", "2005-06-05 00:00Z"]):
        add("BGL", ts, "FATAL", "BGL-B", node=f"B{i}", alert="alert")
    for node in [None, "NULL", "-", ""]:
        add("BGL", "2005-06-04 12:00Z", "ERROR", "BGL-UNKNOWN", node=node)
    add("BGL", "2005-06-07 00:00Z", "INFO", "BGL-INFO", node="A")
    add("BGL", "2005-06-04 00:00Z", "WARN", "BGL-WARN", node="A")
    for hour in [0, 2]:
        for template in ["OS-A", "OS-B", "OS-C"]:
            add("OpenStack", f"2017-05-14 {hour:02}:00Z", "ERROR", template,
                pid=42, request=f"req-{hour}")
    for hour in [1, 4]:
        add("OpenStack", f"2017-05-14 {hour:02}:00Z", "WARN", "OS-WARN",
            pid=50, vm=f"vm-{hour}")
    add("OpenStack", "2017-05-14 03:00Z", "INFO", "OS-INFO", pid=50)
    for _ in range(2):
        add("OpenStack", "2017-05-14 05:00Z", "ERROR", "OS-MISSING")
    rows.extend(extra_logs)
    tables = [
        ("logs", ["id", "dataset", "ts", "level", "component", "node", "pid", "request_id", "instance_id", "alert", "template_id"],
         ["BIGINT", "VARCHAR", "TIMESTAMPTZ", "VARCHAR", "VARCHAR", "VARCHAR", "BIGINT", "VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"], rows),
        ("templates", ["dataset", "template_id", "template"], ["VARCHAR"] * 3,
         sorted({(r[1], r[-1], "Beispiel " + r[-1]) for r in rows})),
        ("ownership", ["dataset", "component", "team"], ["VARCHAR"] * 3,
         [("BGL", "kernel", "HPC Kernel"), ("OpenStack", "compute", "Cloud Compute")]),
    ]
    parts, params = [], []
    for name, columns, types, values in tables:
        row_sql = "(" + ", ".join("%s::" + t for t in types) + ")"
        parts.append(f"{name} AS (SELECT * FROM (VALUES " + ", ".join([row_sql] * len(values)) +
                     ") AS v(" + ", ".join(columns) + "))")
        params.extend(value for row in values for value in row)
    return ", ".join(parts), params
