# Log Observatory: 4:30 demo

Englischer Sprechtext, deutsche Regie. Nur den Text unter **SPEAK** vorlesen.

## Zuerst vorbereiten

- Die Jury erwartet die echte Anwendung: Nur Folien vorzulesen reicht nicht. Im fertigen Video müssen alle drei Rollen sowie Werkzeugaufrufe, ausgeführte SQL und passende Ergebnisse sichtbar sein.
- Am einfachsten: Eine Person spricht. Eine zweite Person bedient die App oder schneidet vorher aufgenommene echte App-Clips ein. Mehrere Sprecher sind möglich, erhöhen aber den Übergabeaufwand.
- Folien und Sprechtext sind Englisch. Regieanweisungen sind Deutsch und werden nicht vorgelesen. Zielzeit: 4:30 Minuten, harte Grenze: 5:00. Im Video nur Folien 1-8 verwenden. Die PDF enthält zusätzlich zwei technische Referenzfolien.
- Die drei App-Clips zuerst vorbereiten und aufnehmen. Frage-Eingabe und tatsächliche Werkzeugaufrufe behalten. Leere Wartezeiten dürfen herausgeschnitten werden. Keine Ergebnisse, SQL oder erfolgreichen Antworten nachstellen. Zeigt die Antworten, die der Agent tatsächlich liefert.
- Die Aufnahme muss Folien und Browserwechsel erfassen. Falls euer Recorder nur ein Fenster erfasst, nehmt die Folien und die drei Browser-Clips getrennt auf und setzt sie in der angegebenen Reihenfolge zusammen. Ton und Sprechtempo beim Probelauf prüfen.

## Kopierfertige Fragen

### Engineer / OpenStack / All teams

What causes the recurring ComputeManager._run_image_cache_manager_pass failure, and how often does it recur? Inspect the traceback and distinguish observations from hypotheses. Give one next check with log IDs.

### Team Lead / BGL / HPC Kernel

Which problems recur for HPC Kernel across the recorded BGL period? Compare full aggregate frequency and observed node reach for data TLB error interrupt and data storage interrupt. Inspect the weekly trend of BGL-0019 and recommend a next investigation. Cite evidence and disclose truncation.

### Manager / BGL / All teams

Should we investigate data storage interrupt or data TLB error interrupt first? Use exact-phrase search aggregations for both and BGL priority_ranking. Compare full matching-line totals and observed node reach. Explain the score factors and recommend one next check. Do not invent economic impact or a score for a group outside the returned ranking.

## Zeitplan und Sprechtext

### 00:00 - 00:25 | Slide 1

**BILD (nicht vorlesen):** Folie 1 zeigen. Nach dem ersten Satz kurz pausieren.

**SPEAK:**

When a system fails, an engineer needs a diagnostic next step. A team lead needs recurring patterns. A manager needs a reason to act first. Log Observatory answers these questions using nearly five million real log lines and traceable database evidence.

### 00:25 - 00:50 | Slide 2

**BILD (nicht vorlesen):** Folie 2 zeigen und die Architektur von links nach rechts erklären. Danach zum vorbereiteten Engineer-Clip wechseln.

**SPEAK:**

We parse BGL and OpenStack logs and load our own schema into local SereneDB. We define a fictional ownership map. Fixed tools search and calculate. The agent chooses tools, explains the evidence and recommends a check. Each investigation retains its executed SQL.

### 00:50 - 01:45 | Slide 3

**BILD (nicht vorlesen):** 00:50-00:55 Folie 3. Dann echter Engineer-Clip: Rolle Engineer, Datensatz OpenStack, All teams. Frage absenden. Antwort und Belege search_logs/get_context zeigen. SQL und Log 4793594 bzw. 4793598 sichtbar machen. Am Ende kurz auf Folie 3 zurück. Ladezeit darf herausgeschnitten werden.

**SPEAK:**

The engineer asks why the image cache manager keeps failing. The agent searches the message and retrieves context. It finds eight matching failure messages. The traceback identifies InvalidDiskInfo. The qemu-img command cannot open an instance disk: the path does not exist. We can inspect the exact log IDs and SQL. Next, check the disk path and related deletion or storage activity. This explains the inspected failure. The other seven reports still need checking.

### 01:45 - 02:35 | Slide 4

**BILD (nicht vorlesen):** 01:45-01:50 Folie 4. Dann Team-Lead-Clip: BGL, HPC Kernel. Agent-Antwort und top_patterns/pattern_trend-Belege zeigen. Im direkten Bereich Run prepared investigation und Compare leading patterns können die Diagramme erzeugen. Aggregation und Zeitreihe sichtbar halten.

**SPEAK:**

The team lead compares patterns across HPC Kernel. SQL finds around one hundred fifty-three thousand TLB error lines. The trend shows a concentrated burst: more than one hundred fifty-two thousand in one weekly bucket. Storage interrupts occur less often, but reach more nodes. Investigate that wider pattern and check the localized burst. These are log counts and observed nodes, not confirmed incidents or affected customers.

### 02:35 - 03:25 | Slide 5

**BILD (nicht vorlesen):** 02:35-02:40 Folie 5. Dann Manager-Clip: BGL, All teams. Antwort mit beiden Volltextsuchen und priority_ranking zeigen. In Query evidence die Faktoren bzw. zugehörige Tabelle öffnen. Kurz SQL und Ergebniszeilen im selben Clip zeigen.

**SPEAK:**

The manager compares frequency and reach. TLB errors produce more lines, but appear on five hundred forty-one nodes. Storage interrupts appear on twenty-two thousand five hundred twenty-nine nodes. Our score combines frequency, severity, reach, trend and alerts. Storage interrupts rank first in this BGL comparison. We recommend investigating them first. The score supports prioritization. It does not measure financial damage.

### 03:25 - 03:45 | Slide 6

**BILD (nicht vorlesen):** Folie 6 zeigen. Optional 3-5 Sekunden echte Claude-/mcp-Ansicht mit sieben Tools einblenden, falls euer Kollege sie aufgenommen hat. Keine erfolgreiche Claude-Antwort behaupten, solange diese Aufnahme fehlt.

**SPEAK:**

The same functions also work through MCP. Assistants can discover seven read tools and three role prompts. Results have clear limits and SQL evidence. Claude connection instructions are included. The server makes no model calls.

### 03:45 - 04:10 | Slide 7

**BILD (nicht vorlesen):** Folie 7 zeigen. Pilot als Vorschlag formulieren. Keine gemessene Zeit- oder Geldersparnis behaupten.

**SPEAK:**

Next, we propose a supervised pilot with an operations team. We want to reduce manual log lookup and improve handovers. We would compare time to a supported next action, answer quality and investigation cost with the current workflow. Customer savings still need validation.

### 04:10 - 04:30 | Slide 8

**BILD (nicht vorlesen):** Folie 8 bis zum Ende zeigen. Spätestens bei 04:40 stoppen. Appendix-Folien 9 und 10 im Video auslassen, aber im einzureichenden PDF behalten.

**SPEAK:**

This prototype uses historical public logs and fictional ownership. Event grouping and scores remain heuristics. People verify recommendations before acting. A customer pilot needs access controls and sensitive-data handling. Each role gets a supported next step, with evidence ready to inspect.

## Aufnahme und Abgabe

### Lokal starten

PowerShell im Repo: docker compose up -d. Danach .\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1. Browser: http://127.0.0.1:8501. Bereits laufende Instanzen können einen anderen Port haben.

### Verbindung prüfen

Database connected und Agent connected müssen sichtbar sein. Bei Bedarf Reconnect / refresh data. Datensatz, Team und historische Daten wählen und immer Apply scope klicken. Nichts neu laden, wenn die vollständigen Daten schon vorhanden sind.

### Drei echte Clips aufnehmen

Je Rolle die kopierfertige Frage auf Seite 2 stellen. Nicht Ask the prepared question drücken: Die vorbereitete Standardfrage kann anders lauten. Nach einer Antwort das zu dieser Antwort gehörende Query evidence öffnen.

### Belege zeigen

Pro Rolle mindestens den Werkzeugnamen, eine tatsächlich ausgeführte SQL und passende Ergebniszeilen zeigen. Beim Engineer den Traceback, beim Team Lead Aggregation und Zeitreihe, beim Manager die beiden Suchaggregationen und die Score-Faktoren.

### Video schneiden und prüfen

Nach Zeitplan vorgehen. Bei 4:30 soll der Schluss fertig sein. Tatsächliche Laufzeit kontrollieren und unter 5 Minuten bleiben. Bei abweichenden Ergebnissen den Text anpassen, statt eine unpassende Zahl vorzulesen.

Nur die fertige Slides-PDF und den echten Video-Link ins Formular eintragen. Links ohne Anmeldung testen. Maximal fünf Minuten. Der Claude-Test ist eine getrennte, noch zu dokumentierende Abnahme.
