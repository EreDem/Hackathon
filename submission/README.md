# Aufnahme und Abgabe

## Aktueller Stand

Die Slides und das Video sind **zwei getrennte Abgaben**. Das aktuelle Video zeigt
nur die Bedienung der Anwendung; die Folien werden dabei nicht eingeblendet.
Die etwa 3:08 Minuten lange Schnittvorlage wurde vom Team nachgesprochen. Die
fertige Aufnahme mit eurer Stimme liegt beim Team und muss noch hochgeladen werden.

- [Jury-Guide mit Zuordnung aller Anforderungen](Jury-Guide.md) (Englisch).
- [Slides als PDF](Log-Observatory-Slides.pdf): acht Hauptfolien und zwei technische
  Referenzfolien; diese PDF ist die Folienabgabe.
- [Bearbeitbare PowerPoint](Log-Observatory-Slides.pptx).
- [Aktueller englischer Sprechtext](Video-Narration-English.md): passt zum Video
  ohne Folien. Alte 4:30-Aufnahmepläne werden nicht mehr verwendet.
- [Links für die Formularfelder 4, 5 und 6](Abgabelinks.md).
- [Ausgeführte SQL und echte Folienbelege](evidence/presentation-evidence.json).
- [Vollständige dokumentierte Untersuchung für alle drei Rollen](../docs/worked-investigation.md).

`Demo-Script.md`, `Website-Demo-Klickplan.md`, `demo-plan.json` und
`Demo-Script-and-Recording-Guide.pdf` sind ältere Aufnahmeunterlagen. Sie sind
kein Teil der endgültigen Formularabgabe und ersetzen den aktuellen Sprechtext nicht.

## Video: letzter Schritt beim Team

Die fertige MP4 mit eurer Stimme hochladen und ohne Anmeldung öffnen. Das Video
muss höchstens fünf Minuten dauern. Es zeigt Engineer/OpenStack, Team Lead/BGL
und Manager/BGL, jeweils die Frage, tatsächliche Agent-Werkzeuge, ausgeführte SQL
und passende Ergebnisse. Die Produktbeschreibung am Anfang benennt das Problem.
Die konkrete Dauer der finalen MP4 muss nach dem letzten Schnitt geprüft werden.

Die lokalen Dateien unter `submission/video/` sind Schnitt- und Sprachvorlagen.
Sie werden nicht automatisch als eure endgültige vertonte Aufnahme veröffentlicht.
Ein Skript, eine PowerPoint oder eine MP4 ohne eigene öffentliche URL ersetzt
den Videolink im Formular nicht.

## MCP-Sonderpreis: noch offener Nachweis

Server, sieben Lesewerkzeuge, drei Rollen-Prompts und echte Protokolltests sind
vorhanden. Die [Claude-Anleitung](../docs/MCP.md) erklärt die Verbindung und die
drei Fragen für den Test. **Eine tatsächliche Claude-Aufnahme oder ein Protokoll
liegt laut Team noch nicht vor.** Die OpenAI-Webdemo ersetzt diesen Nachweis
nicht. Folie 6 nennt diesen Schritt deshalb weiterhin offen. Nach bestandenem
Claude-Test den Nachweis veröffentlichen und erst dann den Status aktualisieren.

## Quellen und Grenzen

Die Folienzahlen sind durch [Folienbelege](evidence/presentation-evidence.json)
und die [Untersuchungsbelege](../docs/evidence/worked-investigation.json)
nachvollziehbar. Die Vergleichs-SQL steht zusätzlich in
[bgl-pattern-comparison.sql](evidence/bgl-pattern-comparison.sql).

Kundenpilot und erwarteter Nutzen sind Vorschläge. Zeitersparnis und
wirtschaftlicher Schaden wurden nicht gemessen. Beobachtete Knoten sind keine
Kundenzahl. Historische Daten, fiktive Ownership, gekürzte Ergebnisse und
heuristische Ereignisse/Prioritätsscores bleiben ausdrücklich benannte Grenzen.
