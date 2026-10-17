"""Expliziter kostenpflichtiger Verbindungstest mit künstlichen Daten.

Aufruf: python -m agent.smoke --live
Keine SereneDB-Abfrage. Nicht für die Hackathon-Demo verwenden.
"""
import argparse
import json
import os

from dotenv import dotenv_values
from openai import OpenAI

from agent.agent import Agent, ROOT
from agent.budget import Budget, MODELL


def test_suche(**kwargs):
    return {"sql": "-- TESTDATEN: keine Datenbankabfrage ausgeführt",
            "zeilen": 1, "truncated": False,
            "daten": [{"id": 1, "dataset": "BGL", "message": "Künstlicher Verbindungstest, keine reale Störung."}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Echte OpenAI-Aufrufe ausdrücklich aktivieren.")
    if not parser.parse_args().live:
        parser.error("Dieser Test kostet API-Guthaben; zum Start --live angeben.")
    config = dotenv_values(ROOT / ".env")
    key = os.getenv("OPENAI_API_KEY") or config.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY fehlt.")
    budget = Budget(ROOT / ".agent-usage.sqlite3")
    with OpenAI(api_key=key, timeout=30, max_retries=0) as client:
        agent = Agent(client, {"search_logs": test_suche}, budget, model=MODELL, testdaten=True)
        result = agent.antworte("Engineer", None,
            "Dies ist nur ein Verbindungstest mit künstlichen Daten. Rufe search_logs einmal mit "
            "query='Verbindungstest' auf. Bestätige anschließend in einem Satz mit Beleg-ID, "
            "dass es Testdaten sind. Keine weiteren Untersuchungen.", [])
    print(result["text"])
    print(json.dumps(result["meta"], ensure_ascii=False, indent=2))
    print(f"Lokales Kostenprotokoll inkl. Reserven: {budget.total():.6f} USD")
    if result["meta"]["status"] != "ok" or not result["belege"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
