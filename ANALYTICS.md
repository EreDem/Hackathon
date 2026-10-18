# Bereich 3: Analytics – Übergabe

## Stand und Zuständigkeit

`tools/analytics.py` implementiert ausschließlich die drei Analytics-Funktionen
für Team Lead und Manager. Datenpipeline, Ownership, Engineer-Suche, Agent und UI
wurden nicht verändert. Die komplette SQL-Abnahme läuft auf SereneDB 26.10.1.

**Offene Integrationsabhängigkeit:** Bereich 2 muss `tools/db.py` liefern.
Analytics importiert beim Aufruf dessen `query(sql, params=None, limit=200)`.
Bis dahin sind die Funktionen importierbar, melden beim produktiven Aufruf aber
ausdrücklich den fehlenden Helfer. Es gibt keinen produktiven Ersatz-DB-Client.
Die Tests besitzen einen eigenen, ausschließlich dort verwendeten SereneDB-Transport.
Sobald der Helfer vorliegt, verwendet die Echtdaten-Abnahme ihn automatisch.

Erwarteter Helfer: `127.0.0.1`, `psycopg.ClientCursor`, `dict_row`, tatsächlich
ausgeführte SQL über `mogrify`, und Beachtung des übergebenen Fetch-Limits.
Die Anwendung lädt `.env`, **bevor** der Helfer erstmals importiert wird.

## Aufrufe und Ergebnisse

```python
from dotenv import load_dotenv
load_dotenv()
from tools.analytics import top_patterns, pattern_trend, priority_ranking

top_patterns("HPC Kernel", dataset="BGL", limit=10)
top_patterns("Cloud Compute", dataset="OpenStack", limit=100)
pattern_trend(template_id="BGL-0019", intervall="1 day")
pattern_trend(team="Cloud Compute", intervall="1 hour")
priority_ranking(group_by="template", dataset="BGL", limit=20)
priority_ranking(group_by="team", dataset="OpenStack")
```

Alle Funktionen akzeptieren `von` und `bis` als datetime oder ISO-Zeitstempel,
beide Grenzen inklusive. Ohne Offset gilt die gespeicherte UTC-Konvention.
Ohne Grenzen wird der volle verfügbare Zeitraum des ausgewählten Datensatzes
verwendet. Es gibt keine automatische Beschränkung auf die letzten Tage.
Ein gewünschter relativer Zeitraum muss am `MAX(ts)` des Datensatzes verankert
werden, niemals an der heutigen Uhrzeit. BGL und OpenStack stammen aus
unterschiedlichen Jahren. Die BGL-Zeitmarkierung wird nicht korrigiert.

`top_patterns(team=None)` wertet alle Teams aus, weiterhin je Team und Template.
`pattern_trend` verlangt Template und/oder Team; beide Filter werden geschnitten.
Die Template-ID bestimmt den Datensatz, ein widersprechender Datensatz ist ein
Eingabefehler. Zeitintervalle: `1 hour`, `1 day`, `1 week`; Standard `1 day`.
Top-Patterns und Ranking erlauben Limits von 1 bis 1000, Trends höchstens
10.000 Zeitpunkte. Leere Bereiche liefern leere Listen. Ein existierender
Datenbereich ohne Treffer eines Templates liefert dagegen null Fehler je
beobachtetem Zeitfenster. Datenbankfehler bleiben Fehler und werden nicht
als leere Ergebnisse versteckt.

Gemeinsame Rückgabe:

```python
{
    "sql": "tatsächlich ausgeführte SQL mit gebundenen Werten",
    "zeilen": 10,       # zurückgegebene Ergebnisgruppen, nicht Log-Häufigkeit!
    "daten": [...],
    "meta": {
        "filter": {...},
        "gruppen_gesamt": 210,
        "gekuerzt": True,
        "limit": 10,
        "bereich": {"sql": "...", "zeilen": 1, "daten": [...], "gekuerzt": False},
        # außerdem Level, Zählweise, Hinweise und gemessene Abfragezeiten
    },
}
```

Für das LLM: `json.dumps(ergebnis, default=str)`. `meta` mitgeben, damit Grenzen
und Kürzungen nicht verloren gehen. Für das Belege-Panel sowohl `sql`/`daten`
als auch `meta.bereich.sql`/`meta.bereich.daten` zugänglich machen.
Die Bereichsabfrage zählt **alle** Level vor dem Template-/Fehlerfilter,
gruppiert nach Datensatz und Team, und zeigt die effektiven Zeitgrenzen.
Haupt- und Bereichsabfrage sind getrennte Abfragen; während einer Auswertung
keinen Datenimport ausführen.

| Funktion | Wichtige Ergebnisfelder |
|---|---|
| `top_patterns` | `dataset`, `team`, `template_id`, `template`, `n`, `ereignisse`, `alerts`, `knoten`, `vms`, `requests`, `komponenten`, `example_log_id`, `erstmals`, `zuletzt`, `problem_template_ids` |
| `pattern_trend` | `dataset`, `zeit`, `beobachtete_logs`, `datenluecke`, `n`, `ereignisse`, `alerts` |
| `priority_ranking` | `dataset`, `gruppe`, `teams`, `template_ids`, Zähler/Reichweiten wie oben, `haeufigkeit`, alle Score-Faktoren, `max_haeufigkeit`, `max_reichweite`, `vergleichsgruppe`, `score`, `rang`, `status`, `nicht_bewertbar_gesamt`, `von`, `bis`, beide Zeitraumhälften, `trend_hinweis` |

Diagramme baut Bereich 5: Trendlinien je Datensatz trennen, `datenluecke=True`
als Unterbrechung darstellen. Nur in beobachteten Zeitfenstern bedeutet `n=0`
null passende Fehler. Bei Lücken sind `n`, `ereignisse` und `alerts` `None`.

## Zählung, Score und Grenzen

- BGL: ERROR/FATAL. OpenStack: WARN/ERROR/FATAL. INFO-Latenzanomalien gehören
  weiterhin zum Engineer-Tool `vm_dauer` und werden hier nicht neu implementiert.
- `n` zählt passende Logzeilen. `ereignisse` zählt bei BGL Einzelzeilen und bei
  OpenStack unterschiedliche `(pid, ts)` innerhalb des Filterbereichs.
  Fehlt PID oder Zeitstempel, bleibt jede Zeile ein eigenes Ereignis.
- Gleiche PID/Zeit kann unterschiedliche Vorgänge zusammenfassen; Ereignisse
  sind eine dokumentierte Näherung, keine gesicherten Incident-Zahlen. Insbesondere
  Summen von Template-Ereigniszahlen sind bei OpenStack nicht zulässig.
- Das erste ERROR/FATAL-Template nach Log-ID, ersatzweise das erste WARN-Template,
  repräsentiert ein OpenStack-Ereignis. Top-Patterns behält alle Templates und
  kennzeichnet ihre Zuordnung. Das Problemranking fasst sie zusammen; die
  zugehörigen Template-IDs bleiben erhalten. Die Zuordnung beweist keine Ursache.
- Das Teamranking zählt direkt über die gefilterten Ereignisse. Ein Ereignis,
  das Komponenten mehrerer Teams berührt, kann je Team vorkommen; Teamzahlen
  deshalb ebenfalls nicht als globale Incident-Zahl addieren.

```text
Score = haeufigkeit_norm * schweregrad * reichweite_norm
        * trendfaktor * alertfaktor
```

Häufigkeit: BGL-Zeilen bzw. OpenStack-Ereignisse. Schweregrad: maximaler Wert
FATAL=3, ERROR=2, WARN=1. Reichweite: gültige BGL-Knoten; bei OpenStack VMs,
falls vorhanden, sonst Requests. `NULL`, `"NULL"`, `"-"` und leere BGL-Knoten
zählen nicht. Reichweiten sind **beobachtete** Kennungen, kein Kunden-Impact;
teilweise fehlende Kennungen können die reale Reichweite unterschätzen.

Die beiden normierten Faktoren sind jeweils Wert/Maximum innerhalb derselben
Vergleichsgruppe **vor** Anwendung des Ausgabelimits. Vergleichsgruppe ist
Datensatz plus Reichweitenart. Ränge aus unterschiedlichen Vergleichsgruppen
sind nicht vergleichbar; die Ergebnisreihenfolge stellt keinen globalen Rang dar.
Unbewertbare Probleme folgen je Datensatz auf bewertbare; ihre Häufigkeit bleibt
sichtbar, `score` und `rang` sind `None`. `nicht_bewertbar_gesamt` zählt solche
Gruppen auch vor einer Kürzung.

Trendfaktor: `1 + clamp((zweite_haelfte - erste_haelfte) / ereignisse, -0.5, 0.5)`.
Der effektive Zeitraum wird zeitlich halbiert; die Mitte gehört zur zweiten
Hälfte. Keine Ausdehnung oder fehlende Zeitstempel ergeben Faktor 1 mit Hinweis.
Der Faktor vergleicht Kalenderzeiträume und korrigiert keine Beobachtungslücken.
Alertfaktor: BGL `1 + alerts/n`, sonst 1. Alle Faktoren stehen im Ergebnis.
Der Score ist eine nachvollziehbare Priorisierungsheuristik, keine gemessene
Ausfallzeit, kein finanzieller Schaden und keine bestätigte Ursache.

## Lokale Umgebung und Tests

Auf diesem Rechner wurden Python 3.12 in `.venv`, die vorhandenen Abhängigkeiten,
Docker Desktop und der bestehende Compose-Service eingerichtet. Die unveränderte
Pipeline hat beide vollständigen Datensätze verarbeitet und geladen. Rohdaten,
Parquet-Dateien und Nachweise liegen in den bereits ignorierten Verzeichnissen.

**Lokale Anmeldung:** Der neue Container verwendet die sichere Standard-
Passwortauthentifizierung. Das zufällige Passwort steht ausschließlich im
ignorierten `.env`-Wert `DB_DSN`. Die allgemeine Trust-Regel aus der README wurde
nicht gesetzt. Keine Zugangsdaten ins Repository übernehmen. Der Port bleibt
wie in Compose auf `127.0.0.1:7890` begrenzt.

Die Basis-Einrichtung auf weiteren Rechnern beschreibt die vorhandene README.
Der optionale Helfer `ingest/run_sql.py` verwendet den containerlokalen
Admin-Zugang aus der README und stoppt beim ersten SQL-Fehler. `DB_DSN` bleibt
der Lesezugang für App und Tools.
Der Analytics-Testtransport liest zuerst `ANALYTICS_TEST_DSN`, sonst `DB_DSN`
aus der Umgebung/`.env`. Ohne Angabe gilt die im Team vereinbarte lokale DSN.

Aus dem Repository-Hauptordner, PowerShell:

```powershell
# Schnittstellen-/Validierungstests ohne Datenbank
.\.venv\Scripts\python.exe -m unittest tests.test_analytics -v

# Zusätzlich SQL-Verhalten auf echten SereneDB-Abfragen prüfen.
# Fixtures sind CTEs; bestehende Tabellen werden nicht verändert.
$env:ANALYTICS_TEST_DB = '1'
.\.venv\Scripts\python.exe -m unittest tests.test_analytics -v

# Read-only-Abnahme gegen die vollständig geladenen Challenge-Daten
.\.venv\Scripts\python.exe -m tests.check_analytics_real
```

Die Echtdatenprüfung schreibt `out/analytics-validation.json` mit tatsächlich
ausgeführten Queries, Ergebnissen, Laufzeiten, Serverversion und Prüfbefunden.
Fehlgeschlagene Prüfungen ergeben Exit-Code 1. Prüfbefunde des ursprünglichen
Ladevorgangs liegen lokal in `out/analytics-load.log`.

### Gemessene Abnahme, 17.10.2026

- SereneDB 26.10.1; 4.747.963 BGL- und 207.820 OpenStack-Zeilen; 399 + 71 Templates;
  keine ungeparsten Zeilen, keine fehlende oder doppelte Ownership-Zuordnung.
- BGL-0019: 152.734 Fehlerzeilen. BGL-0119: 63.491 Fehlerzeilen auf 22.529 Knoten.
  Der Importbericht zählt zusätzlich zwei INFO-Zeilen, also 63.493 insgesamt.
- BGL-0119 liegt bei vollständiger Problem-Auswertung auf Rang 1 mit Score
  ca. 1,232753; BGL-0019 auf Rang 7 mit ca. 0,071212, jeweils `BGL:knoten`.
  Keine Template-ID wurde dafür im produktiven Code speziell behandelt.
- Cloud Compute: 192 ERROR-Zeilen, acht Ereignisse, ein Problem unter OS-0045;
  OS-0063 bleibt als zugehöriges Template verfügbar. WARN wird separat mitgezählt.
- Teamzahlen stimmen mit einer unabhängigen Kontrollabfrage überein.
  Bereichsstatistik umfasst alle 4.955.783 Zeilen.
- Erste gemessene Hauptabfragen: ca. 0,014 bis 0,512 s; zusätzliche
  Bereichsabfragen ca. 0,009 bis 0,060 s. Einzelmessungen auf diesem Rechner,
  keine garantierten Laufzeiten. Aktuelle Werte stehen im JSON-Nachweis.

**Noch offen:** Nach Lieferung von `tools/db.py` die Echtdatenprüfung erneut
ausführen. Erst `gemeinsamer_helfer_integriert=true` im Nachweis bestätigt diese
Integration. Agenten-Anbindung und Darstellung bleiben Aufgaben von Bereich 4/5.
