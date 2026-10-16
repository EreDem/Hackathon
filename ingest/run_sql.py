"""
run_sql.py – führt eine .sql-Datei Statement für Statement gegen SereneDB aus
und zeigt Ergebnisse an. Praktisch, wenn psql nicht installiert ist.

    python ingest/run_sql.py ingest/load.sql
"""
import sys
import time

import psycopg

DSN = "host=localhost port=7890 dbname=postgres user=postgres"


def statements(sql: str):
    # Kommentare entfernen, an ';' trennen (reicht für unsere einfachen Skripte)
    lines = [l.split("--", 1)[0] for l in sql.splitlines()]
    for stmt in "\n".join(lines).split(";"):
        if stmt.strip():
            yield stmt.strip()


def main(path: str) -> None:
    sql = open(path, encoding="utf-8").read()
    with psycopg.connect(DSN, autocommit=True) as conn:
        for stmt in statements(sql):
            first = stmt.splitlines()[0][:80]
            t0 = time.time()
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                    print(f"✓ {first}  ({time.time() - t0:.1f} s)")
                    if cur.description:
                        cols = [d.name for d in cur.description]
                        print("   " + " | ".join(cols))
                        for row in cur.fetchmany(15):
                            print("   " + " | ".join(str(v)[:60] for v in row))
            except Exception as e:  # weiterlaufen, Fehler anzeigen
                print(f"✗ {first}\n   {type(e).__name__}: {e}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ingest/load.sql")
