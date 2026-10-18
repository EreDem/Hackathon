# Aufnahme und Abgabe

## Euer nächster Schritt

Für die genaue Bedienung der Website zuerst den
**[Website-Demo-Klickplan](Website-Demo-Klickplan.md)** öffnen. Er ordnet die
einzelnen Klicks und sichtbaren Belege den passenden englischen Sätzen zu.

Öffnet **[Demo-Script-and-Recording-Guide.pdf](Demo-Script-and-Recording-Guide.pdf)**.
Seite 1 erklärt die Vorbereitung, Seite 2 enthält die drei kopierfertigen Fragen.
Auf den Seiten 3-6 steht der **englische Sprechtext** mit Zeitmarken und deutschen
Regieanweisungen. Seite 7 erklärt den Klickplan und die Abgabe.

**Ziel: etwa 4:30 Minuten. Maximal: 5:00 Minuten.** Das Skript umfasst 400 englische
Wörter. Die tatsächliche Dauer hängt von eurem Sprechtempo und den Klicks ab:
einmal mit Stoppuhr proben. Nur den englischen Text unter SPEAK vorlesen.

## Die Dateien

- **[Slides als PDF](Log-Observatory-Slides.pdf):** diese Datei gehört in die Abgabe.
  Sie enthält acht Hauptfolien und zwei technische Referenzfolien. Im Video nur
  die ersten acht Folien verwenden.
- **[Bearbeitbare PowerPoint](Log-Observatory-Slides.pptx):** editierbare Texte,
  Tabellen und Diagramme. Der Sprechtext steht auch in den Notizen.
- **[Skript als Markdown](Demo-Script.md):** zum Kopieren oder Lesen auf einem
  zweiten Bildschirm.
- **[Ausgeführte SQL und echte Belege](evidence/presentation-evidence.json):**
  öffentliche Challenge-Daten und der tatsächlich bestätigte Agent-Fall.

## Das Video muss die Anwendung zeigen

Folien vorzulesen genügt für die Challenge nicht. Nehmt drei echte Browser-Clips
auf, je einen für Engineer, Team Lead und Manager. Zeigt die eingegebene Frage,
die ausgewählten Werkzeuge, die ausgeführte SQL und passende Ergebniszeilen.
Danach die Clips mit den Folien und eurem gesprochenen Text zusammensetzen.
Wartezeiten könnt ihr herausschneiden. Die tatsächlichen Antworten und Belege
behalten und keine Erfolge nachstellen. Bei abweichender Antwort den Sprechtext
anpassen. Die Rohdaten sind historisch und die Team-Zuordnung ist fiktiv.

Die drei Rollen zeigen unterschiedliche Entscheidungen:

1. **Engineer / OpenStack / All teams:** Traceback des Cache Managers und
   `InvalidDiskInfo`, mit konkreten Log-IDs und einem nächsten Diagnoseschritt.
2. **Team Lead / BGL / HPC Kernel:** wiederkehrende Muster, vollständige
   Aggregationen und der zeitlich konzentrierte TLB-Ausbruch.
3. **Manager / BGL / All teams:** Häufigkeit gegen beobachtete Knotenreichweite
   abwägen und die Score-Faktoren erklären.

## MCP-Sonderpreis

Der Server und seine Protokolltests sind vorhanden. Eine tatsächlich mit Claude
beantwortete Frage und passende Werkzeugaufrufe müsst ihr noch aufnehmen bzw.
als Team nachweisen. Die OpenAI-Agent-Aufnahme ersetzt den Claude-Test nicht.
Folie 6 und das Skript behaupten deshalb keinen abgeschlossenen Claude-Test.
Nach erfolgreichem Test könnt ihr die Foliennotiz entsprechend aktualisieren.

## Abgabelinks

Für die Folien einen **öffentlichen Link zur PDF-Datei** aus diesem Repository
verwenden. Die veröffentlichte Commit-Version ist auch dann stabil erreichbar,
wenn ihr danach weiterarbeitet. Den endgültigen, anonym geprüften Link findet
ihr nach Veröffentlichung in `Abgabelinks.md` neben dieser Datei.

Das Video nehmt ihr selbst auf und ladet die fertige MP4 hoch. Einen Link nutzen,
der ohne Anmeldung oder Freigabe-Anfrage funktioniert. Beide Links in einem
privaten Browserfenster testen. Das Skript oder die PowerPoint ersetzen weder
die Slides-PDF noch die Videoaufnahme im Formular. Das Formular verlangt für
Video und Slides getrennte Links.

## Quellen und Grenzen

Die Zahlen stammen aus den ausgeführten Abfragen in dieser Evidenzdatei und aus
`docs/evidence/worked-investigation.json` sowie
`docs/evidence/mcp-protocol-check.json`. Die neue Vergleichsabfrage der
Referenzfolie wurde am 18.10.2026 nochmals gegen den vollständigen lokalen
BGL-Bestand ausgeführt. Der Engineer-Fall ist der echte bestätigte Live-Test.

Nutzen im Betriebsalltag und der Kundenpilot sind Vorschläge. Wir behaupten keine
gemessene Zeitersparnis, keinen belegten wirtschaftlichen Schaden und keinen
bereits laufenden Kundenpilot. Beobachtete Knoten sind keine Kundenzahl.
Event-Gruppierung und Prioritäts-Score bleiben Heuristiken. Die Slides-PDF enthält
hochauflösende Folienabbildungen; für Text-, Daten- oder Diagrammänderungen die
bearbeitbare PowerPoint verwenden.
