# CLAUDE.md – Projektkontext „Making Sense of Logs“

## Wer und was

- Ich bin **Eren**, Informatik-Student (RWTH Aachen, Fokus ML/KI). Antworte auf **Deutsch**, erkläre verständlich,
  ich arbeite unter **Windows mit PowerShell** und VS Code.
- Projekt: **schubKI National AI Hackathon 2026, Challenge 04 von SereneDB: „Making Sense of Logs“**.
  48-h-Sprint am **17.–18. Oktober 2026**, online, Team aus **5 Personen**.
- Aufgabe der Challenge: Prototyp, der Log-Daten in nützliche Antworten für drei Rollen verwandelt.
  SereneDB findet Belege und berechnet Kennzahlen, ein KI-Agent erklärt und empfiehlt.
  Bewertet wird der Ablauf **Frage → Belege → Empfehlung**.
- **Leitprinzip: SQL rechnet, das LLM erklärt.** Das LLM erfindet keine Zahlen, jede Aussage ist auf eine Query
  oder konkrete Log-Zeilen rückführbar.

## Die drei Rollen (gleiche Daten, andere Flughöhe)

| Rolle | Frage | Ebene |
|---|---|---|
| Engineer | „Warum ist dieser Fehler passiert?“ | einzelnes Ereignis + Kontext (gleicher Request/VM bzw. Knoten davor) |
| Team Lead | „Was kommt in meinem Team immer wieder?“ | Muster (Templates) je Team, Trend |
| Manager | „Welches Team / Problem zuerst?“ | Muster × Auswirkung, Rangliste mit Score |

## Vorgaben aus der offiziellen SereneDB-Guidance

- Daten: **BGL + OpenStack** Rohdaten von Zenodo (Links im Brief), ca. **770 MB**.
- Selbst bauen: **Schema**, **Laden** (bevorzugt per SQL: `read_csv`, `read_json`, `read_ndjson`, `read_parquet`, `COPY`;
  ein Skript zur Vorbereitung ist ok), **Ownership-Tabelle** (fiktiv: dataset, component, team; im README dokumentieren).
- Alle SQL-Dateien und Skripte gehören ins Repo.
- KI-Nutzung ist **ausdrücklich erwünscht**. Docs-MCP verbinden:
  `claude mcp add --transport http serenedb-docs https://api.serenedb.com/mcp`
  (Tools: search_docs, read_section, docs_health). Die Doku ist auch in SQL durchsuchbar: `SELECT * FROM sdb_docs.search('…')`.
  **Bei SereneDB-Syntaxfragen immer zuerst den Docs-MCP nutzen**, nicht Postgres-Wissen annehmen.

## Die Daten

| | BGL | OpenStack |
|---|---|---|
| Was | Blue Gene/L Supercomputer, Hardware/Kernel | Nova (Cloud), API-Requests, VM-Lebenszyklus |
| Umfang | ca. 4,7 Mio. Zeilen | ca. 200.000 Zeilen (normal1, normal2, abnormal) |
| Format | `Label Unix-Zeit Datum Knoten Zeit Knoten Typ Komponente Level Nachricht` | `Datei Datum Zeit PID Level Komponente [req-… user project - - -] Nachricht` |
| Besonderheit | Label ≠ `-` = echte Störung (Alert-Kategorie, z. B. KERNDTLB) | `[instance: UUID]` in der Nachricht, Abnormal-Datei mit eingespielten VM-Fehlern |
| Kontext für Engineer | Knoten + Zeitfenster | `request_id`, `instance_id` |

## Architektur

```
Rohdaten (data/) → ingest/prepare.py (Parsing je Format + Drain3 → out/*.parquet)
→ ingest/load.sql (read_parquet → Tabellen logs, templates, ownership + Volltextindex)
→ tools/ (feste SQL-Queries als Python-Funktionen, geben Daten + ausgeführte SQL zurück)
→ agent/ (EIN LLM-Agent mit nativem Tool-Calling, System-Prompt je Rolle)
→ app.py (Streamlit: Rolle/Team wählen, Chat, Belege-Panel, Diagramme)
```

## Schema

- `logs(id, dataset, ts, level, level_raw, component, service, node, pid, request_id, instance_id, alert, message, template_id, source_file, parsed)`
- `templates(template_id, dataset, template, count, first_seen, last_seen, max_level, alerts, main_component, example_log_id)`
- `ownership(dataset, component, team)`
- `level` normalisiert auf DEBUG/INFO/WARN/ERROR/FATAL (BGL: SEVERE→ERROR, FAILURE→FATAL), Original in `level_raw`.
- `template_id` mit Präfix `BGL-0012` / `OS-0007`. `service`: BGL = Ereignistyp (RAS), OpenStack = nova-api/nova-compute/nova-scheduler.

## Tools (Person 2 und 3)

| Tool | Rolle | Liefert |
|---|---|---|
| `search_logs(query, dataset, level, team, von, bis)` | Engineer | Volltexttreffer |
| `get_context(log_id, fenster_sek)` | Engineer | OpenStack: gleicher Request/VM · BGL: gleicher Knoten im Zeitfenster |
| `top_patterns(team, dataset, von, bis, limit)` | Team Lead | häufigste Templates (ERROR/FATAL), mit Alerts |
| `pattern_trend(template_id or team, intervall)` | Lead/Manager | Zeitreihe |
| `priority_ranking(von, bis, group_by)` | Manager | Rangliste je Problem oder Team |

Prioritäts-Score (transparent, Faktoren in UI zeigen):
`Häufigkeit_norm × Schweregrad (FATAL 3, ERROR 2, WARN 1) × Reichweite_norm (Knoten bzw. VMs/Requests) × Trendfaktor (1 ± 0.5) × Alertfaktor (1 + Alert-Anteil, nur BGL)`.

## SereneDB – was wir wissen

- Docker: `docker compose up -d` (Image `serenedb/serenedb`, läuft als SereneDB 26.10.1, Port **7890** nur auf 127.0.0.1,
  Volume `serenedb-data`). Repo-Ordner ist im Container unter **`/data`** gemountet. Pfade in `read_parquet`/`read_csv` sind **Container-Pfade**.
- **Login**: `postgres` hat kein Passwort und ist laut Doku nur über Loopback **im** Container vertraut. Verbindungen aus Windows
  kommen über das Docker-Netz → `password authentication failed`. Team-Entscheidung: ohne Passwort, dafür **einmalig** nach dem ersten Start:
  `docker exec serenedb psql -h 127.0.0.1 -p 7890 -U postgres -c "SET hba = 'host all all 0.0.0.0/0 trust'"` (liegt im Volume).
- Verbindung: `psycopg.connect("host=localhost port=7890 dbname=postgres user=postgres")`.
- Keine verschachtelten Transaktionen, keine Named Cursors (`DECLARE CURSOR`). Für große Ergebnisse `cur.stream(...)`.
- Volltext (**getestet**, Index vollständig: Treffer = Template-Zählung bzw. `LIKE`-Zählung):
  ```sql
  CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS english AS split_text(case := 'lower') WITH (frequency, position, offset);
  CREATE INDEX logs_idx ON logs USING inverted(id, message english);   -- erst laden, dann indexieren
  VACUUM (REFRESH_TABLE) logs;
  -- nicht indexierte Spalten (ts, component …) lassen sich direkt aus logs_idx lesen (Lookup in die Tabelle)
  SELECT id, ts, component, message FROM logs_idx WHERE message @@ ts_phrase('data TLB error');
  ```
- Funktioniert auch: `DESCRIBE`, `read_csv(…, header = true)` (nötig bei reinen Text-Spalten), `GROUP BY ALL`.

## Meine Rolle: Person 1 – Daten & Laden

- Samstag: `prepare.py` auf echten Daten laufen lassen, `load.sql` zum Laufen bringen, Ownership-Tabelle fertig, Qualitätsbericht ans Team.
- Sonntag: Tools von Person 2/3 gegen bekannte Fälle testen, README-Abschnitt Daten/Ownership, Backup-Video.
- Andere: 2 Suche (Engineer-Tools, Index), 3 Analytics (Lead/Manager-Tools, Score), 4 Agent, 5 UI/Demo/Pitch.

## Stand (Sa., 17.10., 02:51)

- **Pipeline läuft komplett auf echten Daten**: `prepare.py` (~125 s, 0 % nicht erkannt) → `load.sql` (~10 s, wiederholbar) → SereneDB.
  Python-Umgebung: `.venv` im Repo (3.12.10) → `.venv\Scripts\python …` oder `.venv\Scripts\Activate.ps1`.
- Daten: `data/BGL/BGL.log`, `data/OpenStack/openstack_{abnormal,normal1,normal2}.log`;
  `data/OpenStack/anomaly_labels.txt` nennt die 4 VM-IDs mit eingespielten Fehlern (Grundwahrheit für Tests).
- **BGL**: 4.747.963 Zeilen, 399 Templates, 348.460 Alert-Zeilen (= Loghub-Angabe), 41 Alert-Kategorien.
  Gewichtet 90 % der Alert-Zeilen liegen im Haupt-Template ihrer Kategorie (z. B. KERNDTLB → BGL-0019 zu 100 %).
  **OpenStack**: 207.820 Zeilen, 71 Templates. Drain-Schwellen BGL 0.4, OpenStack 0.9 (sonst verschmelzen „VM Paused/Resumed“).
- Heute behoben: NUM-Maske nur für ganze Tokens (vorher `512M` → `<NUM>2M`), neue HEX-Regel für Registerwerte
  (muss **nach** PATH stehen, sonst zerschneidet sie UUIDs in Pfaden → 4.000+ Templates), BGL-Parser-Rückfall für 316 Zeilen
  mit verschobenen Feldern (306× „Kill job … timed out“ waren INFO statt FATAL), `ownership.csv` + 2 Komponenten.
  Die Loghub-Validierung (97 % auf 2.000 Zeilen) stammt noch von den alten Masken, Referenzdateien liegen nicht im Repo.
- **Erkenntnisse fürs Team**:
  - BGL: FATAL ≠ Störung. Nur 41 % der FATAL-Zeilen haben ein Alert-Label, aber alle Alert-Zeilen sind FATAL → Alertfaktor ist wichtig.
  - OpenStack: **alle 196** ERROR/FATAL-Zeilen stammen aus `oslo_service.periodic_task` (Cloud Compute) und
    `keystonemiddleware.auth_token` (Cloud API). Cloud Virtualization/Scheduling haben 0 → `top_patterns` für OpenStack mit WARN (3.118).
  - BGL-`ts` ist eigentlich Ortszeit (UTC−7), als UTC markiert. Innerhalb des Datensatzes konsistent.
- Bekannt: `drain3` baut unter **Python 3.13** nicht mit neuem setuptools. Lösung: `pip install "setuptools==69.*" wheel`
  und dann `pip install --no-build-isolation drain3`, oder Python 3.11/3.12.

## Nächste Schritte für mich

1. Qualitätsbericht ans Team (Zahlen und Erkenntnisse oben).
2. Optional: `anomaly_labels.txt` als Tabelle `known_anomalies` laden (4 VM-IDs) für Tests und Engineer-Demo.
3. Sonntag: Tools von Person 2/3 gegen bekannte Fälle testen (KERNDTLB → BGL-0019, die 4 Anomalie-VMs),
   README-Abschnitt Daten/Ownership, Backup-Video.

## Konventionen

- Python 3.11/3.12, Kommentare und Ausgaben auf Deutsch.
- Keine Daten (`data/`, `out/`) und keine `.env` committen.
- Commit-Messages kurz, Englisch oder Deutsch.
