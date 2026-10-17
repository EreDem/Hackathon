# AGENTS.md – Projektkontext „Making Sense of Logs“

## Wer und was

- Antworte auf **Deutsch**, erkläre verständlich,
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
  `codex mcp add serenedb-docs --url https://api.serenedb.com/mcp`
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
- Verbindung: `psycopg.connect("host=127.0.0.1 port=7890 dbname=postgres user=postgres", cursor_factory=psycopg.ClientCursor)`.
  **Nicht `localhost`** und **immer `ClientCursor`**, Gründe unter „Gemeinsame Regeln für alle Tools“.
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
  - OpenStack: **alle 196** ERROR/FATAL-Zeilen (= 12 Ereignisse, siehe „Gemeinsame Regeln“) stammen aus `oslo_service.periodic_task` (Cloud Compute) und
    `keystonemiddleware.auth_token` (Cloud API). Cloud Virtualization/Scheduling haben 0 → `top_patterns` für OpenStack mit WARN (3.118).
  - BGL-`ts` ist eigentlich Ortszeit (UTC−7), als UTC markiert. Innerhalb des Datensatzes konsistent.
- Bekannt: `drain3` baut unter **Python 3.13** nicht mit neuem setuptools. Lösung: `pip install "setuptools==69.*" wheel`
  und dann `pip install --no-build-isolation drain3`, oder Python 3.11/3.12.

## Schnellstart für alle (ca. 15 Minuten)

1. `git pull`, dann in PowerShell: `python -m venv .venv` → `.venv\Scripts\Activate.ps1` → `pip install -r requirements.txt`.
2. `.env.example` nach `.env` kopieren (Person 4 trägt `OPENAI_API_KEY` ein).
3. `docker compose up -d`, danach **einmalig** die trust-Regel (siehe SereneDB → Login).
   Wer SereneDB vorher von Hand gestartet hat: zuerst `docker rm -f serenedb`.
4. **Parquet-Dateien erzeugen.** Sie liegen nicht im Repo (`out/` steht in `.gitignore`), jeder erzeugt sie selbst:
   - Zenodo-Daten (Links im Brief) so entpacken, dass es diese Dateien gibt: `data/BGL/BGL.log` (743 MB) sowie
     `data/OpenStack/openstack_abnormal.log`, `openstack_normal1.log`, `openstack_normal2.log` und `anomaly_labels.txt`.
   - Aus dem Repo-Hauptordner mit aktivierter `.venv`:
     `python ingest/prepare.py data/BGL/BGL.log "data/OpenStack/openstack_*.log"` (ca. 2 Minuten).
     Die Anführungszeichen sind nötig, das Skript löst den `*` selbst auf. Unter Python 3.13 vorher den drain3-Hinweis unter „Stand“ beachten.
   - Ergebnis in `out/`: `logs.parquet` (ca. 62 MB, 4.955.783 Zeilen) und `templates.parquet` (470 Templates), dazu
     `templates.csv` und `components.csv` zum Anschauen. Der Bericht am Ende muss zeigen: BGL 4.747.963 Einträge und 399 Templates,
     OpenStack 207.820 und 71, jeweils `nicht erkannt: 0 (0.00%)`.
   - Optionaler Testlauf vorab: `python ingest/prepare.py data/BGL/BGL.log --limit 200000` (ca. 10 s). Er überschreibt `out/`,
     danach also unbedingt den vollen Lauf machen.
5. `python ingest/run_sql.py ingest/load.sql` (~10 s). Erwartet: `OpenStack | 207820 | 71` und `BGL | 4747963 | 399`,
   „Komponenten ohne Team“ ist leer, die Volltextsuche zeigt 10× `data TLB error interrupt`.

## Gemeinsame Regeln für alle Tools (Person 2–5)

- **DSN mit `127.0.0.1`, nicht `localhost`.** Der Port ist nur an IPv4 gebunden, `localhost` versucht zuerst IPv6 und hängt 20–30 s.
- **Immer `cursor_factory=psycopg.ClientCursor`.** SereneDBs server-seitiges Parameter-Binding bricht bei manchen Kombinationen ab
  (`Invalid unicode (byte sequence mismatch)` bzw. `unexpected field count in "D" message`). Mit `ClientCursor` laufen alle Abfragen unten.
- Listen als Parameter: `level = ANY(%s)` mit Python-Liste. Ein `%` in `LIKE` als `%%` schreiben.
- **Rückgabe jedes Tools:** `{"sql": <tatsächlich ausgeführte SQL>, "zeilen": n, "daten": [dict, …]}`. Belege-Panel und Agent nutzen genau das.
  Für das LLM mit `json.dumps(ergebnis, default=str)` serialisieren (Zeitstempel).
- Gemeinsamer Helfer `tools/db.py` (getestet). Person 2 legt ihn als Erstes an, alle importieren ihn:
  ```python
  import os
  import psycopg
  from psycopg.rows import dict_row

  DSN = os.getenv("DB_DSN", "host=127.0.0.1 port=7890 dbname=postgres user=postgres")

  def query(sql: str, params: list | None = None, limit: int = 200) -> dict:
      """Führt eine Abfrage aus und gibt Daten + die tatsächlich ausgeführte SQL zurück (für das Belege-Panel)."""
      with psycopg.connect(DSN, autocommit=True, cursor_factory=psycopg.ClientCursor) as conn:
          with conn.cursor(row_factory=dict_row) as cur:
              ausgefuehrt = cur.mogrify(sql, params)
              cur.execute(sql, params)
              rows = cur.fetchmany(limit)
      return {"sql": ausgefuehrt, "zeilen": len(rows), "daten": rows}
  ```
- **Die Daten sind historisch, nie `now()` verwenden.** BGL: 03.06.2005 – 04.01.2006. OpenStack: 14.05.2017 19:39 – 17.05.2017 12:02
  in drei Blöcken: 14.05. 19:39–21:56 (abnormal), 16.05. 00:00–06:25 (normal1), 16.05. 15:15 – 17.05. 12:02 (normal2).
  „Letzte 7 Tage“ heißt relativ zu `MAX(ts)` des Datensatzes. Trend-Intervall: BGL Tag/Woche, OpenStack Stunde.
- BGL-`node` enthält auch die Texte `'NULL'` (89.296 Zeilen) und `'-'` (324). Für die Reichweite deshalb
  `COUNT(DISTINCT NULLIF(NULLIF(node, 'NULL'), '-'))`. OpenStack-Reichweite: `COUNT(DISTINCT instance_id)` (2.069 VMs) bzw. `request_id`.
- **OpenStack-Tracebacks sind mehrzeilig:** Jede Zeile eines Python-Tracebacks ist ein eigener Log-Eintrag mit eigenem Template.
  Die 196 ERROR/FATAL-Zeilen sind nur **12 Ereignisse**. Ereignisse zählt man mit `COUNT(DISTINCT (pid, ts))`, nicht mit `COUNT(*)`.
  Beispiel: `Error during ComputeManager._run_image_cache_manager_pass` (OS-0045) tritt 8× auf, jedes Mal mit 24 Zeilen (OS-0045 … OS-0068).
  Die eigentliche Ursache steht mittendrin: OS-0063 `InvalidDiskInfo: Disk info file is invalid: qemu-img failed to execute`.
  Bei BGL tritt das nicht auf (jede FATAL-Zeile hat ein eigenes `(node, ts)`).

## Aufgaben je Person

### Person 1 – Eren: Daten & Laden (Samstag erledigt)

- Fertig: `prepare.py`, `load.sql`, Ownership, SereneDB-Setup, die getesteten SQL-Bausteine in dieser Datei.
- Offen: optional die Tabelle `known_anomalies` (4 VM-IDs) und eine Spalte `event_id` in `prepare.py`, die mehrzeilige
  OpenStack-Tracebacks zu einem Ereignis zusammenfasst. Sonntag: Tools von 2/3 gegen die bekannten Fälle testen,
  README-Abschnitt Daten/Ownership, Backup-Video.

### Person 2 – Suche (Engineer) → `tools/db.py`, `tools/engineer.py`

1. `search_logs(query, dataset=None, level=None, team=None, von=None, bis=None, limit=50)`. WHERE-Teile nur für gesetzte Filter anhängen:
   ```sql
   SELECT i.id, i.ts, i.dataset, i.level, i.component, o.team, i.template_id, i.node, i.instance_id, i.request_id, i.message
   FROM logs_idx i JOIN ownership o ON o.dataset = i.dataset AND o.component = i.component
   WHERE i.message @@ ts_phrase(%s) AND i.level = ANY(%s) AND o.team = %s AND i.ts BETWEEN %s AND %s
   ORDER BY i.ts LIMIT 50
   ```
   Phrase: `ts_phrase('a b')`, alle Wörter: `ts_all(['a', 'b'])`, irgendein Wort: `ts_any(['a', 'b'])`. Groß-/Kleinschreibung ist egal.
2. `get_context(log_id, fenster_sek=600)`:
   - OpenStack: alle Zeilen derselben VM (`WHERE instance_id = %s ORDER BY ts`, typisch 25 Zeilen) und desselben Requests (`request_id`).
   - BGL: Derselbe Knoten ist fast immer leer (KERNDTLB-Alert id 17742: keine weitere Zeile in 24 h). Besser die **Midplane**
     (erste zwei Teile von `node`, z. B. `R20-M0`):
     ```sql
     SELECT l.id, l.ts, l.node, l.level, l.template_id, l.alert, l.message
     FROM logs l JOIN logs s ON s.id = %s
     WHERE l.dataset = 'BGL'
       AND l.node LIKE split_part(s.node, '-', 1) || '-' || split_part(s.node, '-', 2) || '%%'
       AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'
     ORDER BY l.ts LIMIT 100
     ```
     Zusätzlich hilfreich: Wie oft trat dasselbe Template im Fenster auf (Ausbruch oder Einzelfall), und auf wie vielen Knoten?
3. **Die OpenStack-Anomalien sind Verzögerungen, keine Fehlermeldungen** (alle Zeilen INFO). Deshalb ein drittes Tool `vm_dauer(instance_id)`,
   das die Spawn-Dauer mit allen VMs vergleicht:
   ```sql
   SELECT instance_id, CAST(regexp_extract(message, 'Took ([0-9.]+) seconds to spawn', 1) AS DOUBLE) AS sek
   FROM logs WHERE message LIKE '%%seconds to spawn%%'
   ```
   Median 19,7 s, Maximum normaler VMs 26,7 s. Die 4 Anomalie-VMs liegen bei 29,5–50,7 s, also auf Platz 1–4 von 2.066.

### Person 3 – Analytics (Team Lead & Manager) → `tools/analytics.py`

1. `top_patterns(team, dataset=None, von=None, bis=None, limit=10)` (getestet, 0,07 s):
   ```sql
   SELECT l.template_id, ANY_VALUE(t.template) AS template, COUNT(*) AS n, COUNT(l.alert) AS alerts,
          COUNT(DISTINCT NULLIF(NULLIF(l.node, 'NULL'), '-')) AS knoten, COUNT(DISTINCT l.instance_id) AS vms,
          MIN(l.ts) AS erstmals, MAX(l.ts) AS zuletzt
   FROM logs l
   JOIN ownership o ON o.dataset = l.dataset AND o.component = l.component
   JOIN templates t ON t.template_id = l.template_id
   WHERE o.team = %s AND l.level = ANY(%s)
   GROUP BY l.template_id ORDER BY n DESC LIMIT 10
   ```
   Level bei BGL `['ERROR', 'FATAL']`, **bei OpenStack mit `'WARN'`**, sonst sind Cloud Virtualization und Cloud Scheduling leer.
   Bei OpenStack zusätzlich `COUNT(DISTINCT (l.pid, l.ts)) AS ereignisse` ausgeben, da ein Traceback sonst als 24 Fehlertypen zählt.
2. `pattern_trend(template_id=None, team=None, intervall='1 day')`: `time_bucket(%s::INTERVAL, ts)` oder `date_trunc('day', ts)` (beide getestet).
3. `priority_ranking(von, bis, group_by='template' | 'team')`: Score-Formel oben. **Jeden Faktor als eigene Spalte zurückgeben**, das UI zeigt sie.
   Möglichst in SQL rechnen: Häufigkeit_norm und Reichweite_norm = Wert / `MAX(…) OVER ()`, Trendfaktor = zweite Hälfte des Zeitraums
   gegen die erste, begrenzt auf 0,5–1,5, Alertfaktor = `1 + COUNT(alert) / COUNT(*)` (nur BGL).
4. Plausibilitätscheck: Viele Zeilen bei kleiner Reichweite dürfen nicht automatisch oben landen (siehe Bekannte Fälle, BGL-0019).

### Person 4 – Agent → `agent/agent.py`

1. Entscheidung von Kardo (17.10.): OpenAI statt Anthropic. Das offizielle
   `openai`-Python-SDK und die Responses API verwenden. Kein Claude-Modellname
   und keine Anthropic-Tool-Runner-Parameter in OpenAI-Aufrufen.
2. Abhaengigkeiten: `requirements-agent.txt`. API-Key aus `OPENAI_API_KEY` in
   der lokalen `.env`; Modell ueber `OPENAI_MODEL` nach Pruefung des Zugangs.
   Keine Schluessel ausgeben oder committen. Die Einrichtung allein ruft keine API auf.
3. Der Agent waehlt die Werkzeuge von Person 2/3 selbst aus. Rueckgaben und
   tatsaechlich ausgefuehrte SQL pro Anfrage separat als Belege sammeln.
   Keine global geteilte Belegliste. Fehlende Tools deutlich melden;
   Testdaten niemals als echte Datenbankergebnisse praesentieren.
4. Drei Rollen-Prompts (Engineer / Team Lead / Manager). Nur Zahlen aus
   Tool-Ergebnissen nennen, Log-/Template-IDs zitieren und Beobachtungen,
   Hypothesen und naechste Schritte trennen. Datenumfang, Zeitfilter und
   abgeschnittene Ergebnisse offenlegen; historische Zeitraeume verwenden.
5. Schnittstelle zu Person 5 beibehalten:
   `antworte(rolle: str, team: str | None, frage: str, verlauf: list)`
   liefert `{"text": str, "belege": list}`.
6. Aktueller lokaler Stand: Agent-Grundgeruest unter Python 3.13 implementiert,
   lokale Tests und kleiner OpenAI-Verbindungstest erfolgreich. Alle sechs DB-Tools
   aus dem Team-Update sind angeschlossen. Einstieg und Schnittstellen: `agent/README.md`. Testmodell:
   `gpt-6.1-sol`. Erens bekannte Faelle sind durch echte SQL-Abfragen
   bestaetigt; 40 Tests bestehen. UI-Anbindung mit Omar steht noch aus. Lokales Testbudget: 5 USD; Kostenprotokoll
   `.agent-usage.sqlite3` nicht loeschen.

### Person 5 – UI, Demo & Pitch → `app.py`

1. Sofort startbar ohne Agent: ein Streamlit-Gerüst, das `tools/db.py` mit den SQL-Bausteinen oben direkt aufruft.
   Den Agent später über `antworte(...)` einhängen. Start: `streamlit run app.py`.
2. Layout: Seitenleiste mit Rolle und Team (`SELECT DISTINCT team FROM ownership ORDER BY 1`, 9 Teams), in der Mitte der Chat
   (`st.chat_input`, `st.chat_message`), rechts das Belege-Panel: je Beleg `st.code(beleg["sql"], language="sql")` und `st.dataframe(beleg["daten"])`.
   Diagramme mit Plotly: Trend als Linie (`pattern_trend`), Ranking als Balken mit den Score-Faktoren.
3. Demo-Drehbuch: je Rolle ein Fall aus „Bekannte Fälle“. Pitch-Zahlen: 4,95 Mio. Zeilen, Laden in ~10 s, 0 % nicht erkannte Zeilen,
   90 % der Alert-Zeilen im Haupt-Template ihrer Kategorie, alle 4 eingespielten VM-Anomalien per SQL gefunden.

## Bekannte Fälle (Testfälle für alle, Demo-Material)

| Rolle | Frage | Erwartete Belege |
|---|---|---|
| Engineer | „Warum ist VM `544fd51c-4edc-4780-baae-ba1d80a0acfc` auffällig?“ | 25 Zeilen, **alle INFO**. Spawn 41,8 s statt Median 19,7 s (Platz 2 von 2.066). Request `req-d6143bd4-9784-4e95-a0c8-83fba00530b6` = 12 Zeilen von nova-api bis nova-compute |
| Engineer | „Was steckt hinter `data TLB error interrupt`?“ | 152.734 Treffer = Template BGL-0019, zu 100 % Alert KERNDTLB |
| Team Lead (HPC Kernel) | „Was kommt bei uns immer wieder?“ | BGL-0019 data TLB error interrupt (152.734) · BGL-0119 data storage interrupt (63.491, 22.529 Knoten) · BGL-0020 instruction address (47.563) |
| Team Lead (Cloud Compute) | „Was kommt bei uns immer wieder?“ | Alle 192 ERROR-Zeilen sind **ein** Fehler mit 8 Vorkommen: `Error during ComputeManager._run_image_cache_manager_pass`, Ursache OS-0063 `InvalidDiskInfo … qemu-img failed to execute`. Keine Antwort mit „24 Fehlertypen“ |
| Manager | „Welches Problem zuerst?“ | BGL-0019 ist das häufigste Muster, aber **99,6 % kommen von einem Knoten** (`R30-M0-N9-C:J16-U01`, 152.182 Zeilen am 11.06.2005 in gut 6 h). BGL-0119 trifft 22.529 Knoten und sollte im Score deshalb vor BGL-0019 landen |
| alle | Die 4 VM-IDs aus `data/OpenStack/anomaly_labels.txt` | entsprechen Platz 1–4 nach Spawn-Dauer |

## Konventionen

- Python 3.11/3.12, Kommentare und Ausgaben auf Deutsch.
- Keine Daten (`data/`, `out/`) und keine `.env` committen.
- Commit-Messages kurz, Englisch oder Deutsch.
