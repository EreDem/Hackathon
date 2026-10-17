"""Lokales Kostenprotokoll nur für Aufrufe dieses Agenten, kein Plattformlimit.

Vor jeder Anfrage wird eine konservative Schätzung reserviert; bei unbekanntem
Ausgang bleibt sie gebucht. Preise: OpenAI-Modellseiten, 17.10.2026.
Keine Prompts, Logdaten oder Schlüssel werden hier gespeichert.
"""
import math
from contextlib import contextmanager
from pathlib import Path
import sqlite3

MODELL = "gpt-6.1-sol"
# Konservative Standard-Tarife in USD/Million. Sol: normale Eingabe 2 USD,
# Cache-Schreiben 2,50 USD. Für Reservierung und Schätzung immer 2,50 ansetzen;
# dadurch unterschätzen wir Cache-Schreibkosten nicht. Cache-Rabatte ignorieren.
PREISE = {"gpt-5.4-mini-2026-03-17": (0.75, 4.50),
          "gpt-5.4-2026-03-05": (2.50, 15.00), MODELL: (2.50, 10.00)}


class BudgetLimit(Exception):
    pass


class Budget:
    def __init__(self, path: Path, limit_usd: float = 5.0):
        if not math.isfinite(limit_usd) or not 0 < limit_usd <= 5:
            raise ValueError("Lokales Budget muss zwischen 0 und 5 USD liegen.")
        self.path, self.limit = path, limit_usd
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, "
                       "model TEXT, usd REAL, input_tokens INTEGER, output_tokens INTEGER, "
                       "status TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def total(self) -> float:
        with self.connect() as db:
            return db.execute("SELECT COALESCE(SUM(usd),0) FROM usage").fetchone()[0]

    def reserve(self, model: str, input_bytes: int, output_tokens: int) -> int:
        if model not in PREISE:
            raise BudgetLimit("Für dieses Modell ist noch keine Kostenprüfung eingerichtet.")
        preis_in, preis_out = PREISE[model]
        # Ein UTF-8-Byte pro Token plus Reserve für Nachrichten-/Werkzeugrahmen.
        amount = ((input_bytes + 4096) * preis_in + output_tokens * preis_out) / 1_000_000
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT COALESCE(SUM(usd),0) FROM usage").fetchone()[0]
            if total + amount > self.limit:
                raise BudgetLimit("Das lokale Testbudget reicht für diese Anfrage nicht mehr aus.")
            cursor = db.execute("INSERT INTO usage(model,usd,status) VALUES (?,?,'reserviert')", (model, amount))
            return cursor.lastrowid

    def settle(self, entry: int, model: str, usage) -> float | None:
        if usage is None:
            return None  # Unbekannter Verbrauch bleibt vorsichtshalber reserviert.
        amount = (usage.input_tokens * PREISE[model][0] + usage.output_tokens * PREISE[model][1]) / 1_000_000
        with self.connect() as db:
            db.execute("UPDATE usage SET usd=?,input_tokens=?,output_tokens=?,status='gemessen' WHERE id=?",
                       (amount, usage.input_tokens, usage.output_tokens, entry))
        return amount
