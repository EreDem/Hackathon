# Agent: aktueller Stand und Übergabe

Ein Agent mit drei Rollen (Engineer, Team Lead, Manager) verwendet OpenAI
Responses und wählt die verfügbaren Python-Werkzeuge selbst aus. Es gibt keine
freie SQL-Erzeugung. Die Datenbank-Werkzeuge sind Aufgabe von Kirdar/Ghazal.
Ein fehlendes Werkzeug wird nicht durch erfundene Daten ersetzt.
Die sechs Werkzeuge aus dem Team-Update sind inzwischen angeschlossen.

## Start unter Windows

Im Repository-Hauptordner mit eingerichteter `.venv` und lokalem API-Key:

```powershell
.\.venv\Scripts\python.exe -m agent --rolle Engineer --frage "Was steckt hinter data TLB error interrupt?"
.\.venv\Scripts\python.exe -m agent --rolle "Team Lead" --team "HPC Kernel" --frage "Welche Probleme kommen wieder?"
.\.venv\Scripts\python.exe -m agent --rolle Manager --frage "Welches Problem sollten wir zuerst untersuchen?"
```

Solange `tools.engineer` und `tools.analytics` fehlen, meldet der Agent das
ohne kostenpflichtige Modellanfrage. Installation der Agent-Pakete:
` .\.venv\Scripts\python.exe -m pip install -r requirements-agent.txt`.

## Übergabe an Omar

```python
from agent.agent import antworte

ergebnis = antworte("Engineer", None, "Was steckt hinter data TLB error interrupt?", [])
# ergebnis["text"]: Antwort bzw. verständliche Fehlermeldung
# ergebnis["belege"]: aktuelle Belege, getrennt vom Modelltext
# ergebnis["meta"]: Status, Modell, Aufrufzahlen, Tokenverbrauch, Kostenschätzung
```

`verlauf` ist eine Liste von `{"role": "user" | "assistant", "content": str}`.
Die letzten sechs Nachrichten werden verwendet, je höchstens 4000 Zeichen.
Bei Rollen-/Teamwechsel den Verlauf im UI leeren. Alte Chatantworten gelten
nicht als neue Belege. Status `ok` bedeutet abgeschlossener Ablauf mit gültigen
Belegverweisen, **keine automatische inhaltliche Wahrheitsprüfung**.

Im Belege-Panel `beleg_id`, `tool`, `sql`, `parameter` und `daten` zeigen.
`truncated=true` bedeutet Begrenzung durch das DB-Werkzeug;
`truncated=null` bedeutet unbekannte Vollständigkeit. `modell_gekuerzt` und
`modell_zeilen` zeigen die zusätzliche Begrenzung für das Modell. Die volle
Werkzeugrückgabe bleibt innerhalb der Größenprüfung im Belege-Panel erhalten.
`testdaten=true` immer sichtbar als Test markieren. Keine SQL aus dem Modelltext anzeigen.
Zusätzliche Abfragen ebenfalls anzeigen: `meta.bereich` bei Analytics und
`zusatz_belege` bei Engineer. Darin stehen jeweils eigene SQL und Daten.
Das Modell sieht kompakte Belege ohne lange SQL-Texte; im UI bleiben alle SQL erhalten.

## Übergabe an Kirdar und Ghazal

Die Anschlüsse in `agent/toolkit.py` erwarten folgende Funktionen:

| Modul | Funktion und Argumente |
|---|---|
| `tools.engineer` | `search_logs(query, dataset=None, level=None, team=None, von=None, bis=None, limit=20, modus='phrase')` |
| `tools.engineer` | `get_context(log_id, fenster_sek=600, limit=50)`; Log-ID, VM-UUID oder Request-ID |
| `tools.engineer` | `vm_dauer(instance_id=None, limit=5)` |
| `tools.analytics` | `top_patterns(team=None, dataset=None, von=None, bis=None, limit=10)` |
| `tools.analytics` | `pattern_trend(template_id=None, team=None, intervall='1 day', dataset=None, von=None, bis=None)` |
| `tools.analytics` | `priority_ranking(von=None, bis=None, group_by='template', dataset=None, team=None, limit=20)` |

Diese Funktionen sind vorhanden; der Agent verwendet die oben gezeigten Defaults.
Importierbare Funktionen werden angeboten;
ein Teilangebot ist möglich. Ein fehlender Teamfilter wird durch das im UI
gewählte Team ergänzt. Das ist fachliche Vorauswahl, keine Zugriffskontrolle.
Zeiträume werden als ISO-Strings oder `None` übergeben, Level als Liste oder
`None`. Intervalle: `1 hour`, `1 day`, `1 week`. SQL wird parametrisiert.
Verbindungsaufbau: maximal fünf Sekunden. Achtung: SereneDB 26.10.1 akzeptiert
`statement_timeout` laut eigener Dokumentation, erzwingt ihn aber noch nicht;
eine harte Laufzeitgrenze für bereits laufende Abfragen ist daher noch offen.

Pflicht-Rückgabe jedes Werkzeugs:

```python
{
    "sql": "tatsächlich ausgeführte SQL, inklusive eingesetzter Filter",
    "zeilen": 0,  # len(daten), NICHT die Anzahl aller passenden Logs
    "daten": [],  # Liste von Dictionaries; auch ein leeres echtes Ergebnis ist erlaubt
    "truncated": False,  # True bei abgeschnittenen DB-Ergebnissen; nur setzen, wenn bekannt
    # Empfohlen: "datenumfang", "zeitraum", "filter", "gesamt_treffer", "einschraenkungen"
}
```

Zählungen gehören in die Datenfelder der SQL-Aggregation. `truncated` ist für
alte Rückgaben optional; ohne Angabe macht der Agent keine Vollständigkeitszusage.
Ergebnisse dürfen höchstens 200 KB JSON umfassen. Das Modell bekommt höchstens
30 Datenzeilen je Tabelle (Zeitreihen bis 100) und ungefähr 16 KB pro Ergebnis. Bei größeren Mengen enger filtern
oder in SereneDB aggregieren. Lange ID-Listen werden für das Modell auf acht
Einträge gekürzt und als Ausschnitt markiert. Die vollständigen Daten bleiben
im UI-Beleg. Ausnahmen ergeben eine Fehlermeldung, keine Nullzählung.

Analytics liefert in `meta.bereich` Aggregationen über den vollständigen
gefilterten Bestand und dessen historische Datumsgrenzen. Ohne Dataset-/Teamfilter
umfasst das beide Datensätze. OpenStack-Ereignisse werden über `(pid, ts)` angenähert;
das sind keine nachgewiesenen Vorfälle. Relative Zeitfragen benötigen erst diese
Datumsgrenzen. Ränge gelten ausschließlich innerhalb ihrer `vergleichsgruppe`.

## Kosten und Grenzen

- Aktuelle Qualitätskonfiguration: `gpt-6.1-sol`, Reasoning `medium`, Standard-Tarif
  (`service_tier="default"`). Keine Fast-/Ultrafast-Aufschläge.
  Die preiswerte Mini-Variante bleibt in der Preistabelle, war in den Falltests
  aber bei Zeilen-/Ereignisinterpretation und getrennten Ranglisten unzuverlässiger.
- Höchstens 4 Modellanfragen, 6 Werkzeugaufrufe und 2400 Ausgabetokens je Modellanfrage.
  Die vierte Runde dient ausschließlich der abschließenden Antwort.
- Höchstens 80 KB serialisierter Anfragekontext; 30 Sekunden API-Timeout, keine SDK-Retries.
- Vor jeder Anfrage konservative Reservierung im lokalen `.agent-usage.sqlite3`.
  Gesamtkontrolle: 5 USD für alle über dieses Protokoll erfassten Aufrufe.
- GPT-6.1 Sol kostet im Standard-Tarif 2 USD/Million Eingabetokens,
  0,10 USD/Million Cache-Lesetokens, 2,50 USD/Million Cache-Schreibtokens und
  10 USD/Million Ausgabetokens (offizielle Modellseite, 17.10.2026).
  Das lokale Protokoll rechnet vorsichtig alle Eingabetokens zu 2,50 USD:
  Cache-Schreiben ist damit abgedeckt, Rabatte werden nicht abgezogen.
  Deshalb kann die Schätzung über dem tatsächlichen Plattformverbrauch liegen.
  Historische Modelle bleiben korrekt bepreist: GPT-5.4 2,50/15 USD, Mini 0,75/4,50 USD.
  Bei Timeout/fehlenden Verbrauchsdaten bleibt die Reservierung erhalten.
- Das ist eine lokale Kostenschätzung, keine centgenaue Rechnung und kein
  kontoweites OpenAI-Limit. Andere Programme, Steuer, Preisänderungen und gelöschte
  Protokolle werden damit nicht abgedeckt. Das Kostenprotokoll nicht löschen,
  um innerhalb des vereinbarten Testbudgets zu bleiben. Auto-Nachladen bleibt aus.
- Ein Modellwechsel benötigt zuerst eine geprüfte Ergänzung der Preistabelle;
  unbekannte Modelle werden vor dem Aufruf gesperrt.

Quellen: [GPT-6.1 Sol und Preise](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[GPT-5.4 und Preise](https://developers.openai.com/api/docs/models/gpt-5.4),
[Mini und Preise](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[Werkzeugaufrufe](https://developers.openai.com/api/docs/guides/function-calling).

## Prüfungen

Kostenlose lokale Tests mit künstlichen Daten:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Optionaler kostenpflichtiger Verbindungstest, ebenfalls **nur künstliche Daten**:

```powershell
.\.venv\Scripts\python.exe -m agent.smoke --live
```

Am 17.10.2026 erfolgreich: ein echter OpenAI-Werkzeugaufruf und Antwort mit `[B1]`,
zwei Modellanfragen, 2054 Eingabe- und 83 Ausgabetokens; geschätzt 0,001914 USD.
Dies bestätigt die Anbindung, nicht die fachliche Qualität auf echten Logs.

## Abnahme auf echten Daten

```powershell
# Kostenlos: alle Regressionstests einschließlich SereneDB-Fixtures
$env:ANALYTICS_TEST_DB='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Kostenlos: vollständige echte Daten und SQL-Kennzahlen prüfen
.\.venv\Scripts\python.exe -m tests.check_analytics_real
.\.venv\Scripts\python.exe -m tests.check_agent_real
# Kostenpflichtig: zusätzlich je eine echte OpenAI-Antwort pro Rolle
.\.venv\Scripts\python.exe -m tests.check_agent_real --live
```

Am 17.10.2026: 40 Tests einschließlich echter SereneDB-Fixtures bestanden.
Erens Pipeline lokal vollständig ausgeführt: 4.747.963 BGL-Zeilen/399 Templates,
207.820 OpenStack-Zeilen/71 Templates, keine unerkannten Zeilen. Die SQL-Abnahme
bestätigt vollständige Ownership, 152.734 BGL-0019-Treffer, 22.529 Knoten für
BGL-0119 und dessen Rang vor BGL-0019, sowie 192 Cloud-Compute-ERROR-Zeilen in
acht Ereignissen. Die vier bekannten Anomalie-VMs entsprechen den vier längsten
Spawn-Dauern. Alle sechs Werkzeuge wurden durch den Agent-Adapter ausgeführt;
die Bereichsstatistik deckt beide vollständigen Datensätze ab.

Berichte mit SQL und Daten liegen lokal in `out/analytics-validation.json` und
`out/agent-validation.json`. `live_ablauf_bestanden` prüft den technischen Ablauf;
die sprachliche Interpretation muss zusätzlich mit den Belegen verglichen werden.
Prompts und Belegprüfung garantieren keine inhaltlich korrekte Interpretation.

Vergleichsbasis vor dem Upgrade: GPT-5.4/medium: alle drei Rollen mit Status `ok` und echten
DB-Belegen. Kosten der drei Fragen zusammen geschätzt 0,2515 USD. Einschließlich
Verbindungstest und Modell-/Prompt-Vergleichen erfasst das lokale Kostenprotokoll
damals 0,603281 USD (43 abgeschlossene Modellanfragen). Kein kontoweit geprüftes Guthaben.
In den geprüften Antworten stimmen die zentralen Unterscheidungen: langsame VM
ohne bewiesene Ursache, 192 Traceback-Zeilen versus acht Ereignisse, getrennte
Empfehlungen für BGL/OpenStack. Gekürzte Template-ID-Listen sind Beispiele,
keine Rangliste führender Einzelprobleme; die UI sollte sie entsprechend beschriften.

Lokale Integrationskorrekturen in `tools/engineer.py`: Gesamttreffer über alle
Gruppen zählen; SQL für Zusatzstatistiken erhalten; Such-Fallback kennzeichnen;
bei VM-Kontext einen überschaubaren verknüpften Request bevorzugen; Services
als Liste zeigen (alphabetisches MIN/MAX ist keine zeitliche Reihenfolge).
`tools/db.py` lädt die lokale `.env` und begrenzt den Verbindungsaufbau.

Nächster gemeinsamer Schritt: Omars UI mit `antworte` und dem vollständigen
Belege-Panel verbinden und die drei Demo-Fragen darin prüfen. Die Oberfläche
ist noch nicht Teil dieser Agent-Abnahme.

## Upgrade auf GPT-6.1 Sol (17.10.2026)

Aktives Modell und lokale `.env` auf `gpt-6.1-sol` umgestellt; mittlerer
Denkaufwand und Responses-Tool-Calling beibehalten, Standard-Tarif explizit.
40 automatische Tests bestanden. Alle drei Live-Fälle erneut mit Status `ok`:
VM-Dauer/Request-Kontext, 192 Traceback-Zeilen versus acht Ereignisse und
getrennte BGL-/OpenStack-Empfehlungen. Diese Fallprüfung ist kein allgemeiner
Qualitätsnachweis für beliebige Fragen.

Konservative Kostenschätzung der drei neuen Fragen: 0.223800 USD.
Alle bisherigen protokollierten Tests: 0.827081 USD; Cache-Rabatte werden
nicht abgezogen, kein kontoweit abgefragter Rechnungsbetrag.
