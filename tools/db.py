import os
import psycopg
from psycopg.rows import dict_row

# Wichtig: 127.0.0.1 statt localhost (verhindert IPv6-Timeout unter Windows)
DSN = os.getenv("DB_DSN", "host=127.0.0.1 port=7890 dbname=postgres user=postgres")


def query(sql: str, params: list | None = None, limit: int = 200) -> dict:
    """Führt eine Abfrage aus und gibt Daten + die tatsächlich ausgeführte SQL zurück (für das Belege-Panel)."""
    with psycopg.connect(DSN, autocommit=True, cursor_factory=psycopg.ClientCursor) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            ausgefuehrt = cur.mogrify(sql, params) if params is not None else sql.strip()
            cur.execute(sql, params)
            rows = cur.fetchmany(limit) if cur.description else []
    return {
        "sql": ausgefuehrt.strip(),
        "zeilen": len(rows),
        "daten": rows,
    }