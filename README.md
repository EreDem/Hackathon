# Making Sense of Logs – schubKI National AI Hackathon 2026 (Challenge 04, SereneDB)

Prototyp, der Log-Daten (BGL + OpenStack) in Antworten für drei Rollen verwandelt:
**Engineer** (Ursache eines Fehlers), **Team Lead** (wiederkehrende Probleme im Team), **Manager** (Priorisierung).
Ablauf: **Frage → Belege (SereneDB) → Empfehlung (KI-Agent)**. Leitprinzip: SQL rechnet, das LLM erklärt.

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
| 2 | Suche (Engineer) | |
| 3 | Analytics (Team Lead & Manager) | |
| 4 | Agent | |
| 5 | UI, Demo & Pitch | |
