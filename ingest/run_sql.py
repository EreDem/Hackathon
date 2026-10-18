"""Run a SQL file through the local container admin connection; stop on first error.

    python ingest/run_sql.py ingest/load.sql

Uses the same container-local login as the README. DB_DSN remains read-only.
"""
from pathlib import Path
import subprocess
import sys


def main(path: str) -> None:
    sql = Path(path).read_text(encoding="utf-8")
    subprocess.run(
        ["docker", "exec", "-i", "serenedb", "psql", "-h", "127.0.0.1",
         "-p", "7890", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-f", "-"],
        input=sql, text=True, check=True,
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ingest/load.sql")
