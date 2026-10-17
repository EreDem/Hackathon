# Making Sense of Logs – schubKI National AI Hackathon 2026 (Challenge 04, SereneDB)

Prototyp, der Log-Daten (BGL + OpenStack) in Antworten für drei Rollen verwandelt:
**Engineer** (Ursache eines Fehlers), **Team Lead** (wiederkehrende Probleme im Team), **Manager** (Priorisierung).
Ablauf: **Frage → Belege (SereneDB) → Empfehlung (KI-Agent)**. Leitprinzip: SQL rechnet, das LLM erklärt.

## Agent-Entwicklung mit OpenAI (Kardo, Person 4)

Das Agent-Grundgeruest verwendet das offizielle OpenAI-Python-SDK und die Responses API.
Die Schnittstelle zu Omar bleibt `antworte(rolle, team, frage, verlauf)` mit
`{"text": str, "belege": list}`; zusaetzlich liefert `meta` Status und Verbrauch.
Die drei Rollen und alle sechs DB-Werkzeuge von Person 2/3 sind angeschlossen.
Fuer echte Analysen muss die lokale SereneDB laufen und mit beiden Datensaetzen geladen sein.
Start, Tests und Schnittstellen: [agent/README.md](agent/README.md).

Fuer die Agent-Entwicklung unter Windows mit vorhandenem Python 3.13:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-agent.txt
# Nur wenn .env noch nicht existiert:
Copy-Item .env.example .env
```

In `.env` den eigenen `OPENAI_API_KEY` lokal eintragen. Fuer die ersten Tests ist
`OPENAI_MODEL=gpt-6.1-sol` eingestellt. Schluessel nie ins Repository
oder in Chatnachrichten kopieren. Die Installation allein macht keine API-Aufrufe.
Diese kleine Installation umfasst nur Agent/DB-Pakete. Fuer Datenimport und UI
gelten weiterhin die vollstaendigen Abhaengigkeiten unten; besonders den
Drain3-Hinweis fuer Python 3.13 in `requirements.txt` beachten.

## Setup

```powershell
# 1. Abhängigkeiten (Python 3.11/3.12 empfohlen) in einer virtuellen Umgebung
python -m venv .venv
.venv\Scripts\Activate.ps1            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. SereneDB starten (mountet diesen Ordner nach /data, Port nur lokal auf 127.0.0.1)
docker compose up -d

# 2b. EINMALIG: Login ohne Passwort erlauben. postgres ist ab Werk nur über Loopback IM Container
#     vertraut; Verbindungen von Windows/macOS kommen über das Docker-Netz und scheitern sonst mit
#     "password authentication failed". Die Regel liegt im Volume serenedb-data und bleibt erhalten.
docker exec serenedb psql -h 127.0.0.1 -p 7890 -U postgres -c "SET hba = 'host all all 0.0.0.0/0 trust'"

# 3. Rohdaten von Zenodo entpacken: data/BGL/BGL.log, data/OpenStack/openstack_*.log

# 4. Vorbereiten: Parsing + Drain3-Templates -> out/*.parquet  (ca. 2 Minuten)
python ingest/prepare.py data/BGL/BGL.log "data/OpenStack/openstack_*.log"
#    schneller Testlauf: python ingest/prepare.py data/BGL/BGL.log --limit 200000

# 5. In SereneDB laden + Volltextindex  (ca. 10 Sekunden, beliebig oft wiederholbar)
python ingest/run_sql.py ingest/load.sql
```

Docs-MCP für Coding-Agenten: `claude mcp add --transport http serenedb-docs https://api.serenedb.com/mcp`

## Log Observatory UI (Person 5)

From the repository root, after installing requirements and loading the database:

```powershell
# Uses Python 3.11/3.12 and Streamlit 1.66+; theme loads from .streamlit/config.toml
Copy-Item .env.example .env    # first setup only; preserve an existing .env
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Open http://localhost:8501. Direct exploration needs only SereneDB; no model API
key is required. The application loads `.env` before importing database tools.
An unavailable database shows setup guidance and a reconnect button, not demo numbers.

- **Engineer:** full-text search, selectable log rows, an anchor-centered event timeline,
  message details, related request evidence and an OpenStack spawn-duration comparison.
- **Team Lead:** recurring-pattern bars and a selectable pattern trend, with log-line /
  approximate-event measures and visible observation gaps.
- **Manager:** priority bars, frequency-versus-observed-reach bubbles, score factors,
  unscored problems and a drill-down into supporting logs. Ranks stay within their
  dataset/reach comparison group; they are not a global impact ranking.
- **Evidence:** executed SQL, inputs, result tables, scope metadata, partial-result /
  truncation notices and downloadable JSON. Supporting queries remain accessible.

Select a role/dataset, choose a historical range/team, then **Apply scope**.
**Run prepared investigation** queries the active scope. BGL search starts with
`data TLB error interrupt`; the other roles load patterns or priorities. Changing
scope or role clears old results and conversations. Results live in session state;
zooming charts or changing display measures does not re-query the database.
Use **Reconnect / refresh data** after reloading the corpus.

Context deliberately broadens beyond the active dashboard scope: BGL uses the
anchor's midplane/time window, and OpenStack VM/request views cover their recorded
lifecycle. Spawn-duration comparisons use the entire OpenStack corpus. These
exceptions are disclosed beside the results. Log lines and `(pid, ts)` event
approximations are not confirmed incident counts. Scores are heuristics, not
measured customer impact. BGL timestamp conventions remain unchanged.

### Integrated OpenAI agent (Persons 4 and 5)

`agent/agent.py` now implements the existing interface, extended with optional UI settings:

```python
def antworte(rolle: str, team: str | None, frage: str, verlauf: list,
             *, language="de", scope=None) -> dict:
    # rolle: "Engineer", "Team Lead", or "Manager"
    # verlauf: [{"role": "user" | "assistant", "content": "..."}, ...]
    return {"text": "English answer grounded in tools", "belege": [
        {"tool": "search_logs", "inputs": {"query": "..."},
         "result": {"sql": "executed SQL", "zeilen": 1, "daten": []}}
    ]}
```

Person 4 returns raw evidence with `beleg_id`, `tool`, `parameter`, `sql`, `daten`
and completeness metadata. The UI retains those fields, supporting queries,
status and usage, and accepts the wrapped example above for compatibility.
The UI requests `language="en"` and supplies the historical `scope` explicitly.
The agent enforces non-null scope filters on applicable tool calls. Context and
spawn comparisons disclose their broader scope. Existing CLI calls stay German.

Configure `OPENAI_API_KEY` in the ignored local `.env`. The UI checks readiness
without an API request and disables chat until configured. Calls use the configured
`OPENAI_MODEL`, the existing four-request/six-tool-call limits and the local $5
usage ledger; do not delete `.agent-usage.sqlite3`. Failed or incomplete agent
statuses preserve evidence and show English diagnostics instead of a successful
answer. The UI displays evidence IDs, model-view truncation, token usage and
estimated cost. Direct exploration remains available without a model key.

### Five-minute demo

1. **0:00–0:40:** show scope and the query-evidence contract.
2. **0:40–2:00:** Engineer/BGL: run the prepared search, select a hit, inspect the
   event lens and SQL. Discuss observations separately from possible causes.
3. **2:00–3:10:** Team Lead/HPC Kernel: analyze patterns, change the selected
   pattern, and show the trend and its observation gaps.
4. **3:10–4:20:** Manager/BGL: compare frequency with reach, open score factors,
   then investigate supporting logs.
5. **4:20–5:00:** when the OpenAI key is configured, ask a prepared role-specific
   question and show its executed evidence; download the investigation JSON.

For the challenge submission, complete the agent-backed three-role demonstration;
direct exploration alone does not demonstrate agent tool selection.

### UI and tool checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
# Optional read-only real-corpus verification (requires running, loaded SereneDB):
.\.venv\Scripts\python.exe -m tests.check_analytics_real
# Full real-data UI check; --live explicitly enables three paid agent investigations:
.\.venv\Scripts\python.exe -m tests.check_ui_real
.\.venv\Scripts\python.exe -m tests.check_ui_real --live
```

UI tests use explicitly synthetic fixtures from `tests/ui_fixtures.py`; these
are never imported by the production app. They cover role/scope changes,
drill-downs, unavailable services, chart gaps, comparison groups, and query reuse.
Engineer regression tests cover full search totals, evidence retention, bounded
context and partial failures. New SQL must still be verified against the provided
SereneDB instance before the final demo.

### Local integration acceptance, 17 October 2026

- Integrated main commit `88df103` (Person 4's OpenAI agent) on `feat/ui`.
- Full official public corpus loaded: 4,747,963 BGL + 207,820 OpenStack rows;
  399 + 71 templates, zero unparsed rows and complete ownership mapping.
- All 69 regression tests pass with the real database fixtures enabled.
  The six-tool real-corpus check and full analytics acceptance also pass.
- Three English UI investigations completed with status `ok`, executed query
  evidence and role-specific answers. Combined conservative API estimate: $0.18583
  for this run. Future investigations incur their own usage.
- Local evidence is saved in ignored `out/agent-validation.json`,
  `out/analytics-validation.json` and `out/ui-validation.json`.
- This checkout retains password authentication. The approved `log_observatory`
  login has only SELECT on the three challenge tables plus schema usage; its
  connection string and the model key live in ignored `.env`. No broad trust
  rule was applied. `.env.example` contains no key.

For a reload with this read-only app configuration, use the container's local
administrative connection rather than the app login:

```powershell
docker exec serenedb psql -h 127.0.0.1 -p 7890 -U postgres -v ON_ERROR_STOP=1 -f /data/ingest/load.sql
# load.sql recreates tables, so restore this local app's SELECT grants afterward:
docker exec serenedb psql -h 127.0.0.1 -p 7890 -U postgres -v ON_ERROR_STOP=1 -c "GRANT SELECT ON logs TO log_observatory; GRANT SELECT ON templates TO log_observatory; GRANT SELECT ON ownership TO log_observatory;"
```

Dataset attribution: Zhu et al., *Loghub: A Large Collection of System Log
Datasets for AI-driven Log Analytics*, ISSRE 2023; BGL additionally Oliner &
Stearley, DSN 2007. Data came from the challenge's public Zenodo record 8196385.

## Role-specific visual exploration

All views work without model calls. Use the action buttons to run SQL; chart
controls reuse session results. Changing the applied scope clears old evidence.

- **Engineer:** search-hit timeline across all matches, node/time (BGL) or
  component/time (OpenStack) heatmap for the top 20 resources, and a keyboard
  selector that opens supporting log context. Missing timestamps and identifiers
  are counted separately; observation gaps remain blank.
- **Team Lead:** ranked patterns, Pareto concentration using the full matching
  log-line denominator, and up to four leading patterns in shared-axis trends
  and a pattern/time heatmap. Log lines and approximate events remain distinct.
- **Manager:** explainable priority ranking and frequency/reach bubbles, team
  comparison dots within one reach unit, and two equal calendar periods showing
  matching lines, matches per 1,000 scoped lines, and observed calendar buckets.
  Coverage is recorded-log coverage, not uptime or customer impact.

Every query, including supplementary chart queries, is available in the evidence
panel and JSON download. Chart queries expose truncation; unknown rates/reach
remain unknown. Search maps use the search result's effective matching mode.

Run chart and interaction checks with `python -m unittest tests.test_visuals tests.test_ui`.
Set `ANALYTICS_TEST_DB=1` to include real SereneDB checks, then run
`python -m tests.check_ui_real` for all three roles against the loaded corpus.
This command makes no model calls unless `--live` is explicitly supplied.

## Datenschema

| Tabelle | Inhalt |
|---|---|
| `logs` | id, dataset, ts, level, level_raw, component, service, node, pid, request_id, instance_id, alert, message, template_id, source_file, parsed |
| `templates` | template_id, dataset, template, count, first_seen, last_seen, max_level, alerts, main_component, example_log_id |
| `ownership` | dataset, component, team |

- `template_id`: Drain3-Template (Fehlertyp), Präfix `BGL-` bzw. `OS-`
- `alert`: BGL-Label (≠ `-` = im Datensatz als Störung markiert)
- `request_id` / `instance_id`: verknüpfen OpenStack-Zeilen desselben Requests bzw. derselben VM
- `node`: BGL-Knoten, Kontext über Knoten + Zeitfenster

## Ownership-Tabelle (fiktiv)

Zuordnung Komponente → Team in [`ingest/ownership.csv`](ingest/ownership.csv), damit Team Lead und Manager nach Team gruppieren können.

| Team | Komponenten |
|---|---|
| HPC Kernel | BGL: KERNEL |
| HPC Application Support | BGL: APP |
| HPC Control System | BGL: MMCS, BGLMASTER, CMCS |
| HPC Hardware & Interconnect | BGL: DISCOVERY, HARDWARE, LINKCARD, SERV_NET |
| HPC Operations | BGL: MONITOR |
| Cloud API | OpenStack: nova.osapi_compute.wsgi.server, nova.metadata.wsgi.server, nova.api.*, keystonemiddleware.auth_token |
| Cloud Compute | OpenStack: nova.compute.manager, nova.compute.claims, nova.compute.resource_tracker, oslo_service.periodic_task |
| Cloud Virtualization | OpenStack: nova.virt.libvirt.* |
| Cloud Scheduling | OpenStack: nova.scheduler.* |

## Struktur

```
ingest/   prepare.py, load.sql, run_sql.py, ownership.csv
tools/    SQL-Tools für den Agenten (search_logs, get_context, top_patterns, pattern_trend, priority_ranking)
agent/    Rollen-Prompts und Tool-Calling-Schleife
app.py    Streamlit-UI
data/     Rohdaten (nicht im Repo)
out/      Ausgabe von prepare.py (nicht im Repo)
```

## Team

| # | Bereich | Person |
|---|---|---|
| 1 | Daten & Laden | Eren |
| 2 | Suche (Engineer) | Kirdar|
| 3 | Analytics (Team Lead & Manager) | Ghazal |
| 4 | Agent | Kardo |
| 5 | UI, Demo & Pitch | Omar |
